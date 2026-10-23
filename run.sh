#!/usr/bin/env bash
# Starts everything for Replit: FastAPI backend (port 8000) + Vite frontend (port 5173).
# Windows + VSCode users: you do not need this file. Use the two-terminal steps in the README.
set -e
cd "$(dirname "$0")"

python -m pip install -q -r backend/requirements.txt
(cd frontend && npm install --no-audit --no-fund)

# Stop both servers together when this script ends
trap 'kill 0' EXIT

(cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000) &
(cd frontend && npm run dev) &
wait
