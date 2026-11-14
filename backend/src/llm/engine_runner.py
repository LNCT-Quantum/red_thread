"""Local-only inference adapter for Red Thread's LLM integration.

The module accepts a fully formatted prompt string from the prompt/context layer.
It deliberately does not own character personas, case facts, clue validation, or
Fact-ID extraction. Those responsibilities remain with the other team members.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional, Tuple
from urllib.parse import urlparse

import requests


class EngineError(RuntimeError):
    """Base error for local inference failures."""

    code = "ENGINE_ERROR"


class EngineUnavailableError(EngineError):
    code = "ENGINE_UNAVAILABLE"


class ModelNotFoundError(EngineError):
    code = "MODEL_NOT_FOUND"


class EngineTimeoutError(EngineError):
    code = "ENGINE_TIMEOUT"


class EngineConfigurationError(EngineError):
    code = "ENGINE_CONFIGURATION_ERROR"


class EngineRuntimeError(EngineError):
    """The server answered, but reported a failure (e.g. runner crash, out of memory)."""

    code = "ENGINE_RUNTIME_ERROR"


class EmptyCompletionError(EngineError):
    """The stream finished without a single generated token."""

    code = "EMPTY_COMPLETION"


class IncompleteStreamError(EngineError):
    """The connection ended before the backend sent its final 'done' marker."""

    code = "INCOMPLETE_STREAM"


@dataclass(frozen=True)
class EngineConfig:
    backend: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b-instruct-q4_K_M"
    llama_cpp_url: str = "http://127.0.0.1:8080"
    llama_cpp_model_path: str = ""
    llama_cpp_slot_id: int = 0
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 10.0          # max silence between two streamed chunks (warm model)
    request_timeout_s: float = 60.0       # non-streaming generate(): wait for the full answer
    cold_start_timeout_s: float = 120.0   # first request after start: the model may still be loading
    total_deadline_s: float = 30.0        # hard cap on one whole streamed generation
    keep_alive: str = "5m"
    num_ctx: int = 4096
    num_predict: int = 140
    temperature: float = 0.3
    top_p: float = 0.9
    num_thread: Optional[int] = None
    num_gpu: Optional[int] = None

    @classmethod
    def from_env(cls) -> "EngineConfig":
        backend = os.getenv("LLM_BACKEND", "ollama").strip().lower()
        try:
            num_thread = _optional_int_env("LLM_NUM_THREAD")
            num_gpu = _optional_int_env("LLM_NUM_GPU")
            slot_id = int(os.getenv("LLAMA_CPP_SLOT_ID", "0"))
            config = cls(
                backend=backend,
                ollama_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
                ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M").strip(),
                llama_cpp_url=os.getenv("LLAMA_CPP_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
                llama_cpp_model_path=os.getenv("LLAMA_CPP_MODEL_PATH", "").strip(),
                llama_cpp_slot_id=slot_id,
                connect_timeout_s=float(os.getenv("LLM_CONNECT_TIMEOUT_S", "5")),
                read_timeout_s=float(os.getenv("LLM_READ_TIMEOUT_S", "10")),
                request_timeout_s=float(os.getenv("LLM_REQUEST_TIMEOUT_S", "60")),
                cold_start_timeout_s=float(os.getenv("LLM_COLD_START_TIMEOUT_S", "120")),
                total_deadline_s=float(os.getenv("LLM_TOTAL_DEADLINE_S", "30")),
                keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "5m"),
                num_ctx=int(os.getenv("LLM_NUM_CTX", "4096")),
                num_predict=int(os.getenv("LLM_NUM_PREDICT", "140")),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
                top_p=float(os.getenv("LLM_TOP_P", "0.9")),
                num_thread=num_thread,
                num_gpu=num_gpu,
            )
        except ValueError as exc:
            raise EngineConfigurationError(f"Invalid numeric environment setting: {exc}") from exc
        config.validate()
        return config

    @property
    def base_url(self) -> str:
        return self.ollama_url if self.backend == "ollama" else self.llama_cpp_url

    @property
    def timeout(self) -> Tuple[float, float]:
        return (self.connect_timeout_s, self.read_timeout_s)

    @property
    def model_name(self) -> str:
        return self.ollama_model if self.backend == "ollama" else (self.llama_cpp_model_path or "server-loaded-model")

    def validate(self) -> None:
        if self.backend not in {"ollama", "llama_cpp"}:
            raise EngineConfigurationError("LLM_BACKEND must be either 'ollama' or 'llama_cpp'.")
        _validate_local_url(self.base_url)
        if self.backend == "ollama" and not self.ollama_model:
            raise EngineConfigurationError("OLLAMA_MODEL cannot be empty.")
        if min(self.connect_timeout_s, self.read_timeout_s, self.request_timeout_s,
               self.cold_start_timeout_s, self.total_deadline_s) <= 0:
            raise EngineConfigurationError("All timeouts and deadlines must be greater than zero.")
        if self.num_ctx <= 0 or self.num_predict <= 0:
            raise EngineConfigurationError("LLM_NUM_CTX and LLM_NUM_PREDICT must be greater than zero.")
        if not 0 <= self.temperature <= 2:
            raise EngineConfigurationError("LLM_TEMPERATURE must be between 0 and 2.")
        if not 0 < self.top_p <= 1:
            raise EngineConfigurationError("LLM_TOP_P must be greater than 0 and at most 1.")
        if self.num_thread is not None and self.num_thread <= 0:
            raise EngineConfigurationError("LLM_NUM_THREAD must be greater than zero when set.")
        if self.num_gpu is not None and self.num_gpu < 0:
            raise EngineConfigurationError("LLM_NUM_GPU cannot be negative.")


def _optional_int_env(name: str) -> Optional[int]:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


def _validate_local_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise EngineConfigurationError(
            "For this local-only component, backend URLs must use http://127.0.0.1, "
            "http://localhost, or http://[::1]. Cloud/remote endpoints are not allowed."
        )


def _ns_to_ms(value: Any) -> Optional[float]:
    try:
        return round(float(value) / 1_000_000, 3) if value is not None else None
    except (TypeError, ValueError):
        return None


def _with_rate(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Add tokens_per_sec (needed by TurnMetrics) from eval_count / eval_duration_ms."""
    count, duration = metrics.get("eval_count"), metrics.get("eval_duration_ms")
    try:
        metrics["tokens_per_sec"] = round(count / (duration / 1000), 2) if count and duration else None
    except (TypeError, ZeroDivisionError):
        metrics["tokens_per_sec"] = None
    return metrics


