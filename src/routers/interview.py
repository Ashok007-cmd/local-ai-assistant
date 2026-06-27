from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.config import settings
from src.models import (
    InterviewFeedback,
    InterviewQuestion,
    parse_llm_json_output,
)
from src.routers._client import get_llm_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["interview"])

class InterviewSimulateRequest(BaseModel):
    resume_text: str = Field(..., min_length=50, max_length=100_000)
    target_role: str = Field(..., min_length=2, max_length=200)
    model: str = Field(default=settings.DEFAULT_MODEL, description="Ollama model name")
    language: str = Field(default="english", description="Preferred language")


class SubmitAnswerRequest(BaseModel):
    question: InterviewQuestion
    answer: str = Field(..., min_length=10, max_length=10_000)
    model: str = Field(default=settings.DEFAULT_MODEL, description="Ollama model name")
    language: str = Field(default="english", description="Preferred language")


@router.post("/interview/generate-questions")
async def generate_questions(req: InterviewSimulateRequest):
    """
    Generate mock interview questions asynchronously based on a resume and target role.
    """
    client = get_llm_client(req.model)

    prompt = (
        f"Generate 1 mock interview question for a {req.target_role} position.\n"
        f"Candidate's resume:\n{req.resume_text}\n\n"
        "Return a single InterviewQuestion JSON object with:\n"
        "- question\n"
        "- question_type (behavioral|technical|situational|STAR)\n"
        "- difficulty (easy|medium|hard)\n"
        "- target_skill\n"
        "- ideal_answer_keywords (list of 4-6 strings)\n\n"
        f"You MUST generate the question and target_skill in the following language: {req.language}. "
        f"The ideal_answer_keywords must also be in {req.language}."
    )

    system_prompt = (
        f"You are a hiring manager conducting interviews for a {req.target_role} role. "
        "Generate a single relevant, challenging question based on the candidate's resume. "
        "Return a single JSON object — NOT an array."
    )

    result = await client.generate_structured_async(
        prompt=prompt,
        schema=InterviewQuestion,
        system_prompt=system_prompt,
    )

    return {
        "success": result.success,
        "model": req.model,
        "attempts": result.attempts,
        "errors": result.errors,
        "data": result.data.model_dump() if result.data else None,
    }


@router.post("/interview/submit-answer")
async def submit_answer(req: SubmitAnswerRequest):
    """
    Submit an answer to an interview question asynchronously and get structured feedback.
    """
    client = get_llm_client(req.model)

    prompt = (
        f"Question: {req.question.question}\n"
        f"Question type: {req.question.question_type}\n"
        f"Difficulty: {req.question.difficulty}\n"
        f"Target skill: {req.question.target_skill}\n"
        f"Ideal keywords to cover: {', '.join(req.question.ideal_answer_keywords)}\n\n"
        f"Candidate's answer:\n{req.answer}\n\n"
        "Provide structured InterviewFeedback with:\n"
        "- score (0-10)\n"
        "- strengths\n"
        "- weaknesses\n"
        "- suggested_answer_framework\n"
        "- missed_keywords\n\n"
        f"You MUST evaluate and formulate all textual feedback (strengths, weaknesses, "
        f"suggested_answer_framework, and missed_keywords) in the following language: {req.language}."
    )

    system_prompt = (
        "You are an experienced interview coach. Provide constructive, actionable feedback. "
        "Be fair but honest in your assessment."
    )

    result = await client.generate_structured_async(
        prompt=prompt,
        schema=InterviewFeedback,
        system_prompt=system_prompt,
    )

    return {
        "success": result.success,
        "model": req.model,
        "attempts": result.attempts,
        "errors": result.errors,
        "data": result.data.model_dump() if result.data else None,
    }


