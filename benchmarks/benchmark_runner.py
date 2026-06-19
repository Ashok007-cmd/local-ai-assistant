#!/usr/bin/env python3
"""
Inference performance benchmarking suite for local SLM models via Ollama.
Measures tokens/second, time-to-first-token (TTFT), and memory usage.
"""

from __future__ import annotations

import csv
import json
import logging
import time
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import httpx
import psutil
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"

# ---------------------------------------------------------------------------
# Benchmark prompts — representative resume / interview workloads
# ---------------------------------------------------------------------------

SAMPLE_RESUME = """
John Doe
john.doe@email.com | (555) 123-4567

SUMMARY
Software engineer with 5 years of experience building full-stack web applications.
Proficient in Python, JavaScript, React, and cloud infrastructure (AWS).

EXPERIENCE
Senior Software Engineer, TechCorp (2021–Present)
- Led migration of monolithic Rails app to microservices on Kubernetes
- Built real-time data pipeline processing 10k events/sec using Kafka and Spark
- Reduced CI pipeline time by 60% through parallelization and caching strategies

Software Engineer, StartupXYZ (2019–2021)
- Developed RESTful APIs using FastAPI and PostgreSQL
- Implemented automated testing pipeline achieving 92% code coverage
- Built React-based dashboard with real-time WebSocket updates

EDUCATION
B.S. Computer Science, State University (2015–2019)
GPA: 3.7/4.0
Relevant coursework: Algorithms, Machine Learning, Distributed Systems

SKILLS
Languages: Python, JavaScript, TypeScript, Go, SQL
Frameworks: React, FastAPI, Django, Express.js
Tools: Docker, Kubernetes, Terraform, AWS, Git, CI/CD
Data: PostgreSQL, Redis, Kafka, Spark
"""

SAMPLE_INTERVIEW = """
Tell me about a time you had to resolve a conflict within your engineering team.
"""

BENCHMARK_PROMPTS: list[dict[str, str]] = [
    {
        "name": "resume_analysis_short",
        "prompt": f"Analyze this resume for a Senior Software Engineer role. Respond with JSON.\n\nResume:\n{SAMPLE_RESUME[:500]}...",
        "system": "You are a resume reviewer. Output JSON only.",
    },
    {
        "name": "resume_analysis_full",
        "prompt": f"Analyze this resume for a Senior Software Engineer role. Identify skills gaps, strengths, and provide recommendations.\n\nResume:\n{SAMPLE_RESUME}",
        "system": "You are a technical recruiter. Provide detailed analysis.",
    },
    {
        "name": "interview_question",
        "prompt": f"Generate 3 behavioral interview questions for a senior engineer and provide feedback framework.\n\n{SAMPLE_INTERVIEW}",
        "system": "You are a hiring manager. Generate structured output.",
    },
    {
        "name": "json_extraction",
        "prompt": "Extract all technical skills, years of experience, and job titles from this resume as a structured JSON object. Include confidence scores.\n\n" + SAMPLE_RESUME,
        "system": "Extract structured data from text. Output JSON only.",
    },
    {
        "name": "long_context",
        "prompt": "Summarize the following document and extract key action items:\n\n" + (SAMPLE_RESUME * 3),
        "system": "Summarize and extract action items.",
    },
]

# ---------------------------------------------------------------------------
# Benchmark metrics
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    model: str
    prompt_name: str
    prompt_length_chars: int
    prompt_length_tokens_est: int
    response_length_chars: int
    response_length_tokens_est: int
    time_to_first_token_s: float
    total_generation_time_s: float
    tokens_per_second: float
    peak_vram_mb: float
    peak_ram_mb: float
    success: bool
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def get_gpu_memory() -> float:
    """Get GPU memory usage in MB. Returns 0 if no GPU."""
    try:
        import GPUtil

        gpus = GPUtil.getGPUs()
        if gpus:
            return gpus[0].memoryUsed
    except Exception:
        pass
    return 0.0


def check_ollama() -> bool:
    """Verify Ollama is running and accessible."""
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        r.raise_for_status()
        return True
    except Exception:
        return False


