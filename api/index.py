"""Entrada de la función de Vercel: la misma app FastAPI que en Docker.

vercel.json manda aquí todo ``/api/*`` y ``/health``; el frontend lo sirve
la CDN de Vercel desde ``frontend/``.
"""

from backend.main import app  # noqa: F401
