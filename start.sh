#!/usr/bin/env bash
# Starts the API (which launches the three MCP agent servers) and the frontend.
set -e
cd "$(dirname "$0")"
(cd backend && uvicorn cartlog.api:app --port 8000) &
API_PID=$!
trap 'kill $API_PID' EXIT
cd frontend && npm run dev
