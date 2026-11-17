import tempfile
from pathlib import Path

import pytest
from benchmarks.visualize_performance import (
    compute_summary_metrics,
    generate_html_report,
    parse_benchmark_csv,
)


def test_parse_benchmark_csv_and_compute_metrics():
    sample_csv_content = """turn_id,request_id,suspect_id,prompt_tokens,completion_tokens,ttft_ms,generation_time_ms,tokens_per_sec,sla_passed
1,req_001,suspect_001,42,20,150.00,500.00,40.00,True
2,req_002,suspect_001,42,15,50.00,400.00,37.50,True
3,req_003,suspect_001,42,25,850.00,1000.00,25.00,False
"""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(sample_csv_content)
        temp_csv_path = Path(f.name)

    try:
        records = parse_benchmark_csv(temp_csv_path)
        assert len(records) == 3
        assert records[0]["turn_id"] == 1
        assert records[0]["sla_passed"] is True
        assert records[2]["sla_passed"] is False

        metrics = compute_summary_metrics(records, sla_threshold_ms=800.0)
        assert metrics["total_turns"] == 3
        assert metrics["sla_passed_count"] == 2
        assert metrics["sla_pass_rate"] == pytest.approx(66.67, rel=1e-2)
        assert metrics["ttft_ms"]["min"] == 50.00
        assert metrics["ttft_ms"]["max"] == 850.00
        assert metrics["tokens_per_sec"]["mean"] == pytest.approx(34.17, rel=1e-2)
    finally:
        if temp_csv_path.exists():
            temp_csv_path.unlink()


def test_generate_html_report_creates_valid_file():
    records = [
        {
            "turn_id": 1,
            "request_id": "test_req_001",
            "suspect_id": "kabir",
            "prompt_tokens": 40,
            "completion_tokens": 20,
            "ttft_ms": 45.5,
            "generation_time_ms": 600.0,
            "tokens_per_sec": 33.3,
            "sla_passed": True,
        }
    ]
    metrics = compute_summary_metrics(records)

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        temp_html_path = Path(f.name)

    try:
        saved_file = generate_html_report(records, metrics, temp_html_path, model_name="qwen2.5:3b")
        assert saved_file.exists()
        content = saved_file.read_text(encoding="utf-8")
        assert "Red Thread AI Detective" in content
        assert "qwen2.5:3b" in content
        assert "45.5" in content
        assert "100.0" in content
        assert "<canvas id=\"ttftChart\">" in content
    finally:
        if temp_html_path.exists():
            temp_html_path.unlink()
