"""
LLM Task Router — Intelligent model selection based on task complexity.

Routes each LLM call to the optimal model based on:
  - Task type (extraction, classification, generation, reasoning, vision, conversation)
  - Configured routing strategy (cost_optimized, quality_first, local_only)
  - Provider availability (graceful fallback chains)
  - Cost and latency tracking

Tier System:
  Tier 1 (LOCAL/FREE)   → Ollama (Llama/Qwen) or HuggingFace free tier
  Tier 2 (FAST API)     → Gemini Flash, Grok Mini, GPT-4o-mini
  Tier 3 (REASONING)    → Gemini Pro, GPT-4o, Grok 3
  Tier 4 (VISION/DOM)   → Gemini Pro Vision, Grok Vision
"""

import json
import time
import logging
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

from backend.app.config import settings
from backend.app.services.llm_providers import (
    LLMResponse,
    call_gemini,
    call_grok,
    call_openai,
    call_huggingface,
    call_ollama,
    get_available_providers,
)

logger = logging.getLogger("uvicorn.error")


# ─────────────────────────────────────────────────────────────────────────────
# Task Types — What kind of work is being done
# ─────────────────────────────────────────────────────────────────────────────

class TaskType(str, Enum):
    """Classification of LLM task complexity."""
    
    # Tier 1 — Simple extraction, classification, yes/no answers
    EXTRACTION = "extraction"             # Extract name/email/phone from text
    CLASSIFICATION = "classification"     # Intent detection, app type classification
    VALIDATION = "validation"             # Check if answer contains placeholders
    
    # Tier 2 — Structured generation with context
    PARSING = "parsing"                   # Resume parsing, job description analysis
    QA_SIMPLE = "qa_simple"               # Answer notice period, CTC questions
    QA_COMPLEX = "qa_complex"             # Answer "why should we hire you"
    HYDE_GENERATION = "hyde_generation"    # HyDE hypothetical document generation
    EXPLANATION = "explanation"           # Match explanation generation
    CONVERSATION = "conversation"         # Chatbot response generation
    
    # Tier 3 — Deep reasoning, creative generation
    RESUME_TAILORING = "resume_tailoring" # Tailor resume to job description
    COVER_LETTER = "cover_letter"         # Generate cover letter
    ATS_OPTIMIZATION = "ats_optimization" # ATS score critic analysis
    DOM_REASONING = "dom_reasoning"       # Unknown ATS form field mapping
    PLANNING = "planning"                 # Multi-step action planning
    
    # Tier 4 — Visual understanding
    VISION_FORM = "vision_form"           # Screenshot → form field detection
    VISION_VERIFY = "vision_verify"       # Screenshot → verify submission success
    VISION_NAVIGATE = "vision_navigate"   # Screenshot → next action reasoning


class RoutingStrategy(str, Enum):
    """How aggressively to optimize for cost vs quality."""
    COST_OPTIMIZED = "cost_optimized"   # Prefer local/free models whenever possible
    BALANCED = "balanced"               # Default — smart tier selection
    QUALITY_FIRST = "quality_first"     # Always use best available model
    LOCAL_ONLY = "local_only"           # Only use Ollama — no API calls


# ─────────────────────────────────────────────────────────────────────────────
# Tier → Provider Mapping
# ─────────────────────────────────────────────────────────────────────────────

# Task type → assigned tier
TASK_TIER_MAP: Dict[TaskType, int] = {
    # Tier 1 — local/free
    TaskType.EXTRACTION: 1,
    TaskType.CLASSIFICATION: 1,
    TaskType.VALIDATION: 1,
    
    # Tier 2 — fast API
    TaskType.PARSING: 2,
    TaskType.QA_SIMPLE: 1,
    TaskType.QA_COMPLEX: 2,
    TaskType.HYDE_GENERATION: 2,
    TaskType.EXPLANATION: 2,
    TaskType.CONVERSATION: 2,
    
    # Tier 3 — reasoning
    TaskType.RESUME_TAILORING: 3,
    TaskType.COVER_LETTER: 3,
    TaskType.ATS_OPTIMIZATION: 3,
    TaskType.DOM_REASONING: 3,
    TaskType.PLANNING: 3,
    
    # Tier 4 — vision
    TaskType.VISION_FORM: 4,
    TaskType.VISION_VERIFY: 4,
    TaskType.VISION_NAVIGATE: 4,
}

