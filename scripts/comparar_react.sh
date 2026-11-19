#!/usr/bin/env bash
# Compara la pantalla de Tickets actual con la de React (capturas con
# Playwright en escritorio y celular, claro y oscuro). Antes: npm run build
# en frontend-react/. Uso: scripts/comparar_react.sh [Administrador Técnico Solicitante]
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -v "$PWD":/src -w /src mcr.microsoft.com/playwright/python:v1.48.0-jammy \
  bash -c 'pip install -q --disable-pip-version-check playwright==1.48.0 pillow \
    && python scripts/comparar/comparar_react.py "$@"' _ "$@"
