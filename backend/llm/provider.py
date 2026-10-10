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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable
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
    """HTTP 429, 5xx or timeout: retried with backoff, then a fallback provider may succeed."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMTimeoutError(LLMTransientError):
    """The per-check deadline was reached (slow provider or rate-limit waits)."""


class LLMResponseError(LLMError):
    """The model did not return valid JSON for the schema, even after one retry."""


@dataclass
class RateLimits:
    """Pacing for real API calls (cache hits are never delayed)."""
    max_retries: int = 3          # extra attempts on 429/5xx/timeout before giving up
    backoff_seconds: float = 2.0  # wait = backoff * 2**attempt when no Retry-After is sent
    max_wait_seconds: float = 60.0  # a longer Retry-After is not waited out: fail over
    min_interval_seconds: float = 1.0  # minimum gap between two calls to this provider
    fallback_after_seconds: float = 30.0  # with a fallback configured, longer waits switch

    @classmethod
    def from_env(cls) -> "RateLimits":
        d = cls()
        return cls(
            max_retries=int(os.getenv("LLM_MAX_RETRIES") or d.max_retries),
            backoff_seconds=float(os.getenv("LLM_BACKOFF_SECONDS") or d.backoff_seconds),
            max_wait_seconds=float(os.getenv("LLM_MAX_WAIT_SECONDS") or d.max_wait_seconds),
            min_interval_seconds=float(os.getenv("LLM_MIN_INTERVAL_SECONDS")
                                       or d.min_interval_seconds),
            fallback_after_seconds=float(os.getenv("LLM_FALLBACK_AFTER_SECONDS")
                                         or d.fallback_after_seconds))


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After is either delta-seconds or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


@dataclass
class RawCompletion:
    text: str
    input_tokens: int | None
    output_tokens: int | None


def _fmt_tokens(n: int | None) -> str:
    return "no data" if n is None else str(n)


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

    def __init__(self, db_path: Path | str | None = None, limits: RateLimits | None = None):
        self.db_path = db_path
        self.limits = limits or RateLimits()
        self.last_raw: RawCompletion | None = None  # in memory only, for dry-run printouts
        self._last_call = 0.0
        self._sleep = time.sleep
        # Set by the caller per check: progress callback and a time.monotonic() deadline.
        self.on_event: Callable[[str], None] | None = None
        self.deadline: float | None = None
        # Not before this time.monotonic() (set from Retry-After); used by FallbackProvider.
        self.cooldown_until = 0.0
        # Separate cache entries (e.g. for a consistency re-run that must not reuse answers).
        self.cache_namespace = ""

    def _emit(self, msg: str) -> None:
        if self.on_event:
            self.on_event(msg)

    def remaining(self) -> float | None:
        return None if self.deadline is None else self.deadline - time.monotonic()

    def _check_deadline(self) -> None:
        left = self.remaining()
        if left is not None and left <= 0:
            raise LLMTimeoutError(f"{self.name}: check timeout reached")

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call
        if self._last_call and gap < self.limits.min_interval_seconds:
            self._sleep(self.limits.min_interval_seconds - gap)
        self._last_call = time.monotonic()

    def _call_with_backoff(self, prompt: str, schema: dict, key: str) -> tuple[RawCompletion, float]:
        """One logical call: retries 429/5xx/timeouts with Retry-After or exponential backoff."""
        for attempt in range(self.limits.max_retries + 1):
            self._check_deadline()
            self._throttle()
            self._emit(f"calling LLM {self.model} (attempt {attempt + 1}, "
                       f"~{int(len(prompt) / 2.5)} prompt tokens est.)")
            t0 = time.perf_counter()
            try:
                raw = self._complete(prompt, schema)
                self._emit(f"LLM answered in {time.perf_counter() - t0:.1f} s: "
                           f"{_fmt_tokens(raw.input_tokens)} input / "
                           f"{_fmt_tokens(raw.output_tokens)} output tokens")
                return raw, (time.perf_counter() - t0) * 1000
            except LLMTransientError as exc:
                self._log(input_tokens=None, output_tokens=None, ok=False, cache_hit=False,
                          duration_ms=(time.perf_counter() - t0) * 1000, error=str(exc),
                          cache_key=key)
                if isinstance(exc, LLMTimeoutError):
                    raise
                wait = (exc.retry_after if exc.retry_after is not None
                        else self.limits.backoff_seconds * 2 ** attempt)
                if exc.retry_after is not None:
                    self.cooldown_until = time.monotonic() + exc.retry_after
                if attempt == self.limits.max_retries or wait > self.limits.max_wait_seconds:
                    self._emit(f"{exc}; not waiting {wait:.0f} s (limit "
                               f"{self.limits.max_wait_seconds:.0f} s)")
                    raise
                left = self.remaining()
                if left is not None and wait >= left:
                    raise LLMTimeoutError(f"{self.name}: waiting {wait:.0f} s would exceed the "
                                          f"check timeout ({left:.0f} s left)",
                                          retry_after=exc.retry_after) from None
                kind = "rate limited" if "429" in str(exc) else str(exc)
                self._emit(f"{kind}, waiting {wait:.0f} s")
                self._sleep(wait)
            except LLMError as exc:
                self._log(input_tokens=None, output_tokens=None, ok=False, cache_hit=False,
                          duration_ms=(time.perf_counter() - t0) * 1000, error=str(exc),
                          cache_key=key)
                raise
        raise AssertionError("unreachable")  # pragma: no cover

    @abstractmethod
    def _complete(self, prompt: str, schema: dict) -> RawCompletion:
        """One raw call. Raise LLMTransientError for 429/5xx/timeouts, LLMError otherwise."""

    def _log(self, *, input_tokens, output_tokens, duration_ms, ok, cache_hit, error=None,
             cache_key=None):
        with db.connect(self.db_path) as conn:
            db.log_llm_call(conn, provider=self.name, model=self.model,
                            input_tokens=input_tokens, output_tokens=output_tokens,
                            duration_ms=duration_ms, ok=ok, cache_hit=cache_hit,
                            error=error[:500] if error else None, cache_key=cache_key)

    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict:
        db.init_db(self.db_path)
        schema_json = _schema_dict(schema)
        key = db.llm_cache_key(self.name, self.model, prompt, schema_json,
                               self.cache_namespace)
        started = time.perf_counter()
        with db.connect(self.db_path) as conn:
            cached = db.llm_cache_get(conn, key)
        if cached is not None:
            self._emit("LLM answer from cache")
            self._log(input_tokens=None, output_tokens=None, ok=True, cache_hit=True,
                      duration_ms=(time.perf_counter() - started) * 1000, cache_key=key)
            self.last_raw = None
            return schema.model_validate(cached).model_dump()

        last_problem = None
        for attempt in range(2):  # first call + one retry on invalid JSON
            attempt_prompt = prompt if attempt == 0 else prompt + RETRY_NOTE
            raw, duration = self._call_with_backoff(attempt_prompt, schema_json, key)
            self.last_raw = raw
            try:
                result = schema.model_validate(_extract_json(raw.text)).model_dump()
            except (ValueError, ValidationError) as exc:
                last_problem = f"{type(exc).__name__}: {str(exc)[:300]}"
                self._log(input_tokens=raw.input_tokens, output_tokens=raw.output_tokens,
                          duration_ms=duration, ok=False, cache_hit=False, cache_key=key,
                          error=f"invalid JSON (attempt {attempt + 1}): {last_problem}")
                continue
            self._log(input_tokens=raw.input_tokens, output_tokens=raw.output_tokens,
                      duration_ms=duration, ok=True, cache_hit=False, cache_key=key)
            with db.connect(self.db_path) as conn:
                db.llm_cache_put(conn, key, self.name, self.model, result)
            return result
        raise LLMResponseError(
            f"{self.name}/{self.model} returned invalid JSON for {schema.__name__} twice: "
            f"{last_problem}")


def provider_name(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    return f"openai-compatible:{urlparse(base_url).netloc or base_url}"


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str, model: str, *,
                 timeout: float = 60.0, json_mode: bool = True,
                 db_path: Path | str | None = None, transport: httpx.BaseTransport | None = None,
                 limits: RateLimits | None = None, max_output_tokens: int | None = None,
                 reasoning_effort: str | None = None, seed: int | None = None):
        super().__init__(db_path, limits)
        missing = [n for n, v in (("base_url", base_url), ("api_key", api_key),
                                  ("model", model)) if not v]
        if missing:
            raise LLMConfigError(f"LLM provider is missing: {', '.join(missing)}")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.name = provider_name(self.base_url)
        self.json_mode = json_mode
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.seed = seed
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
        if self.max_output_tokens:
            body["max_tokens"] = self.max_output_tokens
        if self.seed is not None:
            body["seed"] = self.seed  # best-effort determinism where the provider supports it
        if self.reasoning_effort:
            # Only for models that accept it (set per slot in .env, e.g. gpt-oss on Groq).
            body["reasoning_effort"] = self.reasoning_effort
        left = self.remaining()
        timeout = self.timeout if left is None else max(1.0, min(self.timeout, left))
        try:
            r = self._client.post(f"{self.base_url}/chat/completions", json=body,
                                  headers={"Authorization": f"Bearer {self._api_key}"},
                                  timeout=timeout)
        except httpx.TimeoutException as exc:
            if self.remaining() is not None and self.remaining() <= 1:
                raise LLMTimeoutError(f"{self.name}: check timeout reached during the call") \
                    from None
            raise LLMTransientError(f"{self.name}: timeout ({type(exc).__name__})") from None
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name}: request failed ({type(exc).__name__})") from None
        if r.status_code == 429 or r.status_code >= 500:
            raise LLMTransientError(f"{self.name}: HTTP {r.status_code}",
                                    retry_after=parse_retry_after(r.headers.get("retry-after")))
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
    """Try providers in order; move to the next one on 429/5xx/timeout, or when a rate-limit
    wait would exceed `fallback_after_seconds`. A provider still cooling down after a 429
    (Retry-After) is skipped while another one is available."""

    def __init__(self, providers: list[LLMProvider], fallback_after_seconds: float | None = None):
        if not providers:
            raise LLMConfigError("FallbackProvider needs at least one provider")
        super().__init__(providers[0].db_path)
        self.providers = providers
        self.name = "fallback(" + ",".join(p.name for p in providers) + ")"
        self.model = providers[0].model
        if fallback_after_seconds is not None:
            for p in providers[:-1]:
                p.limits.max_wait_seconds = min(p.limits.max_wait_seconds,
                                                fallback_after_seconds)

    def _complete(self, prompt: str, schema: dict) -> RawCompletion:  # pragma: no cover
        raise NotImplementedError("FallbackProvider delegates complete_json")

    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict:
        errors = []
        now = time.monotonic()
        ready = [p for p in self.providers if p.cooldown_until <= now]
        order = ready + [p for p in self.providers if p not in ready]
        for i, p in enumerate(order):
            p.on_event, p.deadline = self.on_event, self.deadline
            p.cache_namespace = self.cache_namespace
            if i > 0:
                self._emit(f"switching to fallback model {p.model}")
            try:
                result = p.complete_json(prompt, schema)
                self.last_raw = p.last_raw
                self.last_provider = p
                return result
            except LLMTimeoutError:
                raise
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
    limits = RateLimits.from_env()
    json_mode = (os.getenv("LLM_JSON_MODE") or "1") != "0"
    primary = _slot("LLM_")
    missing = [f"LLM_{k}" for k, v in primary.items() if not v]
    if missing:
        raise LLMConfigError(
            f"{', '.join(missing)} not set in .env. Fill LLM_BASE_URL, LLM_API_KEY and "
            f"LLM_MODEL (see .env.example); for a local Ollama any non-empty key works.")
    providers: list[LLMProvider] = [OpenAICompatibleProvider(
        primary["BASE_URL"], primary["API_KEY"], primary["MODEL"], timeout=timeout,
        json_mode=json_mode, db_path=db_path, transport=transport, limits=limits,
        **_call_options("LLM_"))]
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
            json_mode=json_mode, db_path=db_path, transport=transport,
            limits=RateLimits.from_env(), **_call_options(f"LLM_FALLBACK_{n}_")))
        n += 1
    if len(providers) == 1:
        return providers[0]
    return FallbackProvider(providers, fallback_after_seconds=limits.fallback_after_seconds)


def _call_options(prefix: str) -> dict:
    """max_output_tokens / reasoning_effort for one slot; a fallback slot inherits the
    primary's max tokens but not its reasoning effort (models differ)."""
    max_out = (os.getenv(f"{prefix}MAX_OUTPUT_TOKENS") or os.getenv("LLM_MAX_OUTPUT_TOKENS")
               or "").strip()
    effort = (os.getenv(f"{prefix}REASONING_EFFORT") or "").strip()
    seed = (os.getenv(f"{prefix}SEED") or os.getenv("LLM_SEED") or "").strip()
    return {"max_output_tokens": int(max_out) if max_out else None,
            "reasoning_effort": effort or None,
            "seed": int(seed) if seed else None}


