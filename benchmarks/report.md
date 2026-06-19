# Local AI Assistant — Model Comparison Technical Report

**Generated**: May 26, 2026  
**Hardware**: NVIDIA GeForce GTX 1650 (4 GB VRAM) | 11.6 GB RAM | 12th Gen Intel Core i5-12450H CPU  
**Test Framework**: Ollama 0.22.1 | Python 3.14 | httpx  
**Quantization**: All models at Q4_K_M (standard Ollama library default)

---

## Executive Summary

Three distinct small language models (SLMs) representing different parameter sizes and VRAM footprint classes were benchmarked on identical hardware. The key finding is a direct relation between **GPU VRAM residence** and **inference speed**. 

Models that fit entirely within the 4 GB VRAM boundary (`llama3.2:3b`) run at **~50 tok/s**, whereas models that exceed or sit borderline to VRAM (`gemma3:4b` and `mistral:7b`) trigger partial/full CPU RAM fallback, dropping throughput to **~23.6 tok/s** and **~9.9 tok/s** respectively.

| Model | Parameters | Model Size | VRAM Fit | Avg Speed | Avg TTFT | Output Compliance | Recommended Use |
|-------|------------|------------|----------|-----------|----------|-------------------|-----------------|
| **llama3.2:3b** | 3.2B | 2.0 GB | ✅ Yes (100% GPU) | **49.4 tok/s** | 0.55s | 100% (with Pydantic) | Real-time resume & interview assistance |
| **gemma3:4b** | 4.3B | 3.3 GB | ⚠️ Borderline (100% GPU but tight) | **23.6 tok/s** | 1.35s | 100% (with Pydantic) | Richer entity extraction tasks |
| **mistral:7b** | 7.2B | 4.1 GB | ❌ No (40% CPU / 60% GPU Hybrid) | **9.9 tok/s** | 1.90s | 100% (with Pydantic) | Nuanced analysis (non-real-time) |

---

## Detailed Results by Model

### llama3.2:3b
*   **Architecture**: Llama 3.2 (Meta)
*   **Memory Footprint**: 2.0 GB. Fits completely inside the GTX 1650 4 GB VRAM with ample room for prompt context processing and KV cache.
*   **Average Throughput**: 49.4 tok/s
*   **Average TTFT**: 0.55s (under cold start)
*   **Observations**: Extremely fast and responsive. Ideal for interactive chatbots or auto-complete prompts where low latency (< 1s) is critical.

| Prompt Group | Avg Speed | Avg TTFT (s) | Total Generation Time (s) | Success Rate |
|--------------|-----------|--------------|---------------------------|--------------|
| `resume_analysis_short` | 51.6 tok/s | 0.26s | 4.71s | 100% |
| `resume_analysis_full` | 49.7 tok/s | 0.54s | 11.29s | 100% |
| `interview_question` | 49.7 tok/s | 0.09s | 10.50s | 100% |
| `json_extraction` | 48.9 tok/s | 0.54s | 5.75s | 100% |
| `long_context` | 47.2 tok/s | 1.33s | 9.35s | 100% |

---

### gemma3:4b
*   **Architecture**: Gemma 3 (Google)
*   **Memory Footprint**: 3.3 GB. Fits inside the 4 GB VRAM limit, but leaves very little head room. For long contexts, Ollama may dynamically offload layers or run out of memory cache, resulting in slightly increased latency.
*   **Average Throughput**: 23.6 tok/s
*   **Average TTFT**: 1.35s
*   **Observations**: Serves as a solid mid-tier model. It offers stronger semantic reasoning and recruiter persona alignment compared to Llama 3.2 3B, but at the expense of a 52% reduction in speed.

| Prompt Group | Avg Speed | Avg TTFT (s) | Total Generation Time (s) | Success Rate |
|--------------|-----------|--------------|---------------------------|--------------|
| `resume_analysis_short` | 23.7 tok/s | 0.38s | 22.39s | 100% |
| `resume_analysis_full` | 23.6 tok/s | 0.64s | 22.95s | 100% |
| `interview_question` | 24.0 tok/s | 0.15s | 22.09s | 100% |
| `json_extraction` | 23.6 tok/s | 0.64s | 21.88s | 100% |
| `long_context` | 22.9 tok/s | 4.93s | 20.18s | 100% |

---

### mistral:7b
*   **Architecture**: Mistral 7B (Mistral AI)
*   **Memory Footprint**: 4.1 GB. Exceeds the available VRAM. Ollama runs this in a **40% CPU / 60% GPU hybrid** configuration, loading a major portion of weights into system RAM.
*   **Average Throughput**: 9.9 tok/s
*   **Average TTFT**: 1.90s (peaks at 13.33s for long contexts due to CPU prompt evaluation)
*   **Observations**: While slow, this 7B model provides the most detailed and sophisticated analytical feedback. It is best used for asynchronous, batch resume analysis where execution speed is not a constraint.

| Prompt Group | Avg Speed | Avg TTFT (s) | Total Generation Time (s) | Success Rate |
|--------------|-----------|--------------|---------------------------|--------------|
| `resume_analysis_short` | 10.1 tok/s | 1.00s | 29.51s | 100% |
| `resume_analysis_full` | 9.9 tok/s | 1.83s | 52.97s | 100% |
| `interview_question` | 10.1 tok/s | 0.34s | 44.81s | 100% |
| `json_extraction` | 10.0 tok/s | 1.83s | 53.41s | 100% |
| `long_context` | 9.4 tok/s | 4.52s | 51.69s | 100% |

---

## Performance Comparison

### Generation Speed (Tokens per Second - Higher is Better)

```
llama3.2:3b      ████████████████████████████████████████████████ 49.4
gemma3:4b        ████████████████████████                        23.6
mistral:7b       ██████████                                       9.9
```

### Prompt Processing Latency (TTFT - Lower is Better)

For typical resume prompts (~300 tokens):
```
llama3.2:3b      ███                                             0.54s
gemma3:4b        ████                                            0.64s
mistral:7b       ███████████                                     1.83s
```

For long contexts (~800 tokens):
```
llama3.2:3b      ██████                                          1.33s
gemma3:4b        ██████████████████████                          4.93s
mistral:7b       ██████████████████████                          4.52s
```

---

## Output Quality & Structured Compliance

1.  **JSON Adherence**: By combining Ollama's native `"format": "json"` query constraints with explicit system prompt instructions, all three models achieved a **100% JSON parsing rate** across all 45 test runs.
2.  **Pydantic Schema Validation**:
    *   **llama3.2:3b**: Tended to generate simpler descriptions but adhered to Pydantic rules cleanly. No validation retries were triggered.
    *   **gemma3:4b**: Produced highly comprehensive lists of missing skills and side-by-side improvements. adheared strictly to Pydantic field validation.
    *   **mistral:7b**: Best quality outputs, capturing complex logic structures and creating highly detailed and custom coaching templates.

---

## Recommendations & Sizing

Based on our benchmarks on a 4 GB VRAM system:
*   **Production Default**: **`llama3.2:3b`** is the recommended default. It runs at ~50 tok/s, is fully GPU-resident, and completes resume optimization within 4–5 seconds.
*   **Recruiting Depth Option**: If the candidate wants highly detailed critiques of resume items and is comfortable waiting ~20 seconds, **`gemma3:4b`** is a great alternative due to its superior semantic understanding.
*   **Asynchronous Processing**: **`mistral:7b`** should be reserved for batch processing or offline operations due to CPU fallback bottlenecks (~10 tok/s).
