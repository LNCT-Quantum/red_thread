from __future__ import annotations

import csv
import statistics
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.contracts.dialogue import GenerationMetrics

DEFAULT_TTFT_SLA_MS: float = 800.0


@dataclass(frozen=True, slots=True)
class TurnMetricRecord:
    turn_id: int
    request_id: str
    suspect_id: str
    prompt_tokens: int
    completion_tokens: int
    ttft_ms: float
    generation_time_ms: float
    tokens_per_sec: float
    sla_passed: bool

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "request_id": self.request_id,
            "suspect_id": self.suspect_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "ttft_ms": round(self.ttft_ms, 2),
            "generation_time_ms": round(self.generation_time_ms, 2),
            "tokens_per_sec": round(self.tokens_per_sec, 2),
            "sla_passed": self.sla_passed,
        }


class LatencyProfiler:
    """Measures streaming token latency, evaluates TTFT SLA, and exports benchmark logs."""

    def __init__(self, target_ttft_ms: float = DEFAULT_TTFT_SLA_MS) -> None:
        self.target_ttft_ms = target_ttft_ms
        self.records: list[TurnMetricRecord] = []

    def measure_stream(
        self,
        stream_generator: Iterator[str],
        model_id: str,
        prompt_tokens: int,
    ) -> tuple[str, GenerationMetrics]:
        start_time = time.perf_counter()
        first_token_time: float | None = None
        chunks: list[str] = []

        for chunk in stream_generator:
            if first_token_time is None and chunk:
                first_token_time = time.perf_counter()
            chunks.append(chunk)

        end_time = time.perf_counter()

        if first_token_time is None:
            first_token_time = end_time

        ttft_ms = (first_token_time - start_time) * 1000.0
        generation_ms = max(ttft_ms, (end_time - start_time) * 1000.0)

        full_content = "".join(chunks)
        completion_tokens = max(1, len(full_content.split()))

        metrics = GenerationMetrics(
            model_id=model_id,
            time_to_first_token_ms=round(ttft_ms, 2),
            generation_time_ms=round(generation_ms, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return full_content, metrics

    def record_turn(
        self,
        turn_id: int,
        request_id: str,
        suspect_id: str,
        metrics: GenerationMetrics,
    ) -> TurnMetricRecord:
        tokens_per_sec = 0.0
        if metrics.generation_time_ms > 0 and metrics.completion_tokens:
            tokens_per_sec = metrics.completion_tokens / (metrics.generation_time_ms / 1000.0)

        sla_passed = metrics.time_to_first_token_ms < self.target_ttft_ms

        record = TurnMetricRecord(
            turn_id=turn_id,
            request_id=request_id,
            suspect_id=suspect_id,
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=metrics.completion_tokens or 0,
            ttft_ms=metrics.time_to_first_token_ms,
            generation_time_ms=metrics.generation_time_ms,
            tokens_per_sec=tokens_per_sec,
            sla_passed=sla_passed,
        )
        self.records.append(record)
        return record

    def run_benchmark_suite(
        self,
        runner_fn: Callable[[int], tuple[str, GenerationMetrics]],
        total_turns: int = 50,
        request_prefix: str = "bench_req",
        suspect_id: str = "suspect_001",
    ) -> list[TurnMetricRecord]:
        results: list[TurnMetricRecord] = []
        for turn_idx in range(1, total_turns + 1):
            req_id = f"{request_prefix}_{turn_idx:03d}"
            _, metrics = runner_fn(turn_idx)
            record = self.record_turn(turn_idx, req_id, suspect_id, metrics)
            results.append(record)
        return results

    def summary(self) -> dict[str, Any]:
        if not self.records:
            return {"total_turns": 0, "pass_rate_pct": 0.0}

        ttft_values = [r.ttft_ms for r in self.records]
        throughput_values = [r.tokens_per_sec for r in self.records]
        passed_count = sum(1 for r in self.records if r.sla_passed)

        return {
            "total_turns": len(self.records),
            "passed_turns": passed_count,
            "pass_rate_pct": round((passed_count / len(self.records)) * 100.0, 2),
            "target_sla_ms": self.target_ttft_ms,
            "min_ttft_ms": round(min(ttft_values), 2),
            "mean_ttft_ms": round(statistics.mean(ttft_values), 2),
            "p95_ttft_ms": round(
                statistics.quantiles(ttft_values, n=20)[18] if len(ttft_values) >= 20 else max(ttft_values),
                2,
            ),
            "max_ttft_ms": round(max(ttft_values), 2),
            "mean_tokens_per_sec": round(statistics.mean(throughput_values), 2),
        }

    def export_csv(self, file_path: Path | str) -> None:
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "turn_id",
            "request_id",
            "suspect_id",
            "prompt_tokens",
            "completion_tokens",
            "ttft_ms",
            "generation_time_ms",
            "tokens_per_sec",
            "sla_passed",
        ]

        with target.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in self.records:
                writer.writerow(record.to_csv_row())
