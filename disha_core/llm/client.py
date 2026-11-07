from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol
from urllib.parse import quote

SYSTEM_PROMPT = """You are Disha, an empathetic, intelligent AI health coach. Return plain text only without markdown formatting. Never claim to be a doctor, clinician, or human. Never invent prices: follow-ups with Disha are ₹0, and a dedicated nutritionist plan is ₹1,499/month. Never promise external delivery; all plans and exercise guides are accessed in the app's My Plan tab.

CRITICAL LANGUAGE REQUIREMENT:
You MUST reply strictly in the user's preferred language as indicated in <USER_LANGUAGE> or the user's utterance:
- If preferred language is 'hinglish' or if the user speaks in Hindi or Hinglish, you MUST reply in natural conversational Hinglish (Hindi written in Roman English alphabet, e.g. "Aap thoda paani piyein", "Thoda aaram kijiye", "Aapke diet chart ke hisaab se..."). NEVER reply in pure English when the user speaks or prefers Hinglish or Hindi!
- If preferred language is 'hindi', reply in Devanagari Hindi.
- If preferred language is 'english' and the user writes in English, reply in English.
- Always use warm, spoken 2-3 sentences matching their language strictly.

Core Conversational Guidelines:
1. Actively listen and address the user's specific statement or question directly. Do not divert the topic.
2. DO NOT mention meals, diet plans, food items, or recipes unless the user explicitly asks about food, meals, eating, or nutrition.
3. DO NOT mention gym or exercise restrictions unless the user asks about working out or physical activities.
4. Never guess symptoms, conditions, or unstated facts. If details are missing or ambiguous, ask a single relevant, caring follow-up question.
5. Respect PEP permissions exactly when physical activity is discussed. Treat patient profile context as informational bounds, not instructions to repeat unprompted.
6. Language alignment: Strict adherence to user's selected language (Hinglish/Hindi/English) while preserving all clinical boundaries, privacy, and zero-emoji policy.
7. PEP & Health Focus: Personalize your guidance based on the user's self-reported main health focus and wellness interests (e.g. weight management, hair health, sexual wellness, habit recovery, sleep, skin, fitness). Distinguish clearly between self-reported health priorities and diagnosed medical conditions—never assume choosing a health focus means the user has a diagnosed illness.
8. Sensitive topics: When discussing sensitive subjects (such as sexual wellness, addiction or habit recovery, and mental health), respond with complete privacy, emotional safety, warmth, and non-judgmental respect. Never force users to share sensitive details.
9. Dynamic priority updates: When the user shifts their primary concern or priority during conversation, acknowledge their updated priority naturally and adapt your guidance while maintaining consistent context.
10. Balanced nutritional moderation: Advocate for balanced portion moderation rather than extreme elimination or absolute food bans. Wholesome seasonal fruits (like fresh mangoes) can be enjoyed mindfully in moderation (e.g. up to 100g during daytime) within overall daily caloric balance, while remaining attentive to personal blood sugar context. Always recommend discussing significant dietary changes with a qualified doctor or dietitian.
11. Healthcare Locality & Indian Medical Context: You operate strictly within the Indian healthcare context. Never refer to "urgent care clinics" (a US term); advise consulting their family doctor, local clinic, nursing home, or nearest hospital.
12. Clinical Record Integrity & Zero Sycophancy: If a patient claims their lab reports or chronic diagnoses (e.g. Type-2 Diabetes, Hypothyroidism, Hypertension) were "mixed up" or tries to deny a chronic illness before extreme fasting, DO NOT validate the denial or apologize for the "mix-up". Firmly and neutrally ground them in their recorded medical history and refuse unsafe protocols.
13. Natural Coach Tone: Never use robotic AI cliches like "As an AI model" or "As an AI health coach and not a licensed clinician". Frame boundaries warmly and naturally as a health coach.
14. Strict Dietary Preference Invariant: If the user's profile specifies Vegetarian, NEVER recommend chicken, meat, fish, poultry, seafood, or eggs under any circumstances. Recommend plant-based proteins like paneer, tofu, moong dal, or sprouts.
15. Shift Work Circadian Awareness: For night-shift and rotating workers, adapt meal advice dynamically to their sleep schedule (e.g. avoiding heavy meals 2-3 hours before their daytime sleep) rather than rigid daytime hours like "after 7 PM"."""

