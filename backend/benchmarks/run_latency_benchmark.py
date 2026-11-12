from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

from shared.contracts.dialogue import DialogueRequest
from src.llm import FactExtractor, LatencyProfiler


def check_engine_health(base_url: str, target_model: str) -> tuple[bool, str]:
    """Verifies that the local inference engine (Ollama) is running and the model is present."""
    tags_url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(tags_url, headers={"User-Agent": "RedThread-Profiler"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            # Match model name or name with :latest
            matched = any(
                target_model == m or target_model == m.split(":")[0] or target_model == m.replace(":latest", "")
                for m in models
            )
            if not matched:
                return False, f"Engine is online, but model '{target_model}' is not loaded. Available models: {models}"
            return True, f"Engine is online with model '{target_model}'."
    except urllib.error.URLError as exc:
        return False, f"Could not connect to engine at {base_url}: {exc.reason}"
    except Exception as exc:
        return False, f"Engine check failed: {exc}"


def stream_ollama(prompt: str, model: str, base_url: str = "http://127.0.0.1:11434") -> Iterator[str]:
    """Streams live tokens chunk-by-chunk from local Ollama daemon over HTTP socket."""
    generate_url = f"{base_url.rstrip('/')}/api/generate"
    payload = json.dumps({"model": model, "prompt": prompt, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        generate_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "RedThread-Profiler"},
    )

    with urllib.request.urlopen(req, timeout=60.0) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            chunk = json.loads(line)
            yield chunk.get("response", "")
            if chunk.get("done", False):
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="Live Interrogation Latency Benchmark against local model daemon.")
    parser.add_argument("--url", default="http://127.0.0.1:11434", help="Ollama daemon URL (default: http://127.0.0.1:11434)")
    parser.add_argument("--model", default="qwen2.5:3b", help="Model identifier (e.g. qwen2.5:3b, llama3.2:3b)")
    parser.add_argument("--turns", type=int, default=50, help="Number of benchmark interrogation turns (default: 50)")
    parser.add_argument("--output", default="benchmarks/sprint2_benchmark_report.csv", help="Path to export live benchmark CSV")
    args = parser.parse_args()

    print("=" * 65)
    print("RED THREAD — LIVE INFERENCE BENCHMARK RUNNER")
    print("=" * 65)
    print(f"Engine Endpoint: {args.url}")
    print(f"Target Model:    {args.model}")
    print(f"Requested Turns: {args.turns}")
    print("Checking engine health...")

    healthy, message = check_engine_health(args.url, args.model)
    if not healthy:
        print(f"\n[BLOCKED] {message}")
        print("\nNote: Per Sprint 2 work division, model serving (Ollama/llama.cpp) is owned by Anshul (Engine Lead).")
        print("To run the live benchmark, ensure Anshul's engine daemon is running with the target model.")
        print("Zero simulated results will be produced.\n")
        sys.exit(1)

    print(f"[OK] {message}")
    print("\nStarting live measurement across actual streaming socket...")

    profiler = LatencyProfiler(target_ttft_ms=800.0)
    extractor = FactExtractor(strip_unauthorized=True)

    test_request = DialogueRequest(
        request_id="live_bench_init",
        case_id="case_001",
        suspect_id="suspect_001",
        player_message="Where were you at 9:40 PM?",
        authorized_fact_ids=("fact_001", "fact_021", "fact_023"),
        presented_clue_ids=("clue_006",),
    )

    base_prompt = (
        "You are Anaya Kapoor, a composed blind musician questioned by Detective Aarav. "
        "Answer in 1-2 quiet sentences. State facts fact_021 (lost eyesight at 19) or clue_006 (heard footsteps at 9:40 PM). "
        "Output strictly JSON with format: {\"content\": \"...\", \"cited_fact_ids\": [...], \"cited_clue_ids\": [...]}"
    )

    for turn_idx in range(1, args.turns + 1):
        req_id = f"live_turn_{turn_idx:03d}"
        stream = stream_ollama(base_prompt, model=args.model, base_url=args.url)
        full_text, metrics = profiler.measure_stream(
            stream,
            model_id=args.model,
            prompt_tokens=len(base_prompt.split()),
        )

        # Run extraction & validate against contracts
        result = extractor.extract(full_text, test_request, metrics)
        record = profiler.record_turn(turn_idx, req_id, "suspect_001", metrics)

        status = "PASS" if record.sla_passed else "FAIL"
        print(f"Turn {turn_idx:02d}/{args.turns:02d} | TTFT: {record.ttft_ms:6.2f} ms | Total: {record.generation_time_ms:6.2f} ms | SLA: {status} | Strategy: {result.parse_strategy}")

    output_path = Path(args.output)
    profiler.export_csv(output_path)
    summary = profiler.summary()

    print("\n" + "=" * 65)
    print("LIVE INFERENCE BENCHMARK RESULTS")
    print("=" * 65)
    print(f"Total Live Turns:    {summary['total_turns']}")
    print(f"SLA Passed (<800ms): {summary['passed_turns']} / {summary['total_turns']} ({summary['pass_rate_pct']}%)")
    print(f"Min TTFT:            {summary['min_ttft_ms']} ms")
    print(f"Mean TTFT:           {summary['mean_ttft_ms']} ms")
    print(f"P95 TTFT:            {summary['p95_ttft_ms']} ms")
    print(f"Max TTFT:            {summary['max_ttft_ms']} ms")
    print(f"Mean Throughput:     {summary['mean_tokens_per_sec']} tokens/sec")
    print(f"Exported Report:     {output_path.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    main()
