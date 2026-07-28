import json
import logging
import urllib.request
import urllib.error
from huggingface_hub import InferenceClient
from backend.app.config import settings

logger = logging.getLogger("uvicorn.error")

def query_llm(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    """
    Sends a query to the LLM (Gemini API, Hugging Face Inference API, or local Ollama).
    """
    # 0. Try Google Gemini API if key is provided
    if getattr(settings, "GEMINI_API_KEY", ""):
        try:
            import google.generativeai as genai
            logger.info("Querying Google Gemini API...")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(f"{system_prompt}\n\n{user_prompt}")
            if response and response.text:
                return response.text
        except Exception as e:
            logger.error(f"Error querying Gemini API: {e}. Falling back...")

    # 1. Try Hugging Face Inference API if token is provided
    if settings.HF_TOKEN:
        import requests
        models_to_try = [
            settings.LLM_MODEL,
            "meta-llama/Llama-3.3-70B-Instruct",
            "Qwen/Qwen2.5-Coder-32B-Instruct"
        ]
        seen = set()
        models = [m for m in models_to_try if not (m in seen or seen.add(m))]
        
        headers = {
            "Authorization": f"Bearer {settings.HF_TOKEN}",
            "Content-Type": "application/json"
        }
        router_url = "https://router.huggingface.co/v1/chat/completions"
        
        for m in models:
            try:
                logger.info(f"Querying Hugging Face Serverless Router ({m})...")
                payload = {
                    "model": m,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                }
                res = requests.post(router_url, headers=headers, json=payload, timeout=30)
                if res.status_code == 200:
                    data = res.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"]
                else:
                    logger.warning(f"Hugging Face router returned {res.status_code}: {res.text[:100]}")
            except Exception as e:
                logger.warning(f"Hugging Face model {m} unavailable ({e}). Trying next candidate...")

    # 2. Try Local Ollama (defaulting to qwen2.5 or similar if running locally)
    try:
        logger.info("Attempting to query local Ollama server...")
        ollama_url = "http://localhost:11434/api/chat"
        payload = {
            "model": "qwen2.5" if "qwen" in settings.LLM_MODEL.lower() else "llama3",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }
        
        req = urllib.request.Request(
            ollama_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["message"]["content"]
    except urllib.error.URLError as e:
        logger.warning(f"Ollama not running or unreachable: {e.reason}")
    except Exception as e:
        logger.error(f"Ollama query failed: {e}")

    # 3. Final Fallback: Return empty structure if json_mode, else warning
    logger.warning("No LLM API/Server configured or running. Using rule-based fallback.")
    if json_mode:
        return json.dumps({
            "skills": [],
            "experience": 0.0,
            "location": None,
            "error": "LLM not configured. Using rule-based regex fallback."
        })
    else:
        return "LLM not configured. Please set HF_TOKEN in your .env file or run Ollama locally."