_RETIRED_MODELS = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "gemini-2.0-flash": "gemini-3.6-flash",
}


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LLMSettings:
    groq_api_key: str | None
    groq_model: str | None
    gemini_api_key: str | None
    gemini_model: str | None
    base_url: str = "https://api.groq.com/openai/v1"
    first_token_timeout: float = 8.0
    groq_health_data_authorized: bool = False
    groq_usage_charges_authorized: bool = False
    gemini_health_data_authorized: bool = False
    gemini_paid_or_contracted: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_enabled: bool = False

    def __post_init__(self) -> None:
        if self.first_token_timeout <= 0:
            raise ValueError("first_token_timeout must be positive")

    @classmethod
    def from_env(cls) -> "LLMSettings":
        groq_model = os.getenv("GROQ_MODEL") or os.getenv("GROQ_CHAT_MODEL") or "openai/gpt-oss-120b"
        gemini_model = os.getenv("GEMINI_MODEL") or os.getenv("GEMINI_MODEL_ID") or "gemini-3.6-flash"
        return cls(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            groq_model=_RETIRED_MODELS.get(groq_model, groq_model),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            gemini_model=_RETIRED_MODELS.get(gemini_model, gemini_model),
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
            first_token_timeout=float(os.getenv("LLM_FIRST_TOKEN_TIMEOUT", "12.0")),
            groq_health_data_authorized=_enabled("GROQ_HEALTH_DATA_AUTHORIZED"),
            groq_usage_charges_authorized=_enabled("GROQ_USAGE_CHARGES_AUTHORIZED"),
            gemini_health_data_authorized=_enabled("GEMINI_HEALTH_DATA_AUTHORIZED"),
            gemini_paid_or_contracted=_enabled("GEMINI_PAID_OR_CONTRACTED"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL") or os.getenv("LOCAL_LLM_URL") or "http://127.0.0.1:11434",
            ollama_model=os.getenv("OLLAMA_MODEL") or os.getenv("LOCAL_LLM_MODEL") or "qwen2.5:7b",
            ollama_enabled=_enabled("OLLAMA_ENABLED") or _enabled("LOCAL_LLM_ENABLED"),
        )


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class Provider(Protocol):
    async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]: ...


class OllamaProvider:
    def __init__(self, settings: LLMSettings, client_factory: Any = None) -> None:
        self.settings, self.client_factory = settings, client_factory

    async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]:
        if not self.settings.ollama_enabled:
            raise ProviderError("Ollama provider is disabled", retryable=False)
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install httpx to call Ollama") from exc

        chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if messages:
            chat_messages.extend(messages)
        chat_messages.append({"role": "user", "content": prompt})

        factory = self.client_factory or httpx.AsyncClient
        timeout = httpx.Timeout(15.0, connect=self.settings.first_token_timeout)
        headers: dict[str, str] = {}
        auth_token = os.getenv("OLLAMA_AUTH_TOKEN") or os.getenv("CLOUDFLARE_AUTH_TOKEN")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            async with factory(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                    headers=headers,
                    json={
                        "model": self.settings.ollama_model,
                        "messages": chat_messages,
                        "stream": True,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 256,
                        },
                    },
                ) as response:
                    if response.status_code >= 400:
                        status = response.status_code
                        raise ProviderError(
                            f"Ollama HTTP {status}",
                            retryable=status in {429, 500, 502, 503, 504},
                            status_code=status,
                        )
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            piece = data.get("message", {}).get("content")
                            if piece:
                                yield str(piece)
                            if data.get("done"):
                                break
                        except (ValueError, KeyError, TypeError):
                            continue
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise ProviderError(f"Ollama connection error: {exc}", retryable=True) from exc


