#!/usr/bin/env bash
# ==============================================================================
# DISHA AI — LOCAL RUNTIME & TUNNEL CONTROLLER
# Starts & verifies Docker stack (Postgres, Backend, Nginx Proxy) + Cloudflare Tunnel
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${REPO_ROOT}/infra/logs"
PID_FILE="${LOG_DIR}/tunnel-watchdog.pid"
TUNNEL_URL_FILE="${REPO_ROOT}/agent/TUNNEL_URL.txt"
WATCHDOG_SCRIPT="${REPO_ROOT}/scripts/tunnel-watchdog.sh"

mkdir -p "${LOG_DIR}"

log() {
  local level="${1:-INFO}"
  shift
  echo "[$(date +"%Y-%m-%dT%H:%M:%S%z")] [${level}] $*"
}

check_docker() {
  if ! docker info >/dev/null 2>&1; then
    log "ERROR" "Docker daemon is not running. Please start Docker Desktop."
    return 1
  fi
  return 0
}

wait_for_health() {
  local url="$1"
  local attempts="${2:-30}"
  local name="$3"
  log "INFO" "Waiting for ${name} at ${url}..."
  for ((i = 1; i <= attempts; i++)); do
    if curl -s -f -o /dev/null "${url}"; then
      log "INFO" "✓ ${name} is healthy."
      return 0
    fi
    sleep 1
  done
  log "WARN" "Timed out waiting for ${name} at ${url}."
  return 1
}

start_services() {
  log "INFO" "Starting Disha AI services..."
  check_docker

  cd "${REPO_ROOT}"
  docker compose up -d

  wait_for_health "http://127.0.0.1:8000/health" 30 "Backend API"
  wait_for_health "http://127.0.0.1:8080/health" 30 "Nginx Reverse Proxy"

  # Start tunnel watchdog if not running
  if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    log "INFO" "Cloudflare tunnel watchdog is already running (PID $(cat "${PID_FILE}"))."
  elif pgrep -f "cloudflared tunnel.*8080" >/dev/null 2>&1; then
    log "INFO" "Cloudflare tunnel is active on port 8080."
  else
    log "INFO" "Launching Cloudflare tunnel watchdog on http://127.0.0.1:8080..."
    nohup "${WATCHDOG_SCRIPT}" >/dev/null 2>&1 &
    sleep 5
  fi

  print_status
}

stop_services() {
  log "INFO" "Stopping Disha AI tunnel and services..."
  if [ -f "${PID_FILE}" ]; then
    local pid
    pid="$(cat "${PID_FILE}")"
    if kill -0 "${pid}" 2>/dev/null; then
      log "INFO" "Stopping tunnel watchdog (PID ${pid})..."
      kill -TERM "${pid}" 2>/dev/null || true
    fi
    rm -f "${PID_FILE}"
  fi
  pkill -f "cloudflared tunnel" 2>/dev/null || true

  cd "${REPO_ROOT}"
  docker compose stop
  log "INFO" "Services stopped successfully."
}

print_status() {
  echo ""
  echo "================================================================="
  echo "                      DISHA AI SYSTEM STATUS                     "
  echo "================================================================="
  
  # Check local proxy
  if curl -s -f -o /dev/null "http://127.0.0.1:8080/health"; then
    echo "  Local Web App:   http://localhost:8080"
    echo "  Local Health:    http://localhost:8080/health (OK)"
  else
    echo "  Local Web App:   DOWN (http://localhost:8080)"
  fi

  # Check backend directly
  if curl -s -f -o /dev/null "http://127.0.0.1:8000/health"; then
    echo "  Backend Direct:  http://localhost:8000 (OK)"
  else
    echo "  Backend Direct:  DOWN (http://localhost:8000)"
  fi

  # Check Cloudflare Tunnel URL
  if [ -f "${TUNNEL_URL_FILE}" ]; then
    local tunnel_url
    tunnel_url="$(tr -d ' \n\r' < "${TUNNEL_URL_FILE}")"
    if [ -n "${tunnel_url}" ]; then
      if curl -s -f -o /dev/null -m 5 "${tunnel_url}/health"; then
        echo "  Public URL:      ${tunnel_url} (ONLINE)"
      else
        echo "  Public URL:      ${tunnel_url} (UNREACHABLE)"
      fi
    else
      echo "  Public URL:      Not configured or empty."
    fi
  else
    echo "  Public URL:      No tunnel URL file found."
  fi

  echo "================================================================="
  echo ""
}

case "${1:-status}" in
  start)
    start_services
    ;;
  stop)
    stop_services
    ;;
  restart)
    stop_services
    sleep 2
    start_services
    ;;
  status)
    print_status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac

