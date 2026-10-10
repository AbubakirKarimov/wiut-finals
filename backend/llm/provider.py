"""LLM access: JSON-only completions validated by pydantic, cached and logged in SQLite.

Providers:
- OpenAICompatibleProvider: any OpenAI-compatible /chat/completions endpoint (Gemini, Groq,
  OpenRouter, Ollama, ...). Configured only from .env: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.
- FallbackProvider: ordered providers; moves on only on HTTP 429, 5xx or a timeout.

No model names or prices live in code. API keys are never logged or printed; prompts are
never logged (only token counts, latency and errors go to llm_calls).
"""

import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from backend import db

load_dotenv()

RETRY_NOTE = ("\n\nYour previous reply was not valid JSON matching the schema. "
              "Reply again with ONLY one JSON object that matches the schema.")
SYSTEM_PROMPT = ("You are a careful legal-compliance assistant. Reply with exactly one JSON "
                 "object that matches the given JSON schema. No prose, no markdown.")


class LLMError(RuntimeError):
    """Base class for LLM failures."""


class LLMConfigError(LLMError):
    """Provider is not configured (e.g. LLM_API_KEY missing in .env)."""


class LLMTransientError(LLMError):
    """HTTP 429, 5xx or timeout: a fallback provider may succeed."""


class LLMResponseError(LLMError):
    """The model did not return valid JSON for the schema, even after one retry."""


@dataclass
class RawCompletion:
    text: str
    input_tokens: int | None
    output_tokens: int | None


def _schema_dict(schema: type[BaseModel]) -> dict:
    return schema.model_json_schema()


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value is not an object")
    return data


