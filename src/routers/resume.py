from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.assistant import default_resume_fallback
from src.auth import verify_api_key
from src.config import settings
from src.models import ResumeAnalysisResult
from src.routers._client import get_llm_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["resume"], dependencies=[Depends(verify_api_key)])

class AnalyzeResumeRequest(BaseModel):
    resume_text: str = Field(..., min_length=50, max_length=100_000)
    target_role: str = Field(..., min_length=2, max_length=200)
    model: str = Field(default=settings.DEFAULT_MODEL, description="Ollama model name")
    language: str = Field(default="english", description="Preferred output language")


@router.post("/analyze-resume")
async def analyze_resume(req: AnalyzeResumeRequest):
    """
    Analyze a resume against a target role asynchronously.

    Returns structured skill analysis including gaps, matching score,
    and bullet-point improvements, localized in the preferred language.
    """
    client = get_llm_client(req.model)

    prompt = (
        f"Analyze this resume for a {req.target_role} position.\n\n"
        f"Resume:\n{req.resume_text}\n\n"
        "Provide a detailed ResumeAnalysisResult with:\n"
        "- candidate_name (extract if present)\n"
        "- target_role\n"
        "- years_experience (estimate if possible)\n"
        "- skill_analysis with missing skills, matching_score (0-100), bullet_point_improvements, and strengths\n"
        "- format_issues\n"
        "- overall_recommendation"
    )

    system_prompt = (
        f"You are a senior HR tech recruiter specializing in {req.target_role} roles. "
        "Analyze the resume carefully and produce a structured JSON output. "
        "Be specific and actionable in your feedback. "
        f"You MUST write all textual feedback (descriptions, strengths, missing skills importance, "
        f"bullet point rewrites rationale, format issues, and overall recommendation) "
        f"EXCLUSIVELY in the following language: {req.language}."
    )

    result = await client.generate_structured_async(
        prompt=prompt,
        schema=ResumeAnalysisResult,
        system_prompt=system_prompt,
        fallback_factory=default_resume_fallback,
    )

    return {
        "success": result.success,
        "model": req.model,
        "attempts": result.attempts,
        "errors": result.errors,
        "data": result.data.model_dump() if result.data else None,
    }