@router.post("/interview/submit-answer-stream")
async def submit_answer_stream(req: SubmitAnswerRequest):
    """
    Submit an answer to an interview question and get a streaming coaching response
    followed by the final structured JSON metrics.
    """
    client = get_llm_client(req.model)

    prompt = (
        f"You are conducting a mock interview for the role of {req.question.target_skill} or related target role.\n"
        f"Question: {req.question.question}\n"
        f"Question type: {req.question.question_type}\n"
        f"Difficulty: {req.question.difficulty}\n"
        f"Target skill: {req.question.target_skill}\n"
        f"Ideal keywords to cover: {', '.join(req.question.ideal_answer_keywords)}\n\n"
        f"Candidate's answer:\n{req.answer}\n\n"
        "Provide your feedback in two parts:\n"
        "1. A conversational, spoken-style coaching response (1-2 paragraphs) talking directly "
        "to the candidate, explaining what they did well, what they missed, and how to structure "
        "it better.\n"
        "2. A structured metrics block beginning exactly with the delimiter: ===METRICS===\n"
        "Followed by a single valid JSON object containing the feedback metrics. The JSON must match this schema:\n"
        f"{json.dumps(InterviewFeedback.model_json_schema(), indent=2)}\n\n"
        f"You MUST write BOTH the coaching response AND all text fields in the metrics JSON "
        f"EXCLUSIVELY in the following language: {req.language}.\n"
        "Output the conversational coaching text first, then '===METRICS===', and then the JSON. "
        "Do not include other text or markdown code blocks for the JSON."
    )

    system_prompt = (
        "You are an experienced interview coach. Provide constructive, actionable feedback. "
        "Be encouraging but honest."
    )

    async def event_generator():
        coaching_text_buffer = ""
        metrics_buffer = ""
        in_metrics = False

        try:
            async for chunk in client.stream_raw_async(prompt, system_prompt):
                if "===METRICS===" in chunk and not in_metrics:
                    parts = chunk.split("===METRICS===")
                    if parts[0]:
                        yield f"event: coaching\ndata: {json.dumps(parts[0])}\n\n"
                    in_metrics = True
                    if len(parts) > 1 and parts[1]:
                        metrics_buffer += parts[1]
                elif in_metrics:
                    metrics_buffer += chunk
                else:
                    temp_buffer = coaching_text_buffer + chunk
                    if "===METRICS===" in temp_buffer:
                        idx = temp_buffer.find("===METRICS===")
                        sent_len = len(coaching_text_buffer)
                        coaching_part = temp_buffer[sent_len:idx]
                        if coaching_part:
                            yield f"event: coaching\ndata: {json.dumps(coaching_part)}\n\n"
                        in_metrics = True
                        metrics_part = temp_buffer[idx + len("===METRICS==="):]
                        metrics_buffer += metrics_part
                    else:
                        coaching_text_buffer += chunk
                        yield f"event: coaching\ndata: {json.dumps(chunk)}\n\n"

            # Send done event for coaching text
            yield "event: coaching_done\ndata: {}\n\n"

            # Parse and validate the metrics JSON
            try:
                parsed = parse_llm_json_output(metrics_buffer)
                validated = InterviewFeedback.model_validate(parsed)
                yield f"event: metrics\ndata: {validated.model_dump_json()}\n\n"
            except Exception as e:
                logger.error("Failed to parse streamed metrics JSON: %s. Raw: %s", e, metrics_buffer)
                lang = req.language.lower()
                if lang == "german":
                    strengths = ["Antwort erfolgreich übermittelt"]
                    weaknesses = ["Detaillierte Metriken konnten aufgrund eines Parsing-Fehlers nicht generiert werden"]
                    suggested = "Bitte überprüfen Sie das Coaching-Feedback oben."
                elif lang == "spanish":
                    strengths = ["Respuesta enviada con éxito"]
                    weaknesses = ["No se pudo generar el análisis de métricas detallado"]
                    suggested = "Por favor revise las observaciones del coach arriba."
                else:
                    strengths = ["Answer submitted successfully"]
                    weaknesses = ["Could not generate detailed metrics parsing error"]
                    suggested = "Please review the coaching feedback text above."

                fallback = InterviewFeedback(
                    score=6.0,
                    strengths=strengths,
                    weaknesses=weaknesses,
                    suggested_answer_framework=suggested,
                    missed_keywords=[]
                )
                yield f"event: metrics\ndata: {fallback.model_dump_json()}\n\n"
        except Exception as e:
            logger.error("Error in streaming interview feedback: %s", e)
            yield f"event: error\ndata: {json.dumps(str(e))}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
