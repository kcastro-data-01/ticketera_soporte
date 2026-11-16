"""Dónde corre la app: Docker/local (por defecto) o publicada (Vercel, Render…).

Vercel define ``VERCEL=1`` en todas sus funciones y Render ``RENDER=true`` en
sus servicios. En cualquier otro servidor la versión publicada se marca con
``MODO_PRODUCCION=1`` (render.yaml también la pone, por las dudas). En todos los
casos cambian los mismos valores por defecto (IA apagada, correo por cron,
sin /docs, solo Graph, JWT_SECRET_KEY obligatoria…); cada uno se puede forzar
con su propia variable.
"""

import os


def activo(valor: str | None) -> bool:
    """``1``, ``true``, ``sí``… encendido; lo demás (o vacío), apagado."""
    return (valor or "").strip().lower() in ("1", "true", "si", "sí", "yes")


def en_vercel(env=None) -> bool:
    """Solo Vercel (``VERCEL`` definida por la plataforma)."""
    env = os.environ if env is None else env
    return bool((env.get("VERCEL") or "").strip())


def en_produccion(env=None) -> bool:
    """La versión publicada: Vercel, Render o ``MODO_PRODUCCION=1``."""
    env = os.environ if env is None else env
    return en_vercel(env) or activo(env.get("RENDER")) or activo(env.get("MODO_PRODUCCION"))
