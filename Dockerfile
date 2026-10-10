# ComplianceRadar: API + built frontend in one image (Render free plan, see DEPLOY.md).

# --- stage 1: build the frontend ---
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# No VITE_API_BASE_URL: the UI calls the API on its own origin.
RUN npm run build

# --- stage 2: Python API serving the built frontend ---
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/tmp/compliance.sqlite \
    BROWSER_FALLBACK=0 \
    LIVE_DECISIONS_EPHEMERAL=1 \
    RESET_DB_ON_START=1 \
    CHECK_RATE_LIMIT_PER_MINUTE=5 \
    MAX_CONCURRENT_CHECKS=2 \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY eval/replay_stored.json eval/replay_stored.json
COPY --from=frontend /app/frontend/dist frontend/dist
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app
EXPOSE 10000
# Render sets PORT; one worker (jobs, rate limiter and SQLite live in one process).
CMD ["sh", "-c", "exec uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
