"""Repeatable local benchmark for client TTFT and prompt-prefill timing.

Run with the target local server already started. The script writes a JSON report
and never labels a target as achieved unless measured data supports that result.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from engine_runner import EngineError, get_engine_info, initialize_engine, stream_generate


def run_one(prompt: str, cache_prompt: Optional[bool] = None) -> Dict[str, Any]:
    ttft_ms = None
    completion = None
    error = None
    for event in stream_generate(prompt, cache_prompt=cache_prompt):
        if event.get("type") == "token" and ttft_ms is None:
            ttft_ms = event.get("ttft_ms")
        elif event.get("type") == "complete":
            completion = event
        elif event.get("type") == "error":
            error = event.get("error")
            break
    if error:
        raise RuntimeError(f"Engine error [{error.get('code')}]: {error.get('message')}")
    if completion is None:
        raise RuntimeError("The engine stream ended without a completion event.")
    return {
        "ttft_ms": ttft_ms,
        "prefill_ms": completion["metrics"].get("prompt_eval_duration_ms"),
        "prompt_tokens": completion["metrics"].get("prompt_eval_count"),
        "cache_tokens": completion["metrics"].get("cache_tokens"),
        "tokens_per_sec": completion["metrics"].get("tokens_per_sec"),
        "truncated": bool(completion.get("truncated")),
        "metrics": completion["metrics"],
    }


def median_or_none(values):
    clean = [float(value) for value in values if value is not None]
    return round(statistics.median(clean), 3) if clean else None


def benchmark_llama_cpp(prefix: str, trials: int) -> Dict[str, Any]:
    baseline = []
    cached = []
    for index in range(trials):
        # Same prefix, same-sized changing suffix. Cache is disabled in the control pair.
        suffix_a = f"Control request {index}: respond with one short sentence."
        suffix_b = f"Control follow-up {index}: respond with one short sentence."
        run_one(prefix + suffix_a, cache_prompt=False)
        baseline.append(run_one(prefix + suffix_b, cache_prompt=False))

        # Prime the same slot with the prefix, then change only the suffix.
        suffix_c = f"Cached request {index}: respond with one short sentence."
        suffix_d = f"Cached follow-up {index}: respond with one short sentence."
        run_one(prefix + suffix_c, cache_prompt=True)
        cached.append(run_one(prefix + suffix_d, cache_prompt=True))

    baseline_prefill = median_or_none(item["prefill_ms"] for item in baseline)
    cached_prefill = median_or_none(item["prefill_ms"] for item in cached)
    improvement = None
    if baseline_prefill and cached_prefill is not None:
        improvement = round((baseline_prefill - cached_prefill) / baseline_prefill * 100, 2)

    return {
        "method": "controlled_llama_cpp_cache_prompt_off_vs_on",
        "baseline_prefill_median_ms": baseline_prefill,
        "cached_prefill_median_ms": cached_prefill,
        "prefill_improvement_percent": improvement,
        "cached_ttft_median_ms": median_or_none(item["ttft_ms"] for item in cached),
        "cache_tokens_median": median_or_none(item["cache_tokens"] for item in cached),
        "cached_ttft_all_ms": [item["ttft_ms"] for item in cached],
        "cached_ttft_max_ms": max((item["ttft_ms"] for item in cached if item["ttft_ms"] is not None), default=None),
        "tokens_per_sec_median": median_or_none(item["tokens_per_sec"] for item in cached),
        "truncated_runs": sum(1 for item in baseline + cached if item["truncated"]),
        "target_prefill_improvement_over_50_percent": improvement is not None and improvement > 50,
        "target_ttft_under_800_ms": (
            median_or_none(item["ttft_ms"] for item in cached) is not None
            and median_or_none(item["ttft_ms"] for item in cached) < 800
        ),
        "trials": trials,
    }


def benchmark_ollama(prefix: str, trials: int) -> Dict[str, Any]:
    # Ollama's public generate request does not expose an on/off switch for its internal
    # prefix cache. We therefore report observed repeated-prefix timings, not a controlled
    # cache-on/cache-off comparison.
    warmup = run_one(prefix + "Warm-up request: answer with one short sentence.")
    repeated = []
    for index in range(trials):
        repeated.append(run_one(prefix + f"Follow-up request {index}: answer with one short sentence."))
    warm_prefill = warmup["prefill_ms"]
    repeated_prefill = median_or_none(item["prefill_ms"] for item in repeated)
    observed_improvement = None
    if warm_prefill and repeated_prefill is not None:
        observed_improvement = round((warm_prefill - repeated_prefill) / warm_prefill * 100, 2)
    ttft_median = median_or_none(item["ttft_ms"] for item in repeated)
    return {
        "method": "ollama_observed_repeated_prefix_only",
        "warmup_prefill_ms": warm_prefill,
        "repeated_prefill_median_ms": repeated_prefill,
        "observed_prefill_change_percent": observed_improvement,
        "repeated_ttft_median_ms": ttft_median,
        "repeated_ttft_all_ms": [item["ttft_ms"] for item in repeated],
        "repeated_ttft_max_ms": max((item["ttft_ms"] for item in repeated if item["ttft_ms"] is not None), default=None),
        "tokens_per_sec_median": median_or_none(item["tokens_per_sec"] for item in repeated),
        "truncated_runs": sum(1 for item in repeated if item["truncated"]),
        "target_prefill_improvement_over_50_percent": None,
        "target_ttft_under_800_ms": ttft_median is not None and ttft_median < 800,
        "cache_claim_note": "Ollama does not expose a cache_prompt off switch in this benchmark; this is observational, not controlled proof of KV-cache savings.",
        "trials": trials,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the local Red Thread LLM engine.")
    parser.add_argument("--trials", type=int, default=5, help="Number of repeated measurements (default: 5).")
    parser.add_argument("--output", default="latency_report.json", help="JSON report output path.")
    parser.add_argument(
        "--prompt-file",
        help="Text file holding the real static persona prefix from Anand's prompt synthesizer. "
        "Strongly recommended: the SLA must be proven on the real prompt, not the synthetic default.",
    )
    args = parser.parse_args()
    if args.trials < 3:
        parser.error("Use at least 3 trials for a more useful median measurement.")

    try:
        # warmup=True loads the model first, so cold-start time is not mixed into TTFT.
        info = initialize_engine(warmup=True)
        if args.prompt_file:
            prefix = Path(args.prompt_file).read_text(encoding="utf-8").rstrip() + "\n\n"
            prefix_source = str(Path(args.prompt_file).resolve())
        else:
            # Synthetic fallback so the script runs anywhere; NOT representative of the real prompt.
            prefix = (
                "You are a local fictional-dialogue engine for a detective game. "
                "Follow the supplied prompt, do not invent facts, and answer concisely. "
            ) * 60
            prefix_source = "synthetic default (replace with --prompt-file for the official run)"
        result = benchmark_llama_cpp(prefix, args.trials) if info["backend"] == "llama_cpp" else benchmark_ollama(prefix, args.trials)
        report = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "engine": info,
            "prefix_source": prefix_source,
            "prefix_characters": len(prefix),
            "result": result,
            "interpretation": "TTFT is client-observed from request start to first non-empty token. Prefill values come from backend metrics.",
        }
        output_path = Path(args.output).resolve()
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"\nReport saved to: {output_path}")
        return 0
    except (EngineError, RuntimeError, OSError) as exc:
        print(f"Benchmark failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