def _env_slots() -> list[str]:
    prefixes, n = ["LLM_"], 1
    while any(_slot(f"LLM_FALLBACK_{n}_").values()):
        prefixes.append(f"LLM_FALLBACK_{n}_")
        n += 1
    return prefixes


def prices_from_env() -> dict[tuple[str, str], tuple[float, float] | None]:
    """USD per 1M input/output tokens per (provider name, model); None when not set."""
    prices = {}
    for prefix in _env_slots():
        slot = _slot(prefix)
        if not slot["BASE_URL"] or not slot["MODEL"]:
            continue
        pin = os.getenv(f"{prefix}PRICE_INPUT_PER_MTOK", "").strip()
        pout = os.getenv(f"{prefix}PRICE_OUTPUT_PER_MTOK", "").strip()
        prices[(provider_name(slot["BASE_URL"]), slot["MODEL"])] = (
            (float(pin), float(pout)) if pin and pout else None)
    return prices


def cost_of(rows: list[dict]) -> float | str:
    """Cost of logged API calls (cache hits are free) from token counts and .env prices.

    Returns "not set" if a call's provider has no price, "no data" if tokens are missing.
    """
    prices = prices_from_env()
    total = 0.0
    for r in rows:
        if r["cache_hit"] or (r["input_tokens"] is None and r["output_tokens"] is None):
            continue  # cache hit, or a failed request that returned no usage
        price = prices.get((r["provider"], r["model"]))
        if price is None:
            return "not set"
        if r["input_tokens"] is None or r["output_tokens"] is None:
            return "no data"
        total += r["input_tokens"] / 1e6 * price[0] + r["output_tokens"] / 1e6 * price[1]
    return round(total, 6)
