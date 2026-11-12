# LLM Interrogation Pipeline & Telemetry Documentation

**Author:** Devansh Vinayak  
**Role:** Fact-ID Extraction, Telemetry & Quality Lead  
**Subsystem:** `backend/src/llm`, `backend/benchmarks`, `backend/tests`  
**Repository:** `D:\red_thread` (PR Fork: `D:\red_thread_fork`)  

---

## 1. Subsystem Mission & Scope

The `src/llm` subsystem serves as the mission-critical bridge between the Red Thread AI Detective game engine and local open-source Large Language Models (`Ollama` / `llama.cpp`):

1. **Guaranteed Factual Gating:** Enforces absolute narrative consistency by preventing suspects from referencing case facts or clues they are not authorized to know at the current game stage.
2. **Resilient Parsing:** Normalizes non-deterministic, messy LLM outputs (markdown blocks, chat preambles, plain text) into validated, schema-compliant `DialogueDraft` objects.
3. **Sub-800ms Latency SLA Verification:** Accurately instruments streaming sockets to measure Time to First Token (`ttft_ms`), end-to-end generation time, and token throughput.
4. **Auditable Telemetry & Visualization:** Produces structured CSV logs and interactive HTML visualizer dashboards for Sprint 2 quality audits.

---

## 2. Architecture & File Layout

```
backend/
├── src/
│   ├── progression/              # Stage gating & clue confrontation reactions
│   │   ├── authorization.py      # DialogueRequest generator (authorized_fact_ids)
│   │   └── evidence_reactions.py # Resolved suspect confrontation states
│   └── llm/                      # Devansh's Subsystem
│       ├── __init__.py           # Public module interface
│       ├── extractor.py          # FactExtractor, citation sanitizer & draft parser
│       └── profiler.py           # LatencyProfiler, TTFT measurement & SLA evaluator
├── benchmarks/
│   ├── run_latency_benchmark.py  # Live socket streaming runner (50 turns against Ollama)
│   ├── sprint2_benchmark_report.csv # 50-turn live GPU benchmark dataset
│   ├── visualize_performance.py # Telemetry statistics engine & CLI summary card
│   └── benchmark_visualizer.html # Interactive dark-mode Chart.js dashboard
├── tests/
│   ├── test_fact_extractor.py    # 7 unit tests (fences, think tags, sanitization)
│   ├── test_latency_profiler.py  # 3 unit tests (streaming mock, SLA thresholds)
│   └── test_benchmark_visualizer.py # 2 unit tests (metrics calculation, HTML report)
└── docs/
    └── llm_pipeline.md           # This comprehensive architecture and setup guide
```

---

## 3. Code Documentation

### 3.1. `FactExtractor` (`src/llm/extractor.py`)

Transforms raw string model responses into strict, typed `DialogueDraft` instances.

* **Multi-Strategy Cascade:**
  1. `exact_json`: Tries `json.loads()` directly on cleaned text.
  2. `markdown_fence`: Extracts JSON enclosed within ````json ... ```` or ```` ... ```` code blocks via regex ```` ```(?:json)?\s*(\{[\s\S]*?\})\s*``` ````.
  3. `enclosed_object`: Isolates the outermost JSON object bracketed between `{` and `}` when conversational preambles ("Sure, here is Kabir's response: {...}") are emitted.
  4. `fallback_regex`: Catches raw dialogue text when the model fails to output JSON entirely, extracting `"statement"` or using the cleaned text as dialogue.
* **Reasoning Tag Removal:** Automatically extracts and strips internal model thinking traces (`<think>...</think>`) emitted by reasoning-centric architectures (DeepSeek-R1, Qwen 2.5 thinking variants).
* **Citation Sanitization (`_sanitize_citations`):**
  - Cross-references model-cited `used_fact_ids` against `DialogueRequest.authorized_fact_ids`.
  - Cross-references `used_clue_ids` against `DialogueRequest.presented_clue_ids`.
  - Automatically drops any unauthorized or hallucinated IDs when `strip_unauthorized=True` (default), preventing game-breaking sequence breaks.
  - Raises `ValueError` when `strip_unauthorized=False` to assist strict offline regression evaluations.

