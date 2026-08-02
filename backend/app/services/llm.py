"""
LLM Service — Unified entry point for LLM calls.

This module provides the backward-compatible query_llm() function used by
all existing callers across the codebase. It now delegates to the intelligent
LLM Router which selects the optimal model based on task complexity.

Migration Guide:
  OLD:  from backend.app.services.llm import query_llm
        result = query_llm(system, user, json_mode=True)

  NEW:  from backend.app.services.llm_router import llm_router, TaskType
        result = llm_router.route(TaskType.PARSING, system, user, json_mode=True)

Both approaches work — query_llm() is preserved for backward compatibility
and defaults to TaskType.QA_COMPLEX routing.
"""

import json
import logging
from typing import Optional

from backend.app.services.llm_router import llm_router, TaskType

logger = logging.getLogger("uvicorn.error")


def query_llm(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = False,
    task_type: Optional[TaskType] = None,
) -> str:
    """
    Sends a query to the LLM with intelligent model selection.
    
    This is the backward-compatible wrapper. All existing callers
    (qa_agent, tailor, critic, etc.) continue to work unchanged.
    
    New callers should pass task_type for optimal routing:
        query_llm(sys, usr, task_type=TaskType.CLASSIFICATION)
    
    Without task_type, defaults to TaskType.QA_COMPLEX (Tier 2).
    
    Args:
        system_prompt: System instructions for the LLM.
        user_prompt: User message content.
        json_mode: If True, requests JSON output format.
        task_type: Optional task type for intelligent routing.
                   If None, uses QA_COMPLEX as default.
    
    Returns:
        LLM response text. Returns fallback JSON or warning string if all providers fail.
    """
    effective_task = task_type or TaskType.QA_COMPLEX
    
    result = llm_router.route(
        task_type=effective_task,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_mode=json_mode,
    )
    
    # If the router returned empty, provide safe fallback (matches old behavior)
    if not result:
        logger.warning("query_llm: LLM Router returned empty. Using fallback.")
        if json_mode:
            return json.dumps({
                "skills": [],
                "experience": 0.0,
                "location": None,
                "error": "All LLM providers failed. Check API keys in .env file."
            })
        else:
            return (
                "LLM not available. Please configure at least one provider:\n"
                "- Set GEMINI_API_KEY in .env for Google Gemini\n"
                "- Set GROK_API_KEY in .env for xAI Grok\n"
                "- Set OPENAI_API_KEY in .env for OpenAI\n"
                "- Set HF_TOKEN in .env for HuggingFace\n"
                "- Run Ollama locally (ollama serve)"
            )
    
    return result
