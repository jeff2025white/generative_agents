#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/environment/frontend_server"
BACKEND_DIR="$ROOT_DIR/reverie/backend_server"

echo "==================================================="
echo "  Generative Agents - One-Click Autostart (macOS)"
echo "==================================================="

# Ollama performance settings
export OLLAMA_NUM_PARALLEL=3
export OLLAMA_MAX_LOADED_MODELS=2
export OLLAMA_KEEP_ALIVE=-1

find_activate_script() {
  local candidates=(
    "$ROOT_DIR/venv/bin/activate"
    "$ROOT_DIR/.venv/bin/activate"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

escape_applescript_string() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

wait_for_ollama() {
  until curl -fsS "http://localhost:11434/api/tags" >/dev/null 2>&1; do
    sleep 2
  done
}

echo "Cleaning up any previously running servers..."
pkill -f "python.*manage.py runserver" 2>/dev/null || true
pkill -f "python.*reverie.py" 2>/dev/null || true
echo "Cleanup complete."

echo
echo "[Checking Dependencies]"
if ! command -v ollama >/dev/null 2>&1; then
  echo "[ERROR] Ollama is not installed or not in PATH."
  echo "Please install Ollama from https://ollama.com/ and try again."
  read -r -p "Press Enter to exit..."
  exit 1
fi

echo "Checking Ollama server status..."
if ! curl -fsS "http://localhost:11434/api/tags" >/dev/null 2>&1; then
  echo "Ollama server is not running. Starting Ollama in the background..."
  nohup ollama serve >/tmp/generative_agents_ollama.log 2>&1 &
  echo "Waiting for Ollama server to spin up..."
  wait_for_ollama
  echo "Ollama server started successfully!"
else
  echo "Ollama server is already running."
fi

echo
echo "[Checking Ollama Configuration]"
echo "---------------------------------------------------"
echo "  OLLAMA_NUM_PARALLEL      = $OLLAMA_NUM_PARALLEL"
echo "  OLLAMA_KEEP_ALIVE        = $OLLAMA_KEEP_ALIVE"
echo "  OLLAMA_MAX_LOADED_MODELS = $OLLAMA_MAX_LOADED_MODELS"
echo "---------------------------------------------------"

echo
echo "[Checking Models]"
echo "Checking local decision model (deepseek-r1:7b)..."
if ! ollama list | grep -qi "deepseek-r1:7b"; then
  echo "[WARN] Local decision model deepseek-r1:7b is missing. Pulling model..."
  ollama pull deepseek-r1:7b
else
  echo "  [OK] deepseek-r1:7b"
fi

echo "Checking embedding model (nomic-embed-text)..."
if ! ollama list | grep -qi "nomic-embed-text"; then
  echo "[WARN] Embedding model nomic-embed-text is missing. Pulling model..."
  ollama pull nomic-embed-text
else
  echo "  [OK] nomic-embed-text"
fi

echo
echo "[GPU Status]"
if command -v system_profiler >/dev/null 2>&1; then
  system_profiler SPDisplaysDataType | grep -E "Chipset Model|Type|Metal" || true
else
  echo "[WARN] system_profiler not found. Cannot check GPU status."
fi

echo
echo "[Currently Loaded Models]"
ollama ps || true

SIM_NAME="sim_$(date +"%Y%m%d_%H%M%S")"
ACTIVATE_SCRIPT="$(find_activate_script || true)"

if [[ -n "$ACTIVATE_SCRIPT" ]]; then
  ENV_SETUP="source \"$ACTIVATE_SCRIPT\""
  echo
  echo "[Python Environment]"
  echo "Using virtual environment: $ACTIVATE_SCRIPT"
else
  ENV_SETUP="echo '[WARN] No venv/.venv found, using system Python.'"
  echo
  echo "[WARN] No venv/.venv found under project root. The new Terminal windows will use system Python."
fi

FRONTEND_CMD="cd \"$FRONTEND_DIR\"; export OLLAMA_NUM_PARALLEL=$OLLAMA_NUM_PARALLEL OLLAMA_MAX_LOADED_MODELS=$OLLAMA_MAX_LOADED_MODELS OLLAMA_KEEP_ALIVE=$OLLAMA_KEEP_ALIVE; $ENV_SETUP; python manage.py runserver"
BACKEND_CMD="cd \"$BACKEND_DIR\"; export OLLAMA_NUM_PARALLEL=$OLLAMA_NUM_PARALLEL OLLAMA_MAX_LOADED_MODELS=$OLLAMA_MAX_LOADED_MODELS OLLAMA_KEEP_ALIVE=$OLLAMA_KEEP_ALIVE; $ENV_SETUP; python reverie.py base_the_ville_isabella_maria_klaus \"$SIM_NAME\" 8640"
FRONTEND_CMD_ESCAPED="$(escape_applescript_string "$FRONTEND_CMD")"
BACKEND_CMD_ESCAPED="$(escape_applescript_string "$BACKEND_CMD")"

echo
echo "[1/2] Launching Django Frontend Server..."
osascript <<EOF
tell application "Terminal"
  activate
  do script "$FRONTEND_CMD_ESCAPED"
end tell
EOF

sleep 3

echo "[2/2] Launching Reverie Backend Server (Auto-running 8640 steps)..."
echo "Running simulation: base_the_ville_isabella_maria_klaus -> $SIM_NAME"
osascript <<EOF
tell application "Terminal"
  do script "$BACKEND_CMD_ESCAPED"
end tell
EOF

echo
echo "==================================================="
echo "  All servers launched automatically!"
echo "  Open browser: http://localhost:8000/simulator_home"
echo "  (You can change the number of steps by editing start_macos.command)"
echo "==================================================="
read -r -p "Press Enter to close this launcher..."