def _ollama_metrics(data: Dict[str, Any], num_ctx: Optional[int] = None) -> Dict[str, Any]:
    done_reason = data.get("done_reason")
    prompt_tokens = data.get("prompt_eval_count")
    metrics = {
        "total_duration_ms": _ns_to_ms(data.get("total_duration")),
        "load_duration_ms": _ns_to_ms(data.get("load_duration")),
        "prompt_eval_duration_ms": _ns_to_ms(data.get("prompt_eval_duration")),
        "eval_duration_ms": _ns_to_ms(data.get("eval_duration")),
        "prompt_eval_count": prompt_tokens,
        "eval_count": data.get("eval_count"),
        "done_reason": done_reason,
        # "length" means num_predict was hit: the answer (and any JSON in it) may be cut off.
        "truncated": done_reason == "length",
        # Ollama silently drops the oldest tokens when the prompt exceeds num_ctx. Best-effort
        # heuristic (cached prefix tokens are not counted, so it can under-report).
        "possible_prompt_truncation": bool(num_ctx and prompt_tokens and prompt_tokens >= num_ctx),
    }
    return _with_rate(metrics)


def _llama_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    timings = data.get("timings") or {}
    stop_type = data.get("stop_type")
    metrics = {
        "prompt_eval_duration_ms": timings.get("prompt_ms", data.get("prompt_ms")),
        "eval_duration_ms": timings.get("predicted_ms", data.get("predicted_ms")),
        "prompt_eval_count": timings.get("prompt_n", data.get("tokens_evaluated")),
        "eval_count": timings.get("predicted_n", data.get("tokens_predicted")),
        "cache_tokens": data.get("tokens_cached", timings.get("cache_n")),
        "backend_reported_ttft_ms": timings.get("first_token_ms"),
        "stop_type": stop_type,
        # stop_type == "limit": n_predict reached, so the output may be cut off mid-JSON.
        "truncated": stop_type == "limit" or bool(data.get("stopped_limit")),
        # llama.cpp sets "truncated" when the *prompt* did not fit in the context window.
        "possible_prompt_truncation": bool(data.get("truncated")),
    }
    return _with_rate(metrics)


def _extract_error(data: Any) -> Optional[str]:
    """Return the message of an in-band error object ({"error": ...}) or None."""
    if not isinstance(data, dict) or not data.get("error"):
        return None
    err = data["error"]
    return str(err.get("message") or err) if isinstance(err, dict) else str(err)


def _raise_backend_error(message: str) -> None:
    if "not found" in message.lower():
        raise ModelNotFoundError(message)
    raise EngineRuntimeError(message)


def _normalize_response_format(response_format: Any) -> Optional[Any]:
    """Accept None, "json", or a JSON-schema dict. Anything else is a caller bug."""
    if response_format is None or response_format == "json" or isinstance(response_format, dict):
        return response_format
    raise EngineConfigurationError("response_format must be None, 'json', or a JSON-schema dict.")


class LocalLLMEngine:
    """Small backend adapter with a stable interface for the integration team."""

    def __init__(self, config: Optional[EngineConfig] = None, session: Optional[requests.Session] = None):
        self.config = config or EngineConfig.from_env()
        self.config.validate()
        self.session = session or requests.Session()
        # Avoid inherited HTTP(S)_PROXY settings for loopback-only inference.
        self.session.trust_env = False
        # False until one generation has succeeded. While False, the model may still be loading
        # from disk, so requests get the longer cold-start timeout instead of the 10 s warm one.
        self._warm = False

    # ------------------------------------------------------------------ HTTP plumbing
    def _get(self, path: str) -> requests.Response:
        try:
            response = self.session.get(f"{self.config.base_url}{path}", timeout=self.config.timeout)
            response.raise_for_status()
            return response
        except requests.Timeout as exc:
            raise EngineTimeoutError(f"Timed out contacting {self.config.backend} health/model API.") from exc
        except requests.RequestException as exc:
            raise EngineUnavailableError(f"Cannot reach local {self.config.backend} server: {exc}") from exc

    def _post(
        self,
        path: str,
        payload: Dict[str, Any],
        stream: bool = False,
        read_timeout: Optional[float] = None,
    ) -> requests.Response:
        timeout = (self.config.connect_timeout_s, read_timeout or self.config.read_timeout_s)
        try:
            response = self.session.post(
                f"{self.config.base_url}{path}",
                json=payload,
                stream=stream,
                timeout=timeout,
                headers={
                    "Accept": (
                        "text/event-stream" if self.config.backend == "llama_cpp" else "application/x-ndjson"
                    ) if stream else "application/json"
                },
            )
            if response.status_code == 404 and self.config.backend == "ollama" and path != "/api/tags":
                detail = str(getattr(response, "text", "") or "")[:200]
                response.close()
                raise ModelNotFoundError(
                    f"Ollama returned 404 (model '{self.config.ollama_model}' missing?). "
                    f"Run: ollama pull {self.config.ollama_model}. {detail}".strip()
                )
            response.raise_for_status()
            return response
        except requests.Timeout as exc:
            raise EngineTimeoutError(f"Local {self.config.backend} request timed out.") from exc
        except requests.RequestException as exc:
            raise EngineUnavailableError(f"Local {self.config.backend} request failed: {exc}") from exc

    def _generation_read_timeout(self, streaming: bool) -> float:
        if not self._warm:
            return self.config.cold_start_timeout_s
        return self.config.read_timeout_s if streaming else self.config.request_timeout_s

    # ------------------------------------------------------------------ diagnostics
    def check_health(self) -> bool:
        """Return True only when the selected local server is ready."""
        try:
            path = "/api/tags" if self.config.backend == "ollama" else "/health"
            self._get(path)
            return True
        except EngineError:
            return False

    def ensure_model_available(self) -> None:
        """For Ollama, verify the configured model is pulled before starting work."""
        if self.config.backend != "ollama":
            return
        data = self._get("/api/tags").json()
        models = data.get("models", [])
        names = {item.get("name") or item.get("model") for item in models}
        if self.config.ollama_model not in names:
            raise ModelNotFoundError(
                f"Model '{self.config.ollama_model}' is not installed. Run: ollama pull {self.config.ollama_model}"
            )

    def get_engine_info(self) -> Dict[str, Any]:
        """Return diagnostics without making any external/cloud request."""
        info: Dict[str, Any] = {
            "backend": self.config.backend,
            "base_url": self.config.base_url,
            "model": self.config.model_name,
            "healthy": self.check_health(),
            "local_only": True,
        }
        if self.config.backend == "ollama" and info["healthy"]:
            try:
                response = self._post("/api/show", {"model": self.config.ollama_model})
                body = response.json()
                details = body.get("details", {})
                info["quantization_level"] = details.get("quantization_level")
                info["parameter_size"] = details.get("parameter_size")
                info["family"] = details.get("family")
            except (EngineError, ValueError):
                info["model_metadata_available"] = False
        elif self.config.backend == "llama_cpp":
            info["gguf_path"] = self.config.llama_cpp_model_path or None
            info["prompt_cache_enabled"] = True
        return info

    def verify_model_quantization(self, expected: str = "Q4_K_M") -> Dict[str, Any]:
        """Inspect Ollama metadata; this reports mismatch rather than hiding it."""
        if self.config.backend != "ollama":
            raise EngineConfigurationError("Quantization metadata inspection via /api/show is an Ollama-only helper.")
        body = self._post("/api/show", {"model": self.config.ollama_model}).json()
        actual = (body.get("details") or {}).get("quantization_level")
        return {"expected": expected, "actual": actual, "matches": bool(actual and actual.upper() == expected.upper())}

    # ------------------------------------------------------------------ payloads
    def _ollama_payload(self, prompt: str, stream: bool, response_format: Any = None) -> Dict[str, Any]:
        options: Dict[str, Any] = {
            "num_ctx": self.config.num_ctx,
            "num_predict": self.config.num_predict,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        if self.config.num_thread is not None:
            options["num_thread"] = self.config.num_thread
        if self.config.num_gpu is not None:
            options["num_gpu"] = self.config.num_gpu
        payload: Dict[str, Any] = {
            "model": self.config.ollama_model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self.config.keep_alive,
            "options": options,
        }
        if response_format is not None:
            # "json" -> JSON mode; a dict -> structured output constrained by that JSON schema.
            payload["format"] = response_format
        return payload

    def _llama_payload(
        self, prompt: str, stream: bool, cache_prompt: Optional[bool] = None, response_format: Any = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "stream": stream,
            "n_predict": self.config.num_predict,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "cache_prompt": True if cache_prompt is None else bool(cache_prompt),
        }
        if self.config.llama_cpp_slot_id >= 0:
            payload["id_slot"] = self.config.llama_cpp_slot_id
        if response_format is not None:
            payload["json_schema"] = {"type": "object"} if response_format == "json" else response_format
        return payload

    # ------------------------------------------------------------------ warm-up
    def warmup(self) -> Dict[str, Any]:
        """Load the model into memory with a 1-token request so real turns never pay the load cost.

        Returns {"warm": True, "elapsed_ms": ...}. Raises EngineError if the server cannot answer.
        """
        started = time.perf_counter()
        # Config is frozen, so build a throw-away payload with a 1-token budget instead of mutating it.
        if self.config.backend == "ollama":
            payload = self._ollama_payload("Hi", False)
            payload["options"]["num_predict"] = 1
            path = "/api/generate"
        else:
            payload = self._llama_payload("Hi", False)
            payload["n_predict"] = 1
            path = "/completion"
        body = self._post(path, payload, read_timeout=self.config.cold_start_timeout_s).json()
        message = _extract_error(body)
        if message:
            _raise_backend_error(message)
        self._warm = True
        return {"warm": True, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}

    # ------------------------------------------------------------------ generation
    def generate_with_metrics(self, prompt: str, response_format: Any = None) -> Dict[str, Any]:
        """Return full text and final backend metrics; raises EngineError on failure."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        response_format = _normalize_response_format(response_format)
        read_timeout = self._generation_read_timeout(streaming=False)
        if self.config.backend == "ollama":
            response = self._post(
                "/api/generate", self._ollama_payload(prompt, False, response_format), read_timeout=read_timeout
            )
            body = response.json()
            message = _extract_error(body)
            if message:
                _raise_backend_error(message)
            text, metrics = body.get("response", ""), _ollama_metrics(body, self.config.num_ctx)
        else:
            response = self._post(
                "/completion", self._llama_payload(prompt, False, None, response_format), read_timeout=read_timeout
            )
            body = response.json()
            message = _extract_error(body)
            if message:
                _raise_backend_error(message)
            text, metrics = body.get("content", ""), _llama_metrics(body)
        if not text:
            raise EmptyCompletionError("The local engine returned an empty completion.")
        self._warm = True
        return {"text": text, "truncated": bool(metrics.get("truncated")), "metrics": metrics}

    def generate(self, prompt: str, response_format: Any = None) -> str:
        """Backward-compatible text-only generation method."""
        return self.generate_with_metrics(prompt, response_format)["text"]

    def stream_generate(
        self, prompt: str, cache_prompt: Optional[bool] = None, response_format: Any = None
    ) -> Iterator[Dict[str, Any]]:
        """Yield token events, then one completion event; every failure becomes an error event.

        Token event:    {"type":"token", "token":"...", "ttft_ms": float|None}   (ttft only on the 1st)
        Completion:     {"type":"complete", "text":"...", "truncated": bool, "metrics": {...}}
        Error:          {"type":"error", "error":{"code":"...", "message":"..."}}

        `truncated` is True when the model hit the num_predict cap, so any JSON in `text` may be cut
        off. Downstream parsers should treat it as "retry or use the regex fallback".
        """
        if not isinstance(prompt, str) or not prompt.strip():
            yield {"type": "error", "error": {"code": "INVALID_PROMPT", "message": "prompt must be a non-empty string"}}
            return
        try:
            response_format = _normalize_response_format(response_format)
        except EngineConfigurationError as exc:
            yield {"type": "error", "error": {"code": exc.code, "message": str(exc)}}
            return

        started = time.perf_counter()
        deadline = self.config.total_deadline_s if self._warm else self.config.cold_start_timeout_s
        first_token_ms: Optional[float] = None
        chunks = []
        final_metrics: Dict[str, Any] = {}
        finished = False
        response: Optional[requests.Response] = None

        def check_deadline() -> None:
            if time.perf_counter() - started > deadline:
                raise EngineTimeoutError(f"Generation exceeded the {deadline:g}s total deadline.")

        try:
            read_timeout = self._generation_read_timeout(streaming=True)
            if self.config.backend == "ollama":
                response = self._post(
                    "/api/generate", self._ollama_payload(prompt, True, response_format),
                    stream=True, read_timeout=read_timeout,
                )
                for raw_line in response.iter_lines(decode_unicode=True):
                    line = _decode_line(raw_line).strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        raise ValueError("stream line is not a JSON object")
                    message = _extract_error(data)
                    if message:  # e.g. {"error": "llama runner process has terminated"}
                        _raise_backend_error(message)
                    token = data.get("response", "")
                    if token:
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - started) * 1000
                        chunks.append(token)
                        yield {"type": "token", "token": token, "ttft_ms": round(first_token_ms, 3) if len(chunks) == 1 else None}
                    if data.get("done"):
                        final_metrics = _ollama_metrics(data, self.config.num_ctx)
                        finished = True
                    check_deadline()
            else:
                response = self._post(
                    "/completion", self._llama_payload(prompt, True, cache_prompt, response_format),
                    stream=True, read_timeout=read_timeout,
                )
                for raw_line in response.iter_lines(decode_unicode=True):
                    line = _decode_line(raw_line).strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        finished = True
                        break
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        raise ValueError("stream line is not a JSON object")
                    message = _extract_error(data)
                    if message:
                        _raise_backend_error(message)
                    token = data.get("content", "")
                    if token:
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - started) * 1000
                        chunks.append(token)
                        yield {"type": "token", "token": token, "ttft_ms": round(first_token_ms, 3) if len(chunks) == 1 else None}
                    if data.get("stop") or data.get("timings"):
                        final_metrics.update(_llama_metrics(data))
                    if data.get("stop"):
                        finished = True
                    check_deadline()

            if not finished:
                raise IncompleteStreamError("The connection ended before the engine sent its final 'done' marker.")
            if not chunks:
                raise EmptyCompletionError("The local engine finished without generating any text.")
            if first_token_ms is not None:
                final_metrics["client_ttft_ms"] = round(first_token_ms, 3)
            final_metrics["generated_characters"] = sum(len(part) for part in chunks)
            self._warm = True
            yield {
                "type": "complete",
                "text": "".join(chunks),
                "truncated": bool(final_metrics.get("truncated")),
                "metrics": final_metrics,
            }
        except EngineError as exc:
            yield {"type": "error", "error": {"code": exc.code, "message": str(exc)}}
        except requests.Timeout as exc:
            yield {"type": "error", "error": {"code": EngineTimeoutError.code, "message": str(exc) or "Local inference timed out."}}
        except requests.RequestException as exc:
            # requests reports a mid-stream read timeout as a ConnectionError; keep the right code.
            code = EngineTimeoutError.code if "read timed out" in str(exc).lower() else EngineUnavailableError.code
            yield {"type": "error", "error": {"code": code, "message": str(exc)}}
        except (ValueError, json.JSONDecodeError) as exc:
            yield {"type": "error", "error": {"code": "INVALID_ENGINE_RESPONSE", "message": f"Could not parse local engine response: {exc}"}}
        except Exception as exc:  # Keep unexpected runtime failures visible to the caller as an event.
            yield {"type": "error", "error": {"code": EngineError.code, "message": str(exc)}}
        finally:
            if response is not None:
                response.close()


def _decode_line(raw_line: Any) -> str:
    if isinstance(raw_line, bytes):
        return raw_line.decode("utf-8", errors="replace")
    return str(raw_line)


_DEFAULT_ENGINE: Optional[LocalLLMEngine] = None


def _get_engine() -> LocalLLMEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = LocalLLMEngine()
    return _DEFAULT_ENGINE


def initialize_engine(config: Optional[EngineConfig] = None, warmup: bool = False) -> Dict[str, Any]:
    """Create, health-check, and validate the selected local backend.

    With warmup=True the model is also loaded into memory (adds `warmup_ms` to the result), so the
    first real interrogation turn is not slowed by a cold start.
    """
    global _DEFAULT_ENGINE
    engine = LocalLLMEngine(config=config)
    if not engine.check_health():
        raise EngineUnavailableError(
            f"{engine.config.backend} is not ready at {engine.config.base_url}. Start the local server and retry."
        )
    engine.ensure_model_available()
    _DEFAULT_ENGINE = engine
    info = engine.get_engine_info()
    if warmup:
        info["warmup_ms"] = engine.warmup()["elapsed_ms"]
    return info


def check_health() -> bool:
    return _get_engine().check_health()


def get_engine_info() -> Dict[str, Any]:
    return _get_engine().get_engine_info()


def verify_model_quantization(expected: str = "Q4_K_M") -> Dict[str, Any]:
    return _get_engine().verify_model_quantization(expected)


def generate(prompt: str, response_format: Any = None) -> str:
    return _get_engine().generate(prompt, response_format=response_format)


def generate_with_metrics(prompt: str, response_format: Any = None) -> Dict[str, Any]:
    return _get_engine().generate_with_metrics(prompt, response_format=response_format)


def stream_generate(
    prompt: str, cache_prompt: Optional[bool] = None, response_format: Any = None
) -> Iterator[Dict[str, Any]]:
    return _get_engine().stream_generate(prompt, cache_prompt=cache_prompt, response_format=response_format)


def stream_sse(
    prompt: str, cache_prompt: Optional[bool] = None, response_format: Any = None
) -> Iterator[str]:
    """Serialize engine events as Server-Sent Events for a FastAPI StreamingResponse."""
    for event in stream_generate(prompt, cache_prompt=cache_prompt, response_format=response_format):
        event_type = event.get("type", "message")
        yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def stream_ndjson(
    prompt: str, cache_prompt: Optional[bool] = None, response_format: Any = None
) -> Iterator[str]:
    """Serialize stream events as newline-delimited JSON records."""
    for event in stream_generate(prompt, cache_prompt=cache_prompt, response_format=response_format):
        yield json.dumps(event, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    try:
        print("Initializing local LLM engine (with warm-up)...")
        print(json.dumps(initialize_engine(warmup=True), indent=2))
        demo_prompt = "In one short sentence, describe why a detective records evidence carefully."
        print("\nStreaming demo:")
        for demo_event in stream_generate(demo_prompt):
            if demo_event["type"] == "token":
                print(demo_event["token"], end="", flush=True)
            elif demo_event["type"] == "complete":
                print("\n\nTruncated:", demo_event["truncated"])
                print("Metrics:", json.dumps(demo_event["metrics"], indent=2))
            elif demo_event["type"] == "error":
                print("\nEngine error:", json.dumps(demo_event["error"], indent=2))
                raise SystemExit(1)
    except EngineError as exc:
        print(f"Engine initialization failed [{exc.code}]: {exc}")
        raise SystemExit(1)
