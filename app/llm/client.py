import time
import httpx
from typing import List, Dict, Any, Tuple
from app.config import settings
from app.llm.mock_engine import MockConversationalEngine

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

class LLMClient:
    """
    Groq LPU LLM Client with automatic fallback and zero-cost mock engine.
    """

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.primary_model = settings.GROQ_DEFAULT_MODEL
        self.fallback_model = settings.GROQ_FALLBACK_MODEL

    async def generate(self, messages: List[Dict[str, str]]) -> Tuple[str, float]:
        """
        Generates conversational response, returning (text, ttft_latency_ms).
        """
        start = time.perf_counter()

        # If no API key configured, use local zero-cost mock engine
        if not self.api_key:
            response_text = MockConversationalEngine.generate_response(messages)
            ttft_ms = (time.perf_counter() - start) * 1000.0
            return response_text, ttft_ms

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Attempt primary model (llama-3.3-70b-versatile)
        payload = {
            "model": self.primary_model,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 120,
            "top_p": 0.9
        }

        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                res = await client.post(GROQ_ENDPOINT, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    text = data["choices"][0]["message"]["content"]
                    ttft_ms = (time.perf_counter() - start) * 1000.0
                    return text.strip(), ttft_ms
                elif res.status_code == 429:
                    # Rate limit hit -> Fallback to 8b
                    payload["model"] = self.fallback_model
                    res_fallback = await client.post(GROQ_ENDPOINT, json=payload, headers=headers)
                    if res_fallback.status_code == 200:
                        data = res_fallback.json()
                        text = data["choices"][0]["message"]["content"]
                        ttft_ms = (time.perf_counter() - start) * 1000.0
                        return text.strip(), ttft_ms
            except Exception:
                pass

        # Final fallback to deterministic mock engine
        response_text = MockConversationalEngine.generate_response(messages)
        ttft_ms = (time.perf_counter() - start) * 1000.0
        return response_text, ttft_ms

# Global singleton
llm_client = LLMClient()