# Tier → ordered fallback chains per routing strategy
# Each entry: (provider_name, model_name)
TIER_CHAINS: Dict[str, Dict[int, List[tuple]]] = {
    "balanced": {
        1: [
            ("gemini", "gemini-3.1-flash-lite"),
            ("ollama", "llama3.2"),
            ("ollama", "qwen2.5"),
            ("huggingface", ""),
        ],
        2: [
            ("gemini", "gemini-3.5-flash"),
            ("gemini", "gemini-3.1-flash-lite"),
            ("grok", "grok-3-mini"),
            ("openai", "gpt-4o-mini"),
            ("huggingface", ""),
            ("ollama", "llama3.2"),
        ],
        3: [
            ("gemini", "gemini-3.5-flash"),
            ("openai", "gpt-4o"),
            ("grok", "grok-3"),
            ("gemini", "gemini-3.1-flash-lite"),
            ("huggingface", ""),
        ],
        4: [
            ("gemini", "gemini-3.5-flash"),
            ("grok", "grok-3"),
            ("openai", "gpt-4o"),
            ("gemini", "gemini-3.1-flash-lite"),
        ],
    },
    "cost_optimized": {
        1: [
            ("gemini", "gemini-3.1-flash-lite"),
            ("ollama", "llama3.2"),
            ("ollama", "qwen2.5"),
            ("huggingface", ""),
        ],
        2: [
            ("gemini", "gemini-3.1-flash-lite"),
            ("ollama", "llama3.2"),
            ("huggingface", ""),
        ],
        3: [
            ("gemini", "gemini-3.5-flash"),
            ("gemini", "gemini-3.1-flash-lite"),
            ("huggingface", ""),
            ("ollama", "llama3.2"),
        ],
        4: [
            ("gemini", "gemini-3.5-flash"),
            ("gemini", "gemini-3.1-flash-lite"),
        ],
    },
    "quality_first": {
        1: [
            ("gemini", "gemini-3.1-flash-lite"),
            ("gemini", "gemini-3.5-flash"),
            ("openai", "gpt-4o-mini"),
            ("grok", "grok-3-mini"),
            ("ollama", "llama3.2"),
        ],
        2: [
            ("gemini", "gemini-3.5-flash"),
            ("openai", "gpt-4o"),
            ("grok", "grok-3"),
            ("gemini", "gemini-3.1-flash-lite"),
        ],
        3: [
            ("gemini", "gemini-3.5-flash"),
            ("openai", "gpt-4o"),
            ("grok", "grok-3"),
        ],
        4: [
            ("gemini", "gemini-3.5-flash"),
            ("grok", "grok-3"),
            ("openai", "gpt-4o"),
        ],
    },
    "local_only": {
        1: [("ollama", "llama3.2"), ("ollama", "qwen2.5"), ("ollama", "mistral")],
        2: [("ollama", "llama3.2"), ("ollama", "qwen2.5")],
        3: [("ollama", "llama3.2"), ("ollama", "qwen2.5")],
        4: [("ollama", "llama3.2")],
    },
}

# Provider name → callable function
PROVIDER_FUNCTIONS: Dict[str, Callable] = {
    "gemini": call_gemini,
    "grok": call_grok,
    "openai": call_openai,
    "huggingface": call_huggingface,
    "ollama": call_ollama,
}


# ─────────────────────────────────────────────────────────────────────────────
# Cost Tracker — Accumulates spend across all providers
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CostTracker:
    """Tracks cumulative LLM usage costs and call counts per session."""
    total_cost_usd: float = 0.0
    total_calls: int = 0
    total_latency_ms: float = 0.0
    calls_by_provider: Dict[str, int] = field(default_factory=dict)
    cost_by_provider: Dict[str, float] = field(default_factory=dict)
    calls_by_task: Dict[str, int] = field(default_factory=dict)
    
    def record(self, response: LLMResponse, task_type: str):
        self.total_calls += 1
        self.total_latency_ms += response.latency_ms
        cost = response.cost_estimate_usd or 0.0
        self.total_cost_usd += cost
        
        provider = response.provider
        self.calls_by_provider[provider] = self.calls_by_provider.get(provider, 0) + 1
        self.cost_by_provider[provider] = self.cost_by_provider.get(provider, 0.0) + cost
        self.calls_by_task[task_type] = self.calls_by_task.get(task_type, 0) + 1
    
    def summary(self) -> Dict[str, Any]:
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_calls": self.total_calls,
            "avg_latency_ms": round(self.total_latency_ms / max(self.total_calls, 1), 1),
            "calls_by_provider": dict(self.calls_by_provider),
            "cost_by_provider": {k: round(v, 6) for k, v in self.cost_by_provider.items()},
            "calls_by_task": dict(self.calls_by_task),
        }


# ─────────────────────────────────────────────────────────────────────────────
# LLM Router — The Core Engine
# ─────────────────────────────────────────────────────────────────────────────