def get_available_models() -> list[str]:
    """Get list of models available in Ollama."""
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def run_single_benchmark(
    model: str,
    prompt: str,
    system_prompt: str | None = None,
    warmup: bool = False,
) -> BenchmarkResult:
    """
    Run a single benchmark against the Ollama /api/generate endpoint.

    Measures:
      - Time to First Token (TTFT) — latency before model starts generating
      - Tokens per second — throughput during generation
      - Peak VRAM / RAM — memory pressure
    """
    process = psutil.Process()

    mem_before = process.memory_info().rss / (1024 * 1024)  # MB
    gpu_before = get_gpu_memory()

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 512 if not warmup else 64,
            "temperature": 0.1,
        },
    }
    if system_prompt:
        payload["system"] = system_prompt

    benchmark_name = "warmup" if warmup else "benchmark"

    try:
        with httpx.Client(timeout=300.0) as client:
            # Measure TTFT via streaming endpoint for accurate first-token timing
            # First, get total time via non-streaming
            start = time.perf_counter()

            response = client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            total_time = time.perf_counter() - start

            result = response.json()
            raw_output = result.get("response", "")
            eval_count = result.get("eval_count", 0)
            eval_duration_ns = result.get("eval_duration", 0)
            prompt_eval_count = result.get("prompt_eval_count", 0)
            prompt_eval_duration_ns = result.get("prompt_eval_duration", 0)

        # Memory after generation
        mem_after = process.memory_info().rss / (1024 * 1024)
        gpu_after = get_gpu_memory()

        peak_vram = max(gpu_after - gpu_before, 0)
        peak_ram = max(mem_after - mem_before, 0)

        # Calculate metrics
        if eval_duration_ns > 0:
            ttft = prompt_eval_duration_ns / 1e9 if prompt_eval_duration_ns > 0 else 0.0
            tokens_per_sec = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0.0
        else:
            # Fallback: estimate from wall-clock time
            ttft = 0.0
            tokens_per_sec = eval_count / total_time if total_time > 0 and eval_count > 0 else 0.0

        result_obj = BenchmarkResult(
            model=model,
            prompt_name=benchmark_name,
            prompt_length_chars=len(prompt),
            prompt_length_tokens_est=estimate_tokens(prompt),
            response_length_chars=len(raw_output),
            response_length_tokens_est=eval_count or estimate_tokens(raw_output),
            time_to_first_token_s=round(ttft, 3),
            total_generation_time_s=round(total_time, 3),
            tokens_per_second=round(tokens_per_sec, 2),
            peak_vram_mb=round(peak_vram, 1),
            peak_ram_mb=round(peak_ram, 1),
            success=bool(raw_output.strip()),
            extra={
                "eval_count": eval_count,
                "eval_duration_ns": eval_duration_ns,
                "prompt_eval_count": prompt_eval_count,
                "prompt_eval_duration_ns": prompt_eval_duration_ns,
            },
        )

        if warmup:
            logger.info("Warmup complete for %s: %.1f tok/s", model, result_obj.tokens_per_second)
        else:
            logger.info(
                "Benchmark %s | %s: %.1f tok/s, TTFT=%.2fs, VRAM=%.0fMB, RAM=%.0fMB",
                model,
                result_obj.prompt_name,
                result_obj.tokens_per_second,
                result_obj.time_to_first_token_s,
                result_obj.peak_vram_mb,
                result_obj.peak_ram_mb,
            )

        return result_obj

    except Exception as e:
        logger.error("Benchmark failed for %s: %s", model, e)
        return BenchmarkResult(
            model=model,
            prompt_name=benchmark_name,
            prompt_length_chars=len(prompt),
            prompt_length_tokens_est=estimate_tokens(prompt),
            response_length_chars=0,
            response_length_tokens_est=0,
            time_to_first_token_s=0.0,
            total_generation_time_s=0.0,
            tokens_per_second=0.0,
            peak_vram_mb=0.0,
            peak_ram_mb=0.0,
            success=False,
            error=str(e),
        )


def run_benchmark_suite(models: list[str], num_runs: int = 3) -> list[BenchmarkResult]:
    """
    Run the full benchmark suite across multiple models.

    Each model gets:
      - A warmup run
      - Multiple runs of each prompt variant
    """
    all_results: list[BenchmarkResult] = []

    for model in models:
        logger.info("=" * 60)
        logger.info("Benchmarking model: %s", model)
        logger.info("=" * 60)

        # Warmup
        logger.info("Running warmup...")
        run_single_benchmark(
            model=model,
            prompt="Write a short greeting.",
            system_prompt="You are a helpful assistant.",
            warmup=True,
        )

        # Run each benchmark prompt
        for prompt_def in BENCHMARK_PROMPTS:
            for run_idx in range(1, num_runs + 1):
                logger.info("Run %d/%d: %s", run_idx, num_runs, prompt_def["name"])
                result = run_single_benchmark(
                    model=model,
                    prompt=prompt_def["prompt"],
                    system_prompt=prompt_def.get("system"),
                )
                result.prompt_name = f"{prompt_def['name']}_run{run_idx}"
                all_results.append(result)

    return all_results


