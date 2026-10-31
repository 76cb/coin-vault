#!/usr/bin/env bash
# Starts a throwaway Coin Vault (SQLite, temp media) serving the built frontend, for Playwright.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$HERE/../backend"
WORK="$(mktemp -d)"
export CV_DATABASE_URL="sqlite:///$WORK/e2e.db"
export CV_MEDIA_ROOT="$WORK/media"
export CV_FRONTEND_DIST="$HERE/dist"
export CV_LOG_JSON=false
export CV_LOG_LEVEL=WARNING
# No outbound price polling during tests; a fixed throwaway key so provider keys can be saved.
export CV_SCHEDULER_ENABLED=false
export CV_ENCRYPTION_KEY="${CV_ENCRYPTION_KEY:-MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=}"
PY="${CV_PYTHON:-$BACKEND/.venv/bin/python}"
cd "$BACKEND"
echo "${E2E_PASSWORD:-e2e-password-123}" | "$PY" -m app.cli create-admin --username "${E2E_USER:-admin}" --password-stdin >/dev/null
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "${E2E_PORT:-8765}"
