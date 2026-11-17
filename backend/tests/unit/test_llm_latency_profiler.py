from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

from shared.contracts.dialogue import GenerationMetrics
from src.llm import LatencyProfiler


def dummy_stream_generator() -> Iterator[str]:
    time.sleep(0.05)
    yield '{"content": "'
    time.sleep(0.02)
    yield "I was at home."
    time.sleep(0.01)
    yield '"}'


def test_measure_stream() -> None:
    profiler = LatencyProfiler(target_ttft_ms=800.0)
    full_text, metrics = profiler.measure_stream(
        dummy_stream_generator(),
        model_id="mock-qwen-3b",
        prompt_tokens=120,
    )

    assert "I was at home." in full_text
    assert metrics.time_to_first_token_ms >= 40.0
    assert metrics.time_to_first_token_ms <= metrics.generation_time_ms
    assert metrics.prompt_tokens == 120
    assert metrics.completion_tokens >= 1


def test_record_turn_sla_pass_and_fail() -> None:
    profiler = LatencyProfiler(target_ttft_ms=800.0)

    fast_metrics = GenerationMetrics(
        model_id="mock-qwen-3b",
        time_to_first_token_ms=350.0,
        generation_time_ms=1100.0,
        prompt_tokens=150,
        completion_tokens=40,
    )
    r1 = profiler.record_turn(1, "req_001", "suspect_001", fast_metrics)
    assert r1.sla_passed is True
    assert r1.tokens_per_sec > 0

    slow_metrics = GenerationMetrics(
        model_id="mock-qwen-3b",
        time_to_first_token_ms=920.0,
        generation_time_ms=1800.0,
        prompt_tokens=150,
        completion_tokens=40,
    )
    r2 = profiler.record_turn(2, "req_002", "suspect_001", slow_metrics)
    assert r2.sla_passed is False


def test_benchmark_suite_and_csv_export(tmp_path: Path) -> None:
    profiler = LatencyProfiler(target_ttft_ms=800.0)

    def mock_runner(idx: int) -> tuple[str, GenerationMetrics]:
        ttft = 300.0 + (idx * 5.0)
        metrics = GenerationMetrics(
            model_id="mock-qwen-3b",
            time_to_first_token_ms=ttft,
            generation_time_ms=ttft + 400.0,
            prompt_tokens=140,
            completion_tokens=35,
        )
        return "response", metrics

    results = profiler.run_benchmark_suite(mock_runner, total_turns=50)
    assert len(results) == 50

    summary = profiler.summary()
    assert summary["total_turns"] == 50
    assert summary["passed_turns"] == 50
    assert summary["pass_rate_pct"] == 100.0
    assert summary["min_ttft_ms"] >= 300.0
    assert summary["max_ttft_ms"] <= 600.0

    csv_path = tmp_path / "test_benchmark_report.csv"
    profiler.export_csv(csv_path)

    assert csv_path.is_file()
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 51
    assert "turn_id,request_id,suspect_id" in lines[0]