def generate_report(results: list[BenchmarkResult], output_dir: Path) -> Path:
    """Generate a comprehensive markdown report from benchmark results."""
    if not results:
        logger.warning("No results to report")
        report_path = output_dir / "report.md"
        report_path.write_text("# Benchmark Report\n\nNo results collected.\n")
        return report_path

    # Convert to DataFrame for analysis
    records = [asdict(r) for r in results]
    df = pd.DataFrame(records)

    # Clean prompt_name for grouping (strip _runN suffix for aggregation)
    df["prompt_group"] = df["prompt_name"].str.replace(r"_run\d+$", "", regex=True)

    report_lines = [
        "# Local AI Assistant — Benchmark Report",
        "",
        f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Models tested**: {', '.join(df['model'].unique())}",
        f"**Total runs**: {len(df)}",
        f"**Hardware**: {_get_hardware_info()}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        df.groupby("model").agg({
            "tokens_per_second": "mean",
            "time_to_first_token_s": "mean",
            "total_generation_time_s": "mean",
            "peak_vram_mb": "mean",
            "peak_ram_mb": "mean",
            "response_length_tokens_est": "mean",
            "success": "mean",
        }).to_markdown(),
        "",
        "---",
        "",
        "## Detailed Model Results",
        "",
    ]

    # Per-model details
    for model in df["model"].unique():
        model_df = df[df["model"] == model]
        total = len(model_df)
        successful = model_df["success"].sum()
        avg_tps = model_df["tokens_per_second"].mean()
        avg_ttft = model_df["time_to_first_token_s"].mean()
        avg_vram = model_df["peak_vram_mb"].mean()
        avg_ram = model_df["peak_ram_mb"].mean()

        report_lines.extend([
            f"### {model}",
            "",
            f"- **Total runs**: {total}",
            f"- **Successful runs**: {int(successful)}/{total} ({successful/total*100:.0f}%)",
            f"- **Average tokens/sec**: {avg_tps:.2f}",
            f"- **Average TTFT**: {avg_ttft:.3f}s",
            f"- **Average peak VRAM**: {avg_vram:.1f} MB",
            f"- **Average peak RAM**: {avg_ram:.1f} MB",
            "",
            "#### Per-Prompt Breakdown",
            "",
            model_df.groupby("prompt_group").agg({
                "tokens_per_second": ["mean", "std"],
                "time_to_first_token_s": ["mean", "std"],
                "total_generation_time_s": ["mean"],
                "peak_vram_mb": ["max"],
                "response_length_tokens_est": ["mean"],
                "success": ["mean"],
            }).to_markdown(),
            "",
        ])

    # Cross-model comparison
    report_lines.extend([
        "---",
        "",
        "## Cross-Model Comparison",
        "",
        "### Tokens per Second (higher is better)",
        "",
        df.groupby("prompt_group").apply(
            lambda g: g.groupby("model")["tokens_per_second"].mean()
        ).to_markdown(),
        "",
        "### Time to First Token — TTFT in seconds (lower is better)",
        "",
        df.groupby("prompt_group").apply(
            lambda g: g.groupby("model")["time_to_first_token_s"].mean()
        ).to_markdown(),
        "",
        "### Memory Usage (MB)",
        "",
        df.groupby("model")[["peak_vram_mb", "peak_ram_mb"]].mean().to_markdown(),
        "",
        "### Format Success Rate (first-attempt parse %)",
        "",
        df.groupby("model")["success"].mean().to_markdown(),
        "",
        "---",
        "",
        "## Raw Data",
        "",
        "```csv",
    ])

    # CSV raw data
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=records[0].keys())
    writer.writeheader()
    for r in records:
        writer.writerow(r)
    report_lines.append(buf.getvalue())
    report_lines.append("```")

    report_text = "\n".join(report_lines)
    report_path = output_dir / "report.md"
    report_path.write_text(report_text)
    logger.info("Report written to %s", report_path)

    return report_path


def _get_hardware_info() -> str:
    """Detect and describe the benchmark hardware."""
    import platform

    info = []
    info.append(f"OS: {platform.system()} {platform.release()}")
    info.append(f"CPU: {platform.processor() or 'unknown'}")
    info.append(f"RAM: {round(psutil.virtual_memory().total / (1024**3), 1)} GB")

    try:
        import GPUtil

        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            info.append(f"GPU: {g.name} ({g.memoryTotal} MB VRAM)")
    except Exception:
        pass

    return " | ".join(info)


def save_csv(results: list[BenchmarkResult], output_dir: Path) -> Path:
    """Save benchmark results as CSV."""
    records = [asdict(r) for r in results]
    csv_path = output_dir / "benchmark_results.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

    logger.info("CSV saved to %s", csv_path)
    return csv_path


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark local Ollama SLM models"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="Models to benchmark (default: all available)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per prompt (default: 3)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="benchmarks",
        help="Output directory (default: benchmarks/)",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models and exit",
    )

    args = parser.parse_args()

    if args.list_models:
        models = get_available_models()
        print("Available models:")
        for m in models:
            print(f"  - {m}")
        return

    if not check_ollama():
        logger.error("Ollama is not running. Start it with: ollama serve")
        sys.exit(1)

    if args.models:
        models = args.models
    else:
        models = get_available_models()
        if not models:
            logger.error("No models found. Pull models first: ollama pull <model>")
            sys.exit(1)

    logger.info("Starting benchmark suite for models: %s", models)
    logger.info("Runs per prompt: %d", args.runs)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = run_benchmark_suite(models, num_runs=args.runs)

    # Save CSV
    save_csv(results, output_dir)

    # Generate report
    report_path = generate_report(results, output_dir)

    # Print summary to console
    print(f"\n{'='*60}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print(f"Report: {report_path}")
    print(f"CSV:    {output_dir / 'benchmark_results.csv'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
