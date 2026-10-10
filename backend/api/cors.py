"""Allowed CORS origins from CORS_ORIGINS (comma-separated).

Unset or empty -> the local Vite dev/e2e origins below. In production set it to the hosted
frontend origin(s), e.g. CORS_ORIGINS=https://wiut-finals.vercel.app. A wildcard is refused:
origins are always listed explicitly.
"""

import os
from urllib.parse import urlsplit

DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]


def parse_origins(raw: str | None) -> list[str]:
    items = [o.strip().rstrip("/") for o in (raw or "").split(",") if o.strip()]
    if not items:
        return list(DEFAULT_ORIGINS)
    out: list[str] = []
    for o in items:
        if "*" in o:
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
        p = urlsplit(o)
        if p.scheme not in ("http", "https") or not p.hostname or p.path or p.query:
            raise ValueError(f"CORS_ORIGINS entry is not an origin (scheme://host[:port]): {o!r}")
        if o not in out:
            out.append(o)
    return out


def cors_origins() -> list[str]:
    return parse_origins(os.getenv("CORS_ORIGINS"))