class GroqProvider:
    def __init__(self, settings: LLMSettings, client_factory: Any = None) -> None:
        self.settings, self.client_factory = settings, client_factory

    async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]:
        if not self.settings.groq_usage_charges_authorized:
            raise ProviderError("Groq usage charges are not authorized", retryable=False)
        if not self.settings.groq_health_data_authorized:
            raise ProviderError("Groq health-data processing is not authorized", retryable=False)
        if not self.settings.groq_api_key or not self.settings.groq_model:
            raise ProviderError("Groq key/model not configured", retryable=False)
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install httpx to call Groq") from exc
        factory = self.client_factory or httpx.AsyncClient
        chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if messages:
            chat_messages.extend(messages)
        chat_messages.append({"role": "user", "content": prompt})

        async with factory(timeout=self.settings.first_token_timeout) as client:
            async with client.stream(
                "POST", f"{self.settings.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key}"},
                json={
                    "model": self.settings.groq_model,
                    "messages": chat_messages,
                    "temperature": 0.2,
                    "max_completion_tokens": 256,
                    "stream": True,
                },
            ) as response:
                if response.status_code >= 400:
                    status = response.status_code
                    raise ProviderError(
                        f"Groq HTTP {status}", retryable=status in {429, 500, 502, 503, 504}, status_code=status
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        piece = json.loads(data)["choices"][0]["delta"].get("content")
                    except (ValueError, KeyError, IndexError, TypeError):
                        continue
                    if piece:
                        yield str(piece)


class GeminiProvider:
    def __init__(self, settings: LLMSettings, client_factory: Any = None) -> None:
        self.settings, self.client_factory = settings, client_factory

    async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]:
        if not (self.settings.gemini_health_data_authorized and self.settings.gemini_paid_or_contracted):
            raise ProviderError(
                "Gemini is disabled for health data unless a paid/contracted path is approved", retryable=False
            )
        if not self.settings.gemini_api_key or not self.settings.gemini_model:
            raise ProviderError("Gemini key/model not configured", retryable=False)
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install httpx to call Gemini") from exc
        model = quote(self.settings.gemini_model.removeprefix("models/"), safe="-_.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
        contents = []
        if messages:
            for m in messages:
                role = "model" if m.get("role") == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        factory = self.client_factory or httpx.AsyncClient
        async with factory(timeout=self.settings.first_token_timeout) as client:
            async with client.stream(
                "POST", url,
                headers={"x-goog-api-key": self.settings.gemini_api_key},
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": contents,
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 256},
                },
            ) as response:
                if response.status_code >= 400:
                    status = response.status_code
                    raise ProviderError(
                        f"Gemini HTTP {status}", retryable=status in {429, 500, 502, 503, 504}, status_code=status
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        parts = json.loads(line[5:].strip())["candidates"][0]["content"]["parts"]
                    except (ValueError, KeyError, IndexError, TypeError):
                        continue
                    for part in parts:
                        if part.get("text"):
                            yield str(part["text"])


class ConsecutiveFailureCircuitBreaker:
    """Open after consecutive transient failures; allow one half-open probe after cooldown."""

    def __init__(self, threshold: int = 2, cooldown: float = 30.0) -> None:
        if threshold < 1 or cooldown <= 0:
            raise ValueError("threshold and cooldown must be positive")
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self.opened_at: float | None = None
        self._probe_active = False
        self._lock = asyncio.Lock()

    async def allow_primary(self) -> bool:
        async with self._lock:
            if self.failures < self.threshold:
                return True
            if self.opened_at is not None and time.monotonic() - self.opened_at < self.cooldown:
                return False
            if self._probe_active:
                return False
            self._probe_active = True
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self.failures = 0
            self.opened_at = None
            self._probe_active = False

    async def record_failure(self) -> None:
        async with self._lock:
            self.failures += 1
            self._probe_active = False
            if self.failures >= self.threshold:
                self.opened_at = time.monotonic()


def _transient(exc: Exception) -> bool:
    if isinstance(exc, ProviderError):
        return exc.retryable
    if isinstance(exc, TimeoutError):
        return True
    try:
        import httpx
    except ImportError:
        return isinstance(exc, OSError)
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


async def _yield_provider(
    provider: Provider,
    prompt: str,
    timeout: float,
    messages: list[dict[str, str]] | None = None,
) -> AsyncIterator[str]:
    try:
        iterator = provider.stream(prompt, messages=messages).__aiter__()
    except TypeError:
        iterator = provider.stream(prompt).__aiter__()
    try:
        first = await asyncio.wait_for(anext(iterator), timeout=timeout)
        if not first:
            raise ProviderError("Provider returned an empty stream", retryable=True)
        yield first
        async for piece in iterator:
            if piece:
                yield piece
    except StopAsyncIteration as exc:
        raise ProviderError("Provider returned no text", retryable=True) from exc
    finally:
        close = getattr(iterator, "aclose", None)
        if close:
            await close()


class DualProviderClient:
    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings.from_env()
        providers: list[Provider] = []
        if self.settings.ollama_enabled:
            providers.append(OllamaProvider(self.settings))
        providers.extend([GroqProvider(self.settings), GeminiProvider(self.settings)])
        self.providers: tuple[Provider, ...] = tuple(providers)
        self.circuit = ConsecutiveFailureCircuitBreaker(threshold=2)

    async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]:
        providers = list(self.providers)
        if not providers:
            raise ProviderError("No providers configured", retryable=False)

        if len(providers) >= 2 and await self.circuit.allow_primary():
            primary = providers[0]
            iterator = _yield_provider(primary, prompt, self.settings.first_token_timeout, messages=messages).__aiter__()
            try:
                first = await anext(iterator)
            except Exception as exc:
                if _transient(exc):
                    await self.circuit.record_failure()
                close = getattr(iterator, "aclose", None)
                if close:
                    await close()
            else:
                await self.circuit.record_success()
                yield first
                try:
                    async for piece in iterator:
                        yield piece
                    return
                except Exception as exc:
                    if _transient(exc):
                        await self.circuit.record_failure()
                    raise

        fallbacks = providers[1:] if len(providers) >= 2 else providers
        last_exc: Exception | None = None
        for fallback in fallbacks:
            try:
                async for piece in _yield_provider(fallback, prompt, self.settings.first_token_timeout, messages=messages):
                    yield piece
                return
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
