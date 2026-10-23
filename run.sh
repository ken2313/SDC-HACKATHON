#!/usr/bin/env bash
# Starts everything for Replit: FastAPI backend (port 8000) + Vite frontend (port 5173).
# Windows + VSCode users: you do not need this file. Use the two-terminal steps in the README.
set -e
cd "$(dirname "$0")"

# Python packages. Replit usually installs them itself, and its Python does not allow a
# plain "pip install" (error: externally-managed-environment). So only install when they
# are missing, and then into the user folder Replit provides.
if python -c "import fastapi, sqlalchemy, uvicorn, dotenv, pydantic" 2>/dev/null; then
  echo "Python packages already installed."
else
  echo "Installing Python packages..."
  python -m pip install -q --user -r backend/requirements.txt \
    || python -m pip install -q -r backend/requirements.txt
fi

# Frontend packages (only the first time, or when package.json changed)
(cd frontend && npm install --no-audit --no-fund)

# This app uses its own SQLite file (backend/data). Make sure the folder exists.
mkdir -p backend/data

# Stop both servers together when this script ends
trap 'kill 0' EXIT

(cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000) &
(cd frontend && npm run dev) &
wait