class LLMProvider(ABC):
    """Subclasses implement `_complete`; caching, validation, retry and logging live here."""

    name: str
    model: str

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path

    @abstractmethod
    def _complete(self, prompt: str, schema: dict) -> RawCompletion:
        """One raw call. Raise LLMTransientError for 429/5xx/timeouts, LLMError otherwise."""

    def _log(self, *, input_tokens, output_tokens, duration_ms, ok, cache_hit, error=None):
        with db.connect(self.db_path) as conn:
            db.log_llm_call(conn, provider=self.name, model=self.model,
                            input_tokens=input_tokens, output_tokens=output_tokens,
                            duration_ms=duration_ms, ok=ok, cache_hit=cache_hit,
                            error=error[:500] if error else None)

    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict:
        db.init_db(self.db_path)
        schema_json = _schema_dict(schema)
        key = db.llm_cache_key(self.name, self.model, prompt, schema_json)
        started = time.perf_counter()
        with db.connect(self.db_path) as conn:
            cached = db.llm_cache_get(conn, key)
        if cached is not None:
            self._log(input_tokens=None, output_tokens=None, ok=True, cache_hit=True,
                      duration_ms=(time.perf_counter() - started) * 1000)
            return schema.model_validate(cached).model_dump()

        last_problem = None
        for attempt in range(2):  # first call + one retry on invalid JSON
            attempt_prompt = prompt if attempt == 0 else prompt + RETRY_NOTE
            t0 = time.perf_counter()
            try:
                raw = self._complete(attempt_prompt, schema_json)
            except LLMError as exc:
                self._log(input_tokens=None, output_tokens=None, ok=False, cache_hit=False,
                          duration_ms=(time.perf_counter() - t0) * 1000, error=str(exc))
                raise
            duration = (time.perf_counter() - t0) * 1000
            try:
                result = schema.model_validate(_extract_json(raw.text)).model_dump()
            except (ValueError, ValidationError) as exc:
                last_problem = f"{type(exc).__name__}: {str(exc)[:300]}"
                self._log(input_tokens=raw.input_tokens, output_tokens=raw.output_tokens,
                          duration_ms=duration, ok=False, cache_hit=False,
                          error=f"invalid JSON (attempt {attempt + 1}): {last_problem}")
                continue
            self._log(input_tokens=raw.input_tokens, output_tokens=raw.output_tokens,
                      duration_ms=duration, ok=True, cache_hit=False)
            with db.connect(self.db_path) as conn:
                db.llm_cache_put(conn, key, self.name, self.model, result)
            return result
        raise LLMResponseError(
            f"{self.name}/{self.model} returned invalid JSON for {schema.__name__} twice: "
            f"{last_problem}")


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str, model: str, *,
                 timeout: float = 60.0, json_mode: bool = True,
                 db_path: Path | str | None = None, transport: httpx.BaseTransport | None = None):
        super().__init__(db_path)
        missing = [n for n, v in (("base_url", base_url), ("api_key", api_key),
                                  ("model", model)) if not v]
        if missing:
            raise LLMConfigError(f"LLM provider is missing: {', '.join(missing)}")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.name = f"openai-compatible:{urlparse(self.base_url).netloc or self.base_url}"
        self.json_mode = json_mode
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def __repr__(self) -> str:  # never expose the key
        return f"OpenAICompatibleProvider(name={self.name!r}, model={self.model!r})"

    def _complete(self, prompt: str, schema: dict) -> RawCompletion:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt + "\n\nJSON schema:\n" +
                 json.dumps(schema, ensure_ascii=False)},
            ],
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = self._client.post(f"{self.base_url}/chat/completions", json=body,
                                  headers={"Authorization": f"Bearer {self._api_key}"})
        except httpx.TimeoutException as exc:
            raise LLMTransientError(f"{self.name}: timeout ({type(exc).__name__})") from None
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name}: request failed ({type(exc).__name__})") from None
        if r.status_code == 429 or r.status_code >= 500:
            raise LLMTransientError(f"{self.name}: HTTP {r.status_code}")
        if r.status_code >= 400:
            raise LLMError(f"{self.name}: HTTP {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMResponseError(f"{self.name}: unexpected response shape") from None
        usage = data.get("usage") or {}
        return RawCompletion(text=text, input_tokens=usage.get("prompt_tokens"),
                             output_tokens=usage.get("completion_tokens"))


class FallbackProvider(LLMProvider):
    """Try providers in order; move to the next one only on 429/5xx/timeout."""

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise LLMConfigError("FallbackProvider needs at least one provider")
        super().__init__(providers[0].db_path)
        self.providers = providers
        self.name = "fallback(" + ",".join(p.name for p in providers) + ")"
        self.model = providers[0].model

    def _complete(self, prompt: str, schema: dict) -> RawCompletion:  # pragma: no cover
        raise NotImplementedError("FallbackProvider delegates complete_json")

    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict:
        errors = []
        for p in self.providers:
            try:
                return p.complete_json(prompt, schema)
            except LLMTransientError as exc:
                errors.append(str(exc))
        raise LLMTransientError("all providers failed: " + "; ".join(errors))


def _slot(prefix: str) -> dict[str, str]:
    return {k: os.getenv(f"{prefix}{k}", "").strip()
            for k in ("BASE_URL", "API_KEY", "MODEL")}


def provider_from_env(db_path: Path | str | None = None,
                      transport: httpx.BaseTransport | None = None) -> LLMProvider:
    """Build the primary provider plus LLM_FALLBACK_1_*, _2_* ... from the environment."""
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS") or 60)
    json_mode = (os.getenv("LLM_JSON_MODE") or "1") != "0"
    primary = _slot("LLM_")
    missing = [f"LLM_{k}" for k, v in primary.items() if not v]
    if missing:
        raise LLMConfigError(
            f"{', '.join(missing)} not set in .env. Fill LLM_BASE_URL, LLM_API_KEY and "
            f"LLM_MODEL (see .env.example); for a local Ollama any non-empty key works.")
    providers: list[LLMProvider] = [OpenAICompatibleProvider(
        primary["BASE_URL"], primary["API_KEY"], primary["MODEL"], timeout=timeout,
        json_mode=json_mode, db_path=db_path, transport=transport)]
    n = 1
    while True:
        slot = _slot(f"LLM_FALLBACK_{n}_")
        if not any(slot.values()):
            break
        missing = [f"LLM_FALLBACK_{n}_{k}" for k, v in slot.items() if not v]
        if missing:
            raise LLMConfigError(f"incomplete fallback slot: {', '.join(missing)} not set")
        providers.append(OpenAICompatibleProvider(
            slot["BASE_URL"], slot["API_KEY"], slot["MODEL"], timeout=timeout,
            json_mode=json_mode, db_path=db_path, transport=transport))
        n += 1
    return providers[0] if len(providers) == 1 else FallbackProvider(providers)
