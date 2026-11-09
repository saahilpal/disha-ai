from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol
from urllib.parse import quote, urlsplit

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Disha, an empathetic, intelligent personal health coach. Return plain text only without markdown formatting. Never claim to be a doctor, clinician, or human. Do not state prices or paid services unless verified pricing is provided in the current context. Never promise external delivery unless the current context confirms it.

LANGUAGE & VOICE:
- Use the preferred language in <USER_LANGUAGE>: natural Hinglish in Roman script, Hindi in Devanagari, or clear English. If the user clearly switches between these supported languages, follow the language of their latest message.
- In Hinglish, use idiomatic everyday phrasing; do not translate English literally or produce awkward Hindi. Do not copy or restate the user's wording.
- Do not open with a greeting by default. Never say "Namaste" unless the user greets you first and this is the first reply.
- Be warm and direct. Use only as much detail as the question needs; ask one useful follow-up only when needed. No emojis.

CONVERSATIONAL COACHING DISCIPLINE:
- Greet at most once at conversation start. Jump directly into the answer without repeating greetings or echoing the user's question.
- Actively address the user's specific query. Do not bring up unsolicited diets or gym restrictions unless asked.
- Conclude with at most one relevant, caring follow-up check-in.

CLINICAL BOUNDARIES & EVIDENCE GROUNDING:
- Ground health guidance in provided <CLINICAL_GROUNDING> and information the user shared.
- For health, food, nutrition, exercise, sleep, hydration, or habit recommendations, use only relevant content in <CLINICAL_GROUNDING>; if it is NOT_FOUND or irrelevant, do not invent advice.
- Treat <REPORTED_HEALTH_INFORMATION> as user-reported, not independently verified.
- Respect <PEP_PERMISSIONS> only when present; missing medical information does not establish safety.
- Honor a dietary preference only when it is present in the user profile.
- Never guess unstated medical conditions or validate denial of clinically recorded diagnoses.
- For night-shift routines, adapt advice to their personal sleep schedule.
- Warm Indian health coaching context; advise consulting family doctor or nearest hospital for clinical assessments."""

_RETIRED_MODELS = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "gemini-2.0-flash": "gemini-3.6-flash",
}


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {"1", "true", "yes", "on"}


def _is_local_url(url: str) -> bool:
    return urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


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
    local_only: bool = False
    groq_enabled: bool = True
    gemini_enabled: bool = True

    def __post_init__(self) -> None:
        if self.first_token_timeout <= 0:
            raise ValueError("first_token_timeout must be positive")

    @classmethod
    def from_env(cls) -> "LLMSettings":
        groq_model = os.getenv("GROQ_MODEL") or os.getenv("GROQ_CHAT_MODEL") or "openai/gpt-oss-120b"
        gemini_model = os.getenv("GEMINI_MODEL") or os.getenv("GEMINI_MODEL_ID") or "gemini-3.6-flash"
        local_only = _enabled("LOCAL_ONLY")
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
            ollama_enabled=local_only or _enabled("OLLAMA_ENABLED") or _enabled("LOCAL_LLM_ENABLED"),
            local_only=local_only,
            groq_enabled=_enabled("GROQ_ENABLED") if os.getenv("GROQ_ENABLED") is not None else True,
            gemini_enabled=_enabled("GEMINI_ENABLED") if os.getenv("GEMINI_ENABLED") is not None else True,
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
        if self.settings.local_only and not _is_local_url(self.settings.ollama_base_url):
            raise ProviderError("LOCAL_ONLY requires Ollama to use a local endpoint", retryable=False)
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
        auth_token = os.getenv("OLLAMA_AUTH_TOKEN")
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
                        "think": False,
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
        if self.settings.local_only or not self.settings.groq_enabled:
            raise ProviderError("Groq is disabled", retryable=False)
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
        if self.settings.local_only or not self.settings.gemini_enabled:
            raise ProviderError("Gemini is disabled", retryable=False)
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
        if self.settings.local_only:
            providers = [OllamaProvider(self.settings)]
        else:
            providers = []
            if self.settings.groq_enabled:
                providers.append(GroqProvider(self.settings))
            if self.settings.gemini_enabled:
                providers.append(GeminiProvider(self.settings))
            if self.settings.ollama_enabled:
                providers.append(OllamaProvider(self.settings))
        self.providers: tuple[Provider, ...] = tuple(providers)
        self.circuit = ConsecutiveFailureCircuitBreaker(threshold=2)

    async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]:
        providers = list(self.providers)
        if not providers:
            raise ProviderError("No providers configured", retryable=False)

        if len(providers) >= 2 and await self.circuit.allow_primary():
            primary = providers[0]
            iterator = _yield_provider(primary, prompt, self.settings.first_token_timeout, messages=messages).__aiter__()
            early_pieces: list[str] = []
            try:
                first = await anext(iterator)
                early_pieces.append(first)
                try:
                    second = await asyncio.wait_for(anext(iterator), timeout=self.settings.first_token_timeout)
                    early_pieces.append(second)
                except StopAsyncIteration:
                    pass
            except Exception as exc:
                if _transient(exc):
                    await self.circuit.record_failure()
                close = getattr(iterator, "aclose", None)
                if close:
                    await close()
            else:
                await self.circuit.record_success()
                for piece in early_pieces:
                    yield piece
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