class LLMRouter:
    """
    Intelligent LLM Task Router.
    
    Routes each call to the optimal model based on task type, provider
    availability, and configured routing strategy. Automatically falls
    back through the provider chain on failures.
    
    Usage:
        router = LLMRouter()
        text = router.route(TaskType.CLASSIFICATION, system_prompt, user_prompt)
        text = router.route(TaskType.RESUME_TAILORING, system_prompt, user_prompt)
    """
    
    def __init__(self, strategy: Optional[str] = None):
        self.strategy = strategy or getattr(settings, "LLM_ROUTING_STRATEGY", "balanced")
        if self.strategy not in TIER_CHAINS:
            logger.warning(f"LLMRouter: Unknown strategy '{self.strategy}', falling back to 'balanced'")
            self.strategy = "balanced"
        
        self.cost_tracker = CostTracker()
        self._provider_cache: Optional[Dict[str, bool]] = None
        self._cache_timestamp: float = 0.0
        
        logger.info(f"LLMRouter: Initialized with strategy='{self.strategy}'")
    
    def _get_available_providers(self) -> Dict[str, bool]:
        """Cached provider availability check (refreshed every 60s)."""
        now = time.time()
        if self._provider_cache is None or (now - self._cache_timestamp) > 60:
            self._provider_cache = get_available_providers()
            self._cache_timestamp = now
            available = [k for k, v in self._provider_cache.items() if v]
            logger.info(f"LLMRouter: Available providers: {available}")
        return self._provider_cache
    
    def route(
        self,
        task_type: TaskType,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        json_mode: bool = False,
        force_provider: Optional[str] = None,
        force_model: Optional[str] = None,
    ) -> str:
        """
        Routes an LLM call to the optimal provider/model for the given task.
        
        Args:
            task_type: The type of task to perform (determines tier)
            system_prompt: System instruction for the LLM
            user_prompt: User message content
            temperature: Sampling temperature (default 0.3)
            max_tokens: Maximum output tokens (default 2000)
            json_mode: Whether to request JSON output format
            force_provider: Override automatic routing — use this specific provider
            force_model: Override automatic routing — use this specific model
        
        Returns:
            The LLM response text, or empty string on complete failure.
        """
        tier = TASK_TIER_MAP.get(task_type, 2)
        available = self._get_available_providers()
        
        # Build the fallback chain for this task's tier
        chain = TIER_CHAINS.get(self.strategy, TIER_CHAINS["balanced"]).get(tier, [])
        
        # If force_provider is specified, put it first
        if force_provider and force_model:
            chain = [(force_provider, force_model)] + [
                (p, m) for p, m in chain if p != force_provider
            ]
        elif force_provider:
            chain = [(p, m) for p, m in chain if p == force_provider] + [
                (p, m) for p, m in chain if p != force_provider
            ]
        
        logger.info(
            f"LLMRouter: Routing task='{task_type.value}' tier={tier} "
            f"strategy='{self.strategy}' chain={[(p, m) for p, m in chain[:3]]}..."
        )
        
        # Try each provider in the chain
        for provider_name, model_name in chain:
            # Skip unavailable providers (except ollama which we check live)
            if provider_name != "ollama" and not available.get(provider_name, False):
                continue
            
            call_fn = PROVIDER_FUNCTIONS.get(provider_name)
            if not call_fn:
                continue
            
            try:
                response: LLMResponse = call_fn(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
                
                if response.success and response.text:
                    self.cost_tracker.record(response, task_type.value)
                    return response.text
                else:
                    logger.warning(
                        f"LLMRouter: {provider_name}/{model_name} failed: "
                        f"{response.error}. Trying next in chain..."
                    )
            except Exception as e:
                logger.warning(
                    f"LLMRouter: {provider_name}/{model_name} exception: {e}. "
                    f"Trying next in chain..."
                )
        
        # Complete failure — all providers exhausted
        logger.error(
            f"LLMRouter: ALL providers failed for task='{task_type.value}'. "
            f"Returning empty response."
        )
        
        # Return safe fallback for JSON mode
        if json_mode:
            return json.dumps({
                "error": "All LLM providers failed",
                "task_type": task_type.value,
            })
        return ""
    
    def route_with_response(
        self,
        task_type: TaskType,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> LLMResponse:
        """
        Like route(), but returns the full LLMResponse object
        including metadata (provider, model, latency, cost).
        """
        tier = TASK_TIER_MAP.get(task_type, 2)
        available = self._get_available_providers()
        chain = TIER_CHAINS.get(self.strategy, TIER_CHAINS["balanced"]).get(tier, [])
        
        for provider_name, model_name in chain:
            if provider_name != "ollama" and not available.get(provider_name, False):
                continue
            
            call_fn = PROVIDER_FUNCTIONS.get(provider_name)
            if not call_fn:
                continue
            
            try:
                response = call_fn(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model_name,
                    **kwargs,
                )
                if response.success and response.text:
                    self.cost_tracker.record(response, task_type.value)
                    return response
            except Exception:
                continue
        
        return LLMResponse(
            text="", provider="none", model="none",
            latency_ms=0, success=False,
            error="All providers exhausted"
        )
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Returns accumulated cost tracking data."""
        return self.cost_tracker.summary()


# ─────────────────────────────────────────────────────────────────────────────
# Global Singleton
# ─────────────────────────────────────────────────────────────────────────────

llm_router = LLMRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Backward-Compatible Wrapper
# ─────────────────────────────────────────────────────────────────────────────

def query_llm_routed(
    system_prompt: str,
    user_prompt: str,
    task_type: TaskType = TaskType.QA_COMPLEX,
    json_mode: bool = False,
) -> str:
    """
    Drop-in replacement for the legacy query_llm() function,
    but routes through the intelligent tier system.
    
    Use this during migration before all callers are updated
    to use llm_router.route() directly.
    """
    return llm_router.route(
        task_type=task_type,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_mode=json_mode,
    )
