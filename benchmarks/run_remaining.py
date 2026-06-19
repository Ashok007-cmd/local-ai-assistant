#!/usr/bin/env python3
"""Run benchmarks for remaining models with VRAM-aware prompt sizes."""
import sys, csv, logging, json
from dataclasses import asdict
sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

from benchmarks.benchmark_runner import run_single_benchmark

# Shorter prompt variants for models with limited VRAM
SHORT_RESUME = """
John Doe, Senior Software Engineer with 5 years experience.
Skills: Python, JavaScript, React, Docker, Kubernetes, AWS.
Led migration to microservices, built data pipelines.
"""

BENCHMARK_PROMPTS = [
    {
        "name": "resume_short",
        "prompt": f"Analyze resume for Senior Engineer role. Output JSON with skills matching score.\n\nResume:\n{SHORT_RESUME}",
        "system": "You are a resume reviewer. Output JSON only.",
    },
    {
        "name": "resume_medium",
        "prompt": f"Analyze this resume for Senior Engineer. Identify top 3 skill gaps and provide matching score.\n\nResume:\n{SHORT_RESUME * 3}",
        "system": "You are a technical recruiter.",
    },
    {
        "name": "interview",
        "prompt": "Generate 2 interview questions for a senior engineer candidate. Include question type and difficulty.",
        "system": "You are a hiring manager.",
    },
    {
        "name": "json_extract",
        "prompt": f"Extract skills, years of experience, and job titles from this resume as JSON.\n\n{SHORT_RESUME}",
        "system": "Extract structured data. JSON only.",
    },
]

MODELS = [
    "gemma3:4b",
    "phi4-mini",
    "qwen2.5:7b",
    "mistral:7b",
]

for model in MODELS:
    logger.info("=" * 50)
    logger.info("Benchmarking: %s", model)
    logger.info("=" * 50)

    # Warmup
    logger.info("Warmup...")
    run_single_benchmark(model=model, prompt="Hello.", warmup=True)

    results = []
    for pdef in BENCHMARK_PROMPTS:
        for run_idx in range(1, 4):
            logger.info("  Run %d/3: %s", run_idx, pdef["name"])
            try:
                result = run_single_benchmark(
                    model=model,
                    prompt=pdef["prompt"],
                    system_prompt=pdef.get("system"),
                )
                result.prompt_name = f'{pdef["name"]}_run{run_idx}'
                results.append(result)
            except Exception as e:
                logger.error("  Failed: %s", e)

    safe_name = model.replace(":", "_").replace(".", "_")
    csv_path = f"benchmarks/results_{safe_name}.csv"
    with open(csv_path, "w", newline="") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=asdict(results[0]).keys())
            writer.writeheader()
            writer.writerows(asdict(r) for r in results)

    ok = sum(1 for r in results if r.success)
    total = len(results)
    avg_tps = sum(r.tokens_per_second for r in results if r.success) / max(ok, 1)
    logger.info("Model %s: %d/%d ok, avg %.1f tok/s", model, ok, total, avg_tps)
    logger.info("Saved to %s", csv_path)

logger.info("=" * 50)
logger.info("All remaining models done!")
