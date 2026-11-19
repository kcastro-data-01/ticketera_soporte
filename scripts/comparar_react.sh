#!/usr/bin/env bash
# Compara las pantallas actuales con las de React (Tickets, Detalle, Nuevo ticket; capturas con
# Playwright en escritorio y celular, claro y oscuro). Antes: npm run build
# en frontend-react/. Uso: scripts/comparar_react.sh [Administrador Técnico Solicitante] [--paginas tickets,detalle,detalle-ia,detalle-cerrado,crear]
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -v "$PWD":/src -w /src mcr.microsoft.com/playwright/python:v1.48.0-jammy \
  bash -c 'pip install -q --disable-pip-version-check playwright==1.48.0 pillow \
    && python scripts/comparar/comparar_react.py "$@"' _ "$@"
