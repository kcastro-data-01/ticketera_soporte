# Official Python image compatible with the pinned requirements
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first so the layer is cached between builds
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the application needs at runtime: backend (tests excluded by
# .dockerignore) and the static frontend served by FastAPI.
COPY backend/ backend/
COPY frontend/ frontend/

EXPOSE 8000

# API + frontend in a single process, reachable from outside the container
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
