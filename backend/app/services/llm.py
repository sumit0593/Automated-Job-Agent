import json
import logging
import urllib.request
import urllib.error
from huggingface_hub import InferenceClient
from backend.app.config import settings

logger = logging.getLogger("uvicorn.error")

def query_llm(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    """
    Sends a query to the LLM (either Hugging Face Inference API or local Ollama).
    """
    # 1. Try Hugging Face Inference API if token is provided
    if settings.HF_TOKEN:
        try:
            logger.info(f"Querying Hugging Face Inference API with model {settings.LLM_MODEL}...")
            client = InferenceClient(token=settings.HF_TOKEN)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Using chat_completion which is standard and robust
            response = client.chat_completion(
                model=settings.LLM_MODEL,
                messages=messages,
                max_tokens=2000,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error querying Hugging Face API: {e}. Falling back...")

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

    # 3. Final Fallback: Return a structured mock if json_mode, else warning
    logger.warning("No LLM API/Server configured or running. Using rule-based fallback.")
    if json_mode:
        # We will parse this fallback inside the calling function if needed,
        # but let's provide a structured response that can be successfully parsed.
        return json.dumps({
            "skills": ["Python", "FastAPI", "JavaScript", "React"],
            "experience": 3.0,
            "location": "Remote",
            "error": "LLM not configured. This is a fallback parsed profile."
        })
    else:
        return "LLM not configured. Please set HF_TOKEN in your .env file or run Ollama locally."