### 3.2. `LatencyProfiler` (`src/llm/profiler.py`)

Instruments real-time token streams against the Sprint 2 sub-800ms SLA target.

* **High-Precision Monotonic Timing:** Uses Python's `time.perf_counter()` for sub-millisecond precision.
* **`measure_stream(stream_generator)`:**
  - Dispatches request timestamp `t_start`.
  - Measures Time to First Token (`ttft_ms = (t_first_chunk - t_start) * 1000`) on socket delivery of chunk 1.
  - Measures total generation duration (`generation_time_ms = (t_end - t_start) * 1000`).
  - Calculates decoding throughput (`tokens_per_sec = token_count / total_seconds`).
  - Evaluates SLA compliance (`sla_passed = ttft_ms < sla_threshold_ms`).
* **`record_turn(...)` & `export_csv(target_file)`:**
  - Persists structured metrics per turn into a standardized CSV schema:
    `turn_id, request_id, suspect_id, prompt_tokens, completion_tokens, ttft_ms, generation_time_ms, tokens_per_sec, sla_passed`.

### 3.3. `run_latency_benchmark.py` (`benchmarks/`)

A live inference runner that benchmarks local engine instances over HTTP sockets.

* **Health Verification (`check_engine_health`):** Verifies the engine is reachable and checks installed models via `/api/tags`.
* **Socket Streaming (`stream_ollama`):** Connects to `POST /api/generate` with `"stream": True` and yields chunks as they arrive across the TCP socket.
* **Warm-up Turn:** Issues turn 0 to compile CUDA kernels and populate model weights into VRAM before beginning recorded turns.
* **IPv4 Loopback Enforced:** Uses `http://127.0.0.1:11434` to prevent Windows IPv6 DNS resolution stalls.

### 3.4. `visualize_performance.py` (`benchmarks/`)

A standalone telemetry processor that requires zero external third-party Python packages.

* **Metric Calculations (`compute_summary_metrics`):** Computes Min, Mean, Median (P50), P90, P95, P99, Max, and SLA pass rates.
* **Terminal Summary Card (`print_cli_summary`):** Formats an ASCII dashboard for terminal feedback.
* **Interactive HTML Dashboard (`generate_html_report`):**
  - Generates `benchmark_visualizer.html` styled with the Red Thread cyber-noir dark UI.
  - Embeds interactive Chart.js graphs:
    1. **TTFT vs 800ms SLA Threshold:** Displays individual turns against a red dashed threshold.
    2. **Latency Breakdown:** Stacked bar chart of TTFT vs remaining generation time.
    3. **Token Generation Speed:** Real-time decoding throughput (tok/s).
    4. **Completion Tokens vs Duration:** Output scaling curve.
  - Interactive searchable, sortable data table for all 50 recorded turns.

---

## 4. Environment & Setup Guide

### 4.1. Prerequisites

