"""
Pydantic schemas for structured LLM output validation.
Used for resume optimization and mock interview workflows.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SkillCategory(str, Enum):
    TECHNICAL = "technical"
    SOFT_SKILL = "soft_skill"
    DOMAIN = "domain"
    CERTIFICATION = "certification"
    LANGUAGE = "language"


class SkillGap(BaseModel):
    """A single identified skill gap."""

    skill_name: str = Field(..., description="Name of the missing or underdeveloped skill")
    category: SkillCategory = Field(..., description="Category of the skill")
    importance: str = Field(
        ..., description="How critical this skill is for the target role"
    )
    suggested_resource: Optional[str] = Field(
        None, description="Suggested learning resource or course"
    )


class BulletPointImprovement(BaseModel):
    """Improvement suggestion for a single resume bullet point."""

    original: str = Field(..., description="Original bullet point from the resume")
    improved: str = Field(..., description="Rewritten, stronger bullet point")
    rationale: str = Field(
        ..., description="Explanation of what makes the improved version better"
    )


class SkillAnalysis(BaseModel):
    """Structured analysis of skills from a resume."""

    missing_skills: List[SkillGap] = Field(
        ..., description="Skills missing or underdeveloped for the target role"
    )
    matching_score: float = Field(
        ..., ge=0.0, le=100.0, description="Overall match score (0–100)"
    )
    bullet_point_improvements: List[BulletPointImprovement] = Field(
        ..., description="Suggested improvements for specific bullet points"
    )
    strengths: List[str] = Field(
        ..., description="Key strengths identified in the resume"
    )

    @field_validator("matching_score")
    @classmethod
    def score_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"matching_score must be between 0 and 100, got {v}")
        return round(v, 1)

    def model_dump_json_safe(self) -> str:
        """Serialize to JSON, ensuring no precision or encoding issues."""
        return self.model_dump_json(indent=2)


class InterviewQuestion(BaseModel):
    """A single interview question with classification."""

    question: str = Field(..., description="The interview question text")
    question_type: str = Field(
        ..., description="Type: behavioral | technical | situational | STAR"
    )
    difficulty: str = Field(..., description="Difficulty: easy | medium | hard")
    target_skill: str = Field(
        ..., description="The skill or competency this question targets"
    )
    ideal_answer_keywords: List[str] = Field(
        ...,
        description="Keywords or concepts a strong answer should contain",
    )


class InterviewFeedback(BaseModel):
    """Feedback on a candidate's interview answer."""

    score: float = Field(..., ge=0.0, le=10.0, description="Overall score (0–10)")
    strengths: List[str] = Field(..., description="What the answer did well")
    weaknesses: List[str] = Field(..., description="Areas for improvement")
    suggested_answer_framework: Optional[str] = Field(
        None, description="e.g., STAR method outline for this question"
    )
    missed_keywords: List[str] = Field(
        ..., description="Important keywords the answer missed"
    )

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 10.0:
            raise ValueError(f"score must be between 0 and 10, got {v}")
        return round(v, 1)


class ResumeAnalysisResult(BaseModel):
    """Top-level container for a full resume analysis."""

    candidate_name: Optional[str] = Field(None, description="Extracted candidate name")
    target_role: str = Field(..., description="The role the resume targets")
    years_experience: Optional[float] = Field(
        None, ge=0.0, description="Estimated years of professional experience"
    )
    skill_analysis: SkillAnalysis = Field(
        ..., description="Detailed skill analysis"
    )
    format_issues: List[str] = Field(
        default_factory=list, description="Formatting or structure issues detected"
    )
    overall_recommendation: str = Field(
        ..., description="High-level recommendation for the candidate"
    )


def parse_llm_json_output(raw: str) -> dict:
    """Safely extract JSON from an LLM response that may contain markdown fences.

    Handles:
      - Markdown code fences (```json ... ```)
      - Leading/trailing explanatory text
      - Multiple JSON objects (picks the outermost object)
      - Trailing content after valid JSON (extra data)
    """
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3].strip()
        elif text.rfind("```") != -1:
            text = text[: text.rfind("```")].strip()

    text = text.strip()

    # Try to find JSON boundaries if there's extra text
    json_start = text.find("{")
    if json_start == -1:
        # Maybe it's an array?
        json_start = text.find("[")
        if json_start == -1:
            raise json.JSONDecodeError("No JSON object or array found", raw, 0)

    # Walk through braces to find the matching close for the outermost object
    depth = 0
    in_string = False
    escape = False
    json_end = -1

    for i in range(json_start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_end = i
                break
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and text[json_start] == "[":
                json_end = i
                break

    if json_end == -1:
        raise json.JSONDecodeError("Unmatched braces in output", raw, 0)

    text = text[json_start : json_end + 1]
    return json.loads(text)
