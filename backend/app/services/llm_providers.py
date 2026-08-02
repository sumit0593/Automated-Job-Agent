"""
LLM Provider Clients — Individual API wrappers for each LLM provider.

Each function handles:
  - Authentication via config settings
  - Request formatting per provider's API spec
  - Error handling and timeout management
  - Structured response extraction

Providers:
  - Google Gemini (gemini-3.5-flash, gemini-3.1-flash-lite)
  - xAI Grok (grok-3, grok-3-mini)
  - OpenAI (gpt-4o, gpt-4o-mini)
  - HuggingFace Inference API (Qwen, Llama via serverless router)
  - Ollama Local (llama3.3, qwen2.5, mistral)
"""

import json
import time
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from backend.app.config import settings

logger = logging.getLogger("uvicorn.error")


# ─────────────────────────────────────────────────────────────────────────────
# Result Container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    text: str
    provider: str
    model: str
    latency_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_estimate_usd: Optional[float] = None
    success: bool = True
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Provider: Google Gemini
# ─────────────────────────────────────────────────────────────────────────────

def call_gemini(
    system_prompt: str,
    user_prompt: str,
    model: str = "gemini-3.5-flash",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> LLMResponse:
    """
    Calls Google Gemini API via the google-generativeai SDK.
    
    Models:
      - gemini-3.5-flash      → Real-time interaction, fast coding, smooth workflows (Tier 2/3)
      - gemini-3.1-flash-lite → High-volume automated tasks requiring extreme efficiency (Tier 1/2)
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return LLMResponse(
            text="", provider="gemini", model=model,
            latency_ms=0, success=False, error="GEMINI_API_KEY not configured"
        )

    start = time.time()
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            warnings.simplefilter("ignore", category=UserWarning)
            import google.generativeai as genai

        genai.configure(api_key=api_key)
        
        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        
        gm = genai.GenerativeModel(
            model_name=model,
            generation_config=generation_config,
            system_instruction=system_prompt if system_prompt else None,
        )
        
        response = gm.generate_content(user_prompt)
        latency = (time.time() - start) * 1000

        if response and response.text:
            # Estimate tokens (rough: 4 chars ≈ 1 token)
            input_tokens = (len(system_prompt) + len(user_prompt)) // 4
            output_tokens = len(response.text) // 4
            
            # Cost estimation (approximate USD per 1M tokens)
            cost_map = {
                "gemini-3.5-flash": {"input": 0.075, "output": 0.30},
                "gemini-3.1-flash-lite": {"input": 0.025, "output": 0.10},
            }
            rates = cost_map.get(model, cost_map["gemini-3.5-flash"])
            cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

            logger.info(f"LLM[Gemini/{model}]: {latency:.0f}ms | ~{input_tokens}+{output_tokens} tokens | ${cost:.6f}")
            return LLMResponse(
                text=response.text, provider="gemini", model=model,
                latency_ms=latency, input_tokens=input_tokens,
                output_tokens=output_tokens, cost_estimate_usd=cost
            )
        else:
            return LLMResponse(
                text="", provider="gemini", model=model,
                latency_ms=(time.time() - start) * 1000,
                success=False, error="Empty response from Gemini"
            )
    except Exception as e:
        return LLMResponse(
            text="", provider="gemini", model=model,
            latency_ms=(time.time() - start) * 1000,
            success=False, error=str(e)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Provider: xAI Grok
# ─────────────────────────────────────────────────────────────────────────────

def call_grok(
    system_prompt: str,
    user_prompt: str,
    model: str = "grok-3-mini",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> LLMResponse:
    """
    Calls xAI Grok API via OpenAI-compatible REST endpoint.
    
    Models:
      - grok-3       → Full reasoning model (Tier 3/4)
      - grok-3-mini  → Fast, cheaper (Tier 2)
    """
    api_key = getattr(settings, "GROK_API_KEY", "")
    if not api_key:
        return LLMResponse(
            text="", provider="grok", model=model,
            latency_ms=0, success=False, error="GROK_API_KEY not configured"
        )

    start = time.time()
    try:
        import requests
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        res = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        latency = (time.time() - start) * 1000
        
        if res.status_code == 200:
            data = res.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            
            # xAI pricing (approximate)
            cost_map = {
                "grok-3": {"input": 3.00, "output": 15.00},
                "grok-3-mini": {"input": 0.30, "output": 0.50},
            }
            rates = cost_map.get(model, cost_map["grok-3-mini"])
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
            
            logger.info(f"LLM[Grok/{model}]: {latency:.0f}ms | {input_tokens}+{output_tokens} tokens | ${cost:.6f}")
            return LLMResponse(
                text=text, provider="grok", model=model,
                latency_ms=latency, input_tokens=input_tokens,
                output_tokens=output_tokens, cost_estimate_usd=cost
            )
        else:
            return LLMResponse(
                text="", provider="grok", model=model,
                latency_ms=latency, success=False,
                error=f"Grok API returned {res.status_code}: {res.text[:200]}"
            )
    except Exception as e:
        return LLMResponse(
            text="", provider="grok", model=model,
            latency_ms=(time.time() - start) * 1000,
            success=False, error=str(e)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Provider: OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> LLMResponse:
    """
    Calls OpenAI API via the official REST endpoint.
    
    Models:
      - gpt-4o       → Best quality, expensive (Tier 3)
      - gpt-4o-mini  → Fast, cheap (Tier 2)
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        return LLMResponse(
            text="", provider="openai", model=model,
            latency_ms=0, success=False, error="OPENAI_API_KEY not configured"
        )

    start = time.time()
    try:
        import requests
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        latency = (time.time() - start) * 1000
        
        if res.status_code == 200:
            data = res.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            
            cost_map = {
                "gpt-4o": {"input": 2.50, "output": 10.00},
                "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            }
            rates = cost_map.get(model, cost_map["gpt-4o-mini"])
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
            
            logger.info(f"LLM[OpenAI/{model}]: {latency:.0f}ms | {input_tokens}+{output_tokens} tokens | ${cost:.6f}")
            return LLMResponse(
                text=text, provider="openai", model=model,
                latency_ms=latency, input_tokens=input_tokens,
                output_tokens=output_tokens, cost_estimate_usd=cost
            )
        else:
            return LLMResponse(
                text="", provider="openai", model=model,
                latency_ms=latency, success=False,
                error=f"OpenAI API returned {res.status_code}: {res.text[:200]}"
            )
    except Exception as e:
        return LLMResponse(
            text="", provider="openai", model=model,
            latency_ms=(time.time() - start) * 1000,
            success=False, error=str(e)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Provider: HuggingFace Inference API
# ─────────────────────────────────────────────────────────────────────────────

def call_huggingface(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> LLMResponse:
    """
    Calls HuggingFace Serverless Inference Router.
    
    Models tried in order:
      - Configured LLM_MODEL from settings
      - meta-llama/Llama-3.3-70B-Instruct
      - Qwen/Qwen2.5-Coder-32B-Instruct
    """
    hf_token = getattr(settings, "HF_TOKEN", "")
    if not hf_token:
        return LLMResponse(
            text="", provider="huggingface", model=model or "unknown",
            latency_ms=0, success=False, error="HF_TOKEN not configured"
        )

    models_to_try = list(dict.fromkeys(filter(None, [
        model,
        getattr(settings, "LLM_MODEL", ""),
        "meta-llama/Llama-3.3-70B-Instruct",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
    ])))

    start = time.time()
    
    import requests
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json",
    }
    router_url = "https://router.huggingface.co/v1/chat/completions"

    for m in models_to_try:
        try:
            payload = {
                "model": m,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            res = requests.post(router_url, headers=headers, json=payload, timeout=30)
            latency = (time.time() - start) * 1000
            
            if res.status_code == 200:
                data = res.json()
                if "choices" in data and len(data["choices"]) > 0:
                    text = data["choices"][0]["message"]["content"]
                    logger.info(f"LLM[HuggingFace/{m}]: {latency:.0f}ms | Free tier")
                    return LLMResponse(
                        text=text, provider="huggingface", model=m,
                        latency_ms=latency, cost_estimate_usd=0.0
                    )
            else:
                logger.warning(f"HF model {m} returned {res.status_code}")
        except Exception as e:
            logger.warning(f"HF model {m} failed: {e}")

    return LLMResponse(
        text="", provider="huggingface", model=models_to_try[0] if models_to_try else "unknown",
        latency_ms=(time.time() - start) * 1000,
        success=False, error="All HuggingFace models failed"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Provider: Ollama (Local)
# ─────────────────────────────────────────────────────────────────────────────

def call_ollama(
    system_prompt: str,
    user_prompt: str,
    model: str = "llama3.2",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> LLMResponse:
    """
    Calls local Ollama server for free, private inference.
    
    Common models:
      - llama3.2       → Meta Llama 3.2 (lightweight)
      - llama3.3       → Meta Llama 3.3 70B (powerful)
      - qwen2.5        → Qwen 2.5 (good coder)
      - mistral        → Mistral 7B (fast)
    """
    ollama_url = getattr(settings, "OLLAMA_URL", "http://localhost:11434")
    
    start = time.time()
    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"
        
        req = urllib.request.Request(
            f"{ollama_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=120) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            text = res_data["message"]["content"]
            latency = (time.time() - start) * 1000
            
            logger.info(f"LLM[Ollama/{model}]: {latency:.0f}ms | Local/Free")
            return LLMResponse(
                text=text, provider="ollama", model=model,
                latency_ms=latency, cost_estimate_usd=0.0
            )
    except urllib.error.URLError as e:
        return LLMResponse(
            text="", provider="ollama", model=model,
            latency_ms=(time.time() - start) * 1000,
            success=False, error=f"Ollama not running: {e.reason}"
        )
    except Exception as e:
        return LLMResponse(
            text="", provider="ollama", model=model,
            latency_ms=(time.time() - start) * 1000,
            success=False, error=str(e)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Provider Availability Check
# ─────────────────────────────────────────────────────────────────────────────

def get_available_providers() -> Dict[str, bool]:
    """Returns which providers are currently configured and available."""
    available = {
        "gemini": bool(getattr(settings, "GEMINI_API_KEY", "")),
        "grok": bool(getattr(settings, "GROK_API_KEY", "")),
        "openai": bool(getattr(settings, "OPENAI_API_KEY", "")),
        "huggingface": bool(getattr(settings, "HF_TOKEN", "")),
        "ollama": False,  # Checked at runtime
    }
    
    # Quick Ollama health check
    try:
        ollama_url = getattr(settings, "OLLAMA_URL", "http://localhost:11434")
        req = urllib.request.Request(f"{ollama_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                available["ollama"] = True
    except Exception:
        pass
    
    return available