* **Operating System:** Windows 10/11 (or Linux/macOS)
* **Python:** Python 3.10+ (tested and verified on **Python 3.12.0**)
* **Inference Engine:** [Ollama](https://ollama.ai) (or `llama-server.exe`)
* **Hardware:** NVIDIA GPU with 6GB+ VRAM recommended (tested on NVIDIA GeForce RTX 4050 Laptop GPU, 6GB GDDR6, CUDA 13.5). CPU mode is also supported.

### 4.2. Step-by-Step Setup

#### Step 1: Clone and Navigate to Backend

```powershell
cd D:\red_thread\backend
```

#### Step 2: Install Python Dependencies

The subsystem is intentionally designed with zero heavy dependencies:

```powershell
# Core dependency: pytest and pydantic
pip install pytest pydantic
```

#### Step 3: Install and Start Ollama

Ensure Ollama is running in your Windows system tray or start it manually:

```powershell
ollama serve
```

#### Step 4: Download Target Model

Pull the official 3B parameter model selected for Red Thread interrogation:

```powershell
ollama pull qwen2.5:3b
```

Verify model availability:

```powershell
ollama list
# Output should contain: qwen2.5:3b (3.1 GB)
```

> [!IMPORTANT]
> **Windows IPv6 Network Configuration Note:**  
> On Windows, connecting to `http://localhost:11434` can introduce an artificial ~2000ms delay in Python's `urllib` while the Windows socket resolver attempts IPv6 `::1` resolution before falling back to IPv4. Always use `http://127.0.0.1:11434` across all benchmark and profiling scripts.

---

## 5. Execution Commands & Verification

### 5.1. Run Automated Unit Tests (12 Tests)

From `D:\red_thread\backend`:

```powershell
python -m pytest tests/ -v
```

**Expected Result:**
```
tests/test_benchmark_visualizer.py::test_parse_benchmark_csv_and_compute_metrics PASSED
tests/test_benchmark_visualizer.py::test_generate_html_report_creates_valid_file PASSED
tests/test_fact_extractor.py::test_clean_json_extraction PASSED
tests/test_fact_extractor.py::test_markdown_fence_extraction PASSED
tests/test_fact_extractor.py::test_preamble_and_enclosed_json PASSED
tests/test_fact_extractor.py::test_stripping_think_tags PASSED
tests/test_fact_extractor.py::test_strips_unauthorized_facts_by_default PASSED
tests/test_fact_extractor.py::test_raises_error_when_strip_unauthorized_disabled PASSED
tests/test_fact_extractor.py::test_fallback_regex_on_plain_text PASSED
tests/test_latency_profiler.py::test_measure_stream PASSED
tests/test_latency_profiler.py::test_record_turn_sla_pass_and_fail PASSED
tests/test_latency_profiler.py::test_benchmark_suite_and_csv_export PASSED
============================= 12 passed in 0.33s =============================
```

### 5.2. Run 50-Turn Live Streaming Latency Benchmark

Execute the live benchmark against your running Ollama engine:

```powershell
python -m benchmarks.run_latency_benchmark --model qwen2.5:3b --turns 50 --output benchmarks/sprint2_benchmark_report.csv
```

### 5.3. Generate and View Performance Visualizer

Generate the dashboard and open it in your browser:

```powershell
# Print summary card and generate HTML
python -m benchmarks.visualize_performance

# Or generate and automatically launch in default browser:
python -m benchmarks.visualize_performance --open
```

File location: [benchmark_visualizer.html](file:///D:/red_thread/backend/benchmarks/benchmark_visualizer.html)

---

## 6. Phases to Reach the End Goal

Devansh's subsystem roadmap is divided into 5 structured phases:

```
[Phase 1: Multi-Strategy Parser] ──> [Phase 2: Socket Telemetry & SLA]
             │                                        │
             ▼                                        ▼
[Phase 3: Live GPU Benchmark]    ──> [Phase 4: Telemetry Visualizer]
             │                                        │
             └───────────────────┬────────────────────┘
                                 ▼
                     [Phase 5: Upstream Engine
                      Integration & PR Delivery]
```

### Phase 1: Contract Adherence & Multi-Strategy Parser (Completed)
* **Goal:** Parse LLM output into validated `DialogueDraft` without exceptions, strip thinking tags, and eliminate hallucinated fact IDs.
* **Deliverable:** `src/llm/extractor.py` and `tests/test_fact_extractor.py`.
* **Exit Criteria:** Zero parse failures across clean JSON, markdown code blocks, conversational preambles, and unformatted raw text.

### Phase 2: Socket Streaming Telemetry & SLA Profiler (Completed)
* **Goal:** Instrument streaming chunk responses with sub-millisecond precision, evaluate the `< 800ms` SLA threshold, and record structured telemetry.
* **Deliverable:** `src/llm/profiler.py` and `tests/test_latency_profiler.py`.
* **Exit Criteria:** Accurately calculates `ttft_ms`, `generation_time_ms`, and `tokens_per_sec`; exports standardized CSV schema.

### Phase 3: Live Hardware Benchmark & Engine Validation (Completed)
* **Goal:** Benchmark real inference with the target 3B model on consumer hardware to prove Sprint 2 viability.
* **Deliverable:** `benchmarks/run_latency_benchmark.py` and `benchmarks/sprint2_benchmark_report.csv`.
* **Measured Outcome:**
  - Evaluated on **Qwen2.5-3B-Instruct (Q4_K_M)** via Ollama on **NVIDIA GeForce RTX 4050 Laptop GPU**.
  - **Min TTFT:** `25.90 ms`
  - **Mean TTFT:** `45.96 ms` (Target SLA `< 800ms` -> **17.4x faster**)
  - **P95 TTFT:** `72.47 ms`
  - **Mean Throughput:** `30.92 tokens/sec`
  - **SLA Pass Rate:** **100.0% (50/50 turns)**

### Phase 4: Telemetry Visualization & Interactive Quality Dashboard (Completed)
* **Goal:** Provide developers and team leads with visual verification of system performance.
* **Deliverable:** `benchmarks/visualize_performance.py`, `benchmarks/benchmark_visualizer.html`, and `tests/test_benchmark_visualizer.py`.
* **Exit Criteria:** CLI summary table and interactive Chart.js graphs (TTFT vs SLA, latency breakdown, throughput, and token length correlation).

### Phase 5: Upstream Engine Integration & PR Delivery (Active Phase)
* **Goal:** Merge the extraction and telemetry subsystem into the main backend engine pipeline and submit the official Pull Request.
* **Sub-Tasks:**
  1. Synchronize all verified files to PR staging repository `D:\red_thread_fork`.
  2. Verify end-to-end integration with `src.progression.authorization` (`PreparedDialogueTurn`) and `case_data/case_001/progression.json`.
  3. Verify evidence confrontation mapping with `case_data/case_001/npc_knowledge.json`.
  4. Submit clean Pull Request from `D:\red_thread_fork` to upstream `D:\red_thread`.

---

## 7. Measured Telemetry Summary Table

| Metric | Measured Result (`qwen2.5:3b`) | Sprint 2 SLA Target | Status |
|---|---|---|:---:|
| **Evaluated Model** | `qwen2.5:3b` (Q4_K_M, 3.09B params) | 3B Parameter Class | **Compliant** |
| **Hardware** | NVIDIA GeForce RTX 4050 Laptop GPU (6GB VRAM) | Consumer Hardware | **Compliant** |
| **Inference Engine** | Local Ollama (`127.0.0.1:11434`) | Local Engine | **Compliant** |
| **Sample Size** | **50 Live Consecutive Turns** | 50 Turns | **Complete** |
| **SLA Pass Rate** | **100.0% (50 / 50)** | &ge; 95.0% | **PASSED** |
| **Min TTFT** | **25.90 ms** | &lt; 800.0 ms | **PASSED** |
| **Mean TTFT** | **45.96 ms** | &lt; 800.0 ms | **PASSED** |
| **P95 TTFT** | **72.47 ms** | &lt; 800.0 ms | **PASSED** |
| **Max TTFT (Cold Start)** | **217.19 ms** | &lt; 800.0 ms | **PASSED** |
| **Mean Throughput** | **30.92 tokens/sec** | &gt; 20 tokens/sec | **PASSED** |
| **Mean Generation Time** | **611.89 ms** | &mdash; | **Optimal** |
| **Parsing Robustness** | **100% (46 exact_json, 4 fallback_regex)** | Zero Unhandled Crashes | **PASSED** |
