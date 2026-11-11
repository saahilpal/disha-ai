#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${TMPDIR:-/tmp}/disha-local-models-${UID}"
AUDIO_VENV="${ROOT_DIR}/.venv-mlx-audio"
OLLAMA_MODEL="${OLLAMA_MODEL:-}"
STT_MODEL="${LOCAL_STT_MODEL:-mlx-community/whisper-large-v3-turbo-asr-fp16}"
TTS_MODEL="${QWEN3_TTS_MODEL:-mlx-community/svara-tts-v1-4bit}"
APP_PORT="${LOCAL_APP_PORT:-8010}"
OLLAMA_URL="http://127.0.0.1:11434"
AUDIO_URL="http://127.0.0.1:8880"

usage() {
  echo "Usage: $0 {start|stop|status}"
}

wait_for_url() {
  local url="$1" attempts="${2:-60}"
  for ((i = 0; i < attempts; i++)); do
    if curl --silent --fail "$url" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_owned() {
  local name="$1" log="$2"
  shift 2
  nohup "$@" >"$log" 2>&1 </dev/null &
  echo "$!" >"${RUN_DIR}/${name}.pid"
}

stop_owned() {
  local name="$1" expected="$2" pid command
  [[ -f "${RUN_DIR}/${name}.pid" ]] || return 0
  pid="$(cat "${RUN_DIR}/${name}.pid")"
  if [[ "$pid" =~ ^[0-9]+$ ]]; then
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$command" == *"$expected"* ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "${RUN_DIR}/${name}.pid"
}

status() {
  mkdir -p "$RUN_DIR"
  for name_url in "Ollama|${OLLAMA_URL}/api/version" "MLX Audio|${AUDIO_URL}/" "Disha API|http://127.0.0.1:${APP_PORT}/health"; do
    name="${name_url%%|*}"
    url="${name_url#*|}"
    if curl --silent --fail "$url" >/dev/null; then
      echo "$name: ready"
    else
      echo "$name: stopped"
    fi
  done
}

start() {
  [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || {
    echo "Local MLX models require an Apple Silicon Mac." >&2
    exit 1
  }
  for tool in brew curl docker ollama uv ffmpeg; do
    command -v "$tool" >/dev/null 2>&1 || {
      echo "Missing $tool. Install Ollama and ffmpeg with: brew install ollama ffmpeg" >&2
      exit 1
    }
  done
  [[ -x "${ROOT_DIR}/.venv/bin/python" ]] || {
    echo "Create the project environment first: uv venv && uv pip install -r disha_core/requirements.txt" >&2
    exit 1
  }

  mkdir -p "$RUN_DIR"
  if ! curl --silent --fail "${OLLAMA_URL}/api/version" >/dev/null; then
    start_owned ollama "${RUN_DIR}/ollama.log" env \
      OLLAMA_HOST=127.0.0.1:11434 OLLAMA_KEEP_ALIVE=5m OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 \
      ollama serve
    wait_for_url "${OLLAMA_URL}/api/version" 60 || {
      echo "Ollama did not start; see ${RUN_DIR}/ollama.log" >&2
      exit 1
    }
  fi
  if [[ -z "$OLLAMA_MODEL" ]]; then
    if ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "qwen3.5:4b"; then
      OLLAMA_MODEL="qwen3.5:4b"
    elif ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "qwen2.5:7b"; then
      OLLAMA_MODEL="qwen2.5:7b"
    else
      OLLAMA_MODEL="qwen3.5:4b"
    fi
  fi
  if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$OLLAMA_MODEL"; then
    ollama pull "$OLLAMA_MODEL"
  fi

  if [[ ! -x "${AUDIO_VENV}/bin/python" ]]; then
    uv venv "$AUDIO_VENV" --python 3.12
  fi
  if ! "${AUDIO_VENV}/bin/python" -c 'import importlib.metadata, fastapi, multipart; assert importlib.metadata.version("mlx-audio") == "0.6.2"' >/dev/null 2>&1; then
    uv pip install --python "${AUDIO_VENV}/bin/python" 'mlx-audio[server]==0.6.2'
  fi

  if ! curl --silent --fail "${AUDIO_URL}/" >/dev/null; then
    start_owned mlx-audio "${RUN_DIR}/mlx-audio.log" \
      "${AUDIO_VENV}/bin/mlx_audio.server" --host 127.0.0.1 --port 8880
    wait_for_url "${AUDIO_URL}/" 60 || {
      echo "MLX Audio did not start; see ${RUN_DIR}/mlx-audio.log" >&2
      exit 1
    }
  fi
  curl --silent --show-error --fail --max-time 600 --get \
    --data-urlencode "model_name=${STT_MODEL}" -X POST "${AUDIO_URL}/v1/models" >/dev/null
  curl --silent --show-error --fail --max-time 600 --get \
    --data-urlencode "model_name=${TTS_MODEL}" -X POST "${AUDIO_URL}/v1/models" >/dev/null

  docker compose up -d postgres
  for ((i = 0; i < 60; i++)); do
    if docker compose exec -T postgres pg_isready -U disha -d disha >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  DB_PASSWORD="$(docker compose exec -T postgres printenv POSTGRES_PASSWORD)"
  [[ -n "$DB_PASSWORD" ]] || {
    echo "Could not read the running Postgres password from Docker Compose." >&2
    exit 1
  }
  if curl --silent --fail "http://127.0.0.1:${APP_PORT}/health" >/dev/null; then
    echo "Port ${APP_PORT} is already serving an app; set LOCAL_APP_PORT to another free port." >&2
    exit 1
  fi

  (
    cd "$ROOT_DIR"
    unset DATABASE_URL GROQ_API_KEY GEMINI_API_KEY GOOGLE_API_KEY LAYA_SERVER_URL LAYA_API_KEY
    # Keep Ollama as the last provider by default; LOCAL_ONLY=true remains an opt-in.
    export LOCAL_ONLY="${LOCAL_ONLY:-false}" OLLAMA_ENABLED=true OLLAMA_BASE_URL="$OLLAMA_URL" OLLAMA_MODEL
    export LOCAL_STT_URL="${AUDIO_URL}/v1/audio/transcriptions" LOCAL_STT_MODEL="$STT_MODEL"
    export TTS_ENGINE=mlx QWEN3_TTS_URL="${AUDIO_URL}/v1/audio/speech" QWEN3_TTS_MODEL="$TTS_MODEL"
    export MLX_TTS_CLI="${AUDIO_VENV}/bin/mlx_audio.tts.generate"
    export LOCAL_TTS_HINDI_VOICE="Hindi (Female)" LOCAL_TTS_ENGLISH_VOICE="English (Indian) (Female)"
    export QWEN3_TTS_TIMEOUT=60 VOICE_TRANSCRIBE_TIMEOUT=30 LLM_FIRST_TOKEN_TIMEOUT=30
    export GROQ_HEALTH_DATA_PROCESSING_APPROVED=false GROQ_HEALTH_DATA_AUTHORIZED=false GROQ_USAGE_CHARGES_AUTHORIZED=false
    export GEMINI_HEALTH_DATA_AUTHORIZED=false GEMINI_PAID_OR_CONTRACTED=false EDGE_TTS_HEALTH_DATA_PROCESSING_APPROVED=false
    export DB_HOST=127.0.0.1 DB_PORT=5432 DB_NAME=disha DB_USER=disha DB_PASSWORD
    exec "${ROOT_DIR}/.venv/bin/python" -m uvicorn disha_core.main:app --host 127.0.0.1 --port "$APP_PORT"
  ) >"${RUN_DIR}/disha-api.log" 2>&1 </dev/null &
  echo "$!" >"${RUN_DIR}/disha-api.pid"
  wait_for_url "http://127.0.0.1:${APP_PORT}/health" 90 || {
    echo "Disha API did not become healthy; see ${RUN_DIR}/disha-api.log" >&2
    exit 1
  }
  echo "Disha is running locally at http://127.0.0.1:${APP_PORT} (Ollama fallback: ${OLLAMA_MODEL})"
  echo "Model server logs and process IDs: ${RUN_DIR}"
}

stop() {
  stop_owned disha-api "uvicorn disha_core.main:app"
  stop_owned mlx-audio "mlx_audio.server"
  stop_owned ollama "ollama serve"
  echo "Stopped local model processes started by this script. Postgres is left running."
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) usage; exit 2 ;;
esac
