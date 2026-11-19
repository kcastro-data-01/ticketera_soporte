# --- Etapa 1: compila la app React (frontend-react/ → dist/) ---
# El resultado lo sirve FastAPI en la raíz (backend/frontend_react.py).
FROM node:22-slim AS react
WORKDIR /src/frontend-react
COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend-react/ ./
RUN npm run build

# --- Etapa 2: la app (API + build de React) ---
# Official Python image compatible with the pinned requirements
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first so the layer is cached between builds
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the application needs at runtime: backend (tests excluded by
# .dockerignore) and the compiled frontend served by FastAPI.
COPY backend/ backend/
COPY --from=react /src/frontend-react/dist/ frontend-react/dist/

# Docker Compose uses 8000; Render sets PORT (10000) and checks /health.
ENV PORT=8000
EXPOSE 8000

# API + frontend in a single process, reachable from outside the container.
# exec: uvicorn is PID 1 and gets SIGTERM (clean shutdown of the mail thread).
# --proxy-headers: behind Render's proxy the app sees https and the real client.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips='*'"]
