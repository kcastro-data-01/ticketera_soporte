"""Dónde corre la app: Docker/local (por defecto) o Vercel.

Vercel define ``VERCEL=1`` en todas sus funciones. Ahí cambian algunos
valores por defecto (IA apagada, correo por cron, sin /docs); cada uno se
puede forzar con su propia variable.
"""

import os


def en_vercel(env=None) -> bool:
    env = os.environ if env is None else env
    return bool((env.get("VERCEL") or "").strip())


def activo(valor: str | None) -> bool:
    """``1``, ``true``, ``sí``… encendido; lo demás (o vacío), apagado."""
    return (valor or "").strip().lower() in ("1", "true", "si", "sí", "yes")
