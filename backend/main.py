"""FastAPI application entry point for the support ticket system."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.database import init_db
from backend.routers.tickets import router as tickets_router
from backend.routers.users import router as users_router


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


app.include_router(tickets_router)
app.include_router(users_router)
