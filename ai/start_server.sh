#!/usr/bin/env bash
# Start the AI inference server on the RunPod Pod.
# Usage (in the Pod terminal):  bash /workspace/SDC-HACKATHON/ai/start_server.sh
set -e
cd "$(dirname "$0")"
pip install -q fastapi uvicorn pandas numpy   # container packages reset when the Pod stops
if [ -z "$INFERENCE_TOKEN" ]; then
  echo "WARNING: INFERENCE_TOKEN is not set"
fi
pkill -f "uvicorn server:app" || true          # stop an old server if one is running
nohup uvicorn server:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
sleep 5
curl -s http://localhost:8000/health && echo