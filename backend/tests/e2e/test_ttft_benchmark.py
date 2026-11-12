import pytest
import time
import ollama
import statistics

# ---------------------------------------------------------
# 1. CONFIGURATION 
# ---------------------------------------------------------
MODEL_NAME = "qwen3:1.7b"
NUM_RUNS = 10  # 10 times test should run and then find  p50 aur p95

# ---------------------------------------------------------
# 2. TEST (TTFT Benchmark)
# ---------------------------------------------------------

@pytest.mark.e2e
def test_ttft_warm_model_benchmark():
    print(f"\n--- Starting TTFT Benchmark for {MODEL_NAME} ---")
    ttft_times = []

    for i in range(NUM_RUNS):
        # Simple prompt force the model to think        
        messages = [{"role": "user", "content": "Say 'Hello'."}]
        
        start_time = time.perf_counter()
        
        try:
            # 1. Model call with stream=True (Mandatory for TTFT)
            # 2. think=False (Mandatory: otherwise thinking mode will increase latency )
            response_stream = ollama.chat(
                model=MODEL_NAME,
                messages=messages,
                stream=True,
                options={"think": False} 
            )
            
            # 3. Stream se pehla token get
            first_chunk = next(response_stream)
            end_time = time.perf_counter()
            
            # 4. measure TTFT  (milliseconds)
            ttft_ms = (end_time - start_time) * 1000
            ttft_times.append(ttft_ms)
            print(f"Run {i+1}: TTFT = {ttft_ms:.2f} ms")
            
        except Exception as e:
            pytest.fail(f"LLM call failed: {e}")

    # ---------------------------------------------------------
    # 3. REPORTING ( p50 aur p95 report )
    # ---------------------------------------------------------
    ttft_times.sort()
    p50 = statistics.median(ttft_times) # Median (50th percentile)
    
    # p95 
    p95_index = int(len(ttft_times) * 0.95)
    p95 = ttft_times[p95_index] if p95_index < len(ttft_times) else ttft_times[-1]
    
    print("\n--- TTFT BENCHMARK RESULTS ---")
    print(f"Model: {MODEL_NAME}")
    print(f"Runs: {NUM_RUNS}")
    print(f"p50 (Median) TTFT: {p50:.2f} ms")
    print(f"p95 (Max) TTFT:    {p95:.2f} ms")
    print("------------------------------")
    
    # we will not fail the test only check if measurement is done
    assert p50 > 0, "TTFT measurement failed (p50 is zero)."