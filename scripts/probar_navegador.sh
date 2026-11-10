#!/usr/bin/env bash
# Pruebas del frontend en un navegador de verdad (Chromium headless con
# Playwright): frontend/tests/navegador. Usa la imagen oficial de Playwright
# (trae los navegadores); instala pytest y playwright en el contenedor.
#
#   scripts/probar_navegador.sh            # todas
#   scripts/probar_navegador.sh -k teclado # una parte
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -v "$PWD":/src -w /src mcr.microsoft.com/playwright/python:v1.48.0-jammy \
  bash -c 'pip install -q --disable-pip-version-check pytest playwright==1.48.0 \
    && python -m pytest -q -p no:cacheprovider frontend/tests/navegador "$@"' _ "$@"
