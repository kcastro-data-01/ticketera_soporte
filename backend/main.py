"""FastAPI application entry point for the support ticket system."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.database import init_db


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create the database schema when the application starts."""
    init_db()
    yield


app = FastAPI(
    title="API de Ticketera de Soporte",
    description="API del sistema de ticketera de soporte (práctica de pasantes).",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["Salud"])
def health_check() -> dict[str, str]:
    """Return the status of the service (health check)."""
    return {"status": "ok"}
