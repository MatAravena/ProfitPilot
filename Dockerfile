# Single-container ProfitPilot: the API serves the built frontend on one port.
# Used by docker/docker-compose.host.yml (always-on host). Dev still runs `npm run start`.

# ── Stage 1: build the frontend ───────────────────────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: backend + built frontend ─────────────────────────────────────────
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST_DIR=/app/frontend_dist
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend /fe/dist /app/frontend_dist

# Non-root: the Builder sandbox runs user-supplied code in this container.
RUN useradd --uid 1000 --create-home app \
    && mkdir -p /data /backups \
    && chown app:app /data /backups
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"

# One worker on purpose: the strategy executor is an in-process singleton.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
