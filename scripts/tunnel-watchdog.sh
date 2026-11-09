#!/usr/bin/env bash
# ==============================================================================
# DISHA AI — PRODUCTION CLOUDFLARE TUNNEL WATCHDOG
# Architecture: Deterministic Host Process Watchdog & Resilient Edge Ingress
# Standards: cloudflare-architect, senior-ai-systems-engineer
# ==============================================================================
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ------------------------------------------------------------------------------
# 1. Configuration & Default Invariants
# ------------------------------------------------------------------------------
TARGET_URL="${TARGET_URL:-http://127.0.0.1:8080}"
HEALTH_URL="${HEALTH_URL:-${TARGET_URL}/health}"
TUNNEL_URL_FILE="${TUNNEL_URL_FILE:-${REPO_ROOT}/agent/TUNNEL_URL.txt}"
LOG_DIR="${LOG_DIR:-${REPO_ROOT}/infra/logs}"
PID_FILE="${PID_FILE:-${LOG_DIR}/tunnel-watchdog.pid}"
CLOUDFLARED_LOG="${CLOUDFLARED_LOG:-${LOG_DIR}/cloudflared.log}"
WATCHDOG_LOG="${WATCHDOG_LOG:-${LOG_DIR}/watchdog.log}"

CHECK_INTERVAL="${CHECK_INTERVAL:-5}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-4}"
MAX_CONSECUTIVE_FAILURES="${MAX_CONSECUTIVE_FAILURES:-3}"
MAX_RESTART_BACKOFF="${MAX_RESTART_BACKOFF:-30}"
TUNNEL_START_TIMEOUT="${TUNNEL_START_TIMEOUT:-45}"

CUSTOM_DOMAIN="${TUNNEL_DOMAIN:-}"
CUSTOM_TUNNEL_NAME="${TUNNEL_NAME:-}"
CUSTOM_TUNNEL_TOKEN="${TUNNEL_TOKEN:-}"

mkdir -p "${LOG_DIR}" "$(dirname "${TUNNEL_URL_FILE}")"

# ------------------------------------------------------------------------------
# 2. Binary Auto-Discovery
# ------------------------------------------------------------------------------
find_cloudflared_bin() {
  if command -v cloudflared &>/dev/null; then
    command -v cloudflared
  elif [ -x "/opt/homebrew/bin/cloudflared" ]; then
    echo "/opt/homebrew/bin/cloudflared"
  elif [ -x "/usr/local/bin/cloudflared" ]; then
    echo "/usr/local/bin/cloudflared"
  else
    echo ""
  fi
}

CLOUDFLARED_BIN="$(find_cloudflared_bin)"
if [ -z "${CLOUDFLARED_BIN}" ]; then
  echo "[!] Error: cloudflared binary not found in PATH, /opt/homebrew/bin, or /usr/local/bin" >&2
  echo "[!] Please install via 'brew install cloudflared' or download from cloudflare.com" >&2
  exit 1
fi

# ------------------------------------------------------------------------------
# 3. Logging Function
# ------------------------------------------------------------------------------
log() {
  local level="${1:-INFO}"
  shift
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  local msg="[${ts}] [${level}] $*"
  echo "${msg}"
  if [ -d "${LOG_DIR}" ]; then
    echo "${msg}" >> "${WATCHDOG_LOG}" 2>/dev/null || true
  fi
}

# ------------------------------------------------------------------------------
# 4. State & Signal Management
# ------------------------------------------------------------------------------
CLOUDFLARED_PID=""
CURRENT_TUNNEL_URL=""

cleanup() {
  log "WARN" "Watchdog signal received; initiating clean teardown..."
  if [ -n "${CLOUDFLARED_PID}" ] && kill -0 "${CLOUDFLARED_PID}" 2>/dev/null; then
    log "INFO" "Terminating cloudflared process (PID ${CLOUDFLARED_PID})..."
    kill -TERM "${CLOUDFLARED_PID}" 2>/dev/null || true
    local wait_count=0
    while kill -0 "${CLOUDFLARED_PID}" 2>/dev/null && [ ${wait_count} -lt 5 ]; do
      sleep 1
      wait_count=$((wait_count + 1))
    done
    if kill -0 "${CLOUDFLARED_PID}" 2>/dev/null; then
      log "WARN" "Force killing cloudflared process (PID ${CLOUDFLARED_PID})..."
      kill -KILL "${CLOUDFLARED_PID}" 2>/dev/null || true
    fi
  fi
  rm -f "${PID_FILE}"
  log "INFO" "Watchdog cleanup complete. Exiting."
  exit 0
}

# ------------------------------------------------------------------------------
# 5. Helper Functions: URL Extraction & Atomic Persistence
# ------------------------------------------------------------------------------
extract_tunnel_url() {
  local log_file="$1"
  if [ ! -f "${log_file}" ]; then
    return 1
  fi
  local extracted
  extracted="$(grep -o -E 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "${log_file}" | tail -n 1 || true)"
  if [ -n "${extracted}" ]; then
    echo "${extracted}"
    return 0
  fi
  return 1
}

save_tunnel_url() {
  local url="$1"
  local target_file="${TUNNEL_URL_FILE}"
  local target_dir
  target_dir="$(dirname "${target_file}")"
  mkdir -p "${target_dir}"
  local tmp_file="${target_file}.tmp.$$"
  echo "${url}" > "${tmp_file}"
  mv -f "${tmp_file}" "${target_file}"

  # Also persist to .env.local for local runtime consumption
  local env_local="${REPO_ROOT}/.env.local"
  if [ -f "${env_local}" ]; then
    sed -i '' '/^PUBLIC_TUNNEL_URL=/d' "${env_local}" 2>/dev/null || true
  fi
  echo "PUBLIC_TUNNEL_URL=\"${url}\"" >> "${env_local}"

  log "INFO" "Persisted live public tunnel URL -> ${target_file} & .env.local: ${url}"
}

# ------------------------------------------------------------------------------
# 6. Backend & Ingress Health Checks
# ------------------------------------------------------------------------------
check_local_health() {
  local resp
  resp="$(curl -s -S -f -m "${HEALTH_CHECK_TIMEOUT}" "${HEALTH_URL}" 2>&1 || true)"
  if [[ "${resp}" == *"\"ok\":true"* ]] || [[ "${resp}" == *"\"ok\": true"* ]] || [[ "${resp}" == *"database"* ]]; then
    return 0
  fi
  log "WARN" "Local health probe failed at ${HEALTH_URL}. Detail: ${resp}"
  return 1
}

check_edge_connectivity() {
  local edge_url="${1:-${CURRENT_TUNNEL_URL}}"
  if [ -z "${edge_url}" ]; then
    return 0
  fi
  local edge_resp
  edge_resp="$(curl -s -S -f -m 5 "${edge_url}/health" 2>&1 || true)"
  if [[ "${edge_resp}" == *"\"ok\":true"* ]] || [[ "${edge_resp}" == *"\"ok\": true"* ]] || [[ "${edge_resp}" == *"database"* ]]; then
    return 0
  fi
  log "WARN" "Public edge health check failed at ${edge_url}/health: ${edge_resp}"
  return 1
}

# ------------------------------------------------------------------------------
# 7. Cloudflared Process Launcher
# ------------------------------------------------------------------------------
start_cloudflared() {
  log "INFO" "Launching cloudflared instance..."

  # Rotate log if larger than 10MB
  if [ -f "${CLOUDFLARED_LOG}" ]; then
    local size
    size="$(wc -c < "${CLOUDFLARED_LOG}" 2>/dev/null || echo 0)"
    if [ "${size}" -gt 10485760 ]; then
      mv -f "${CLOUDFLARED_LOG}" "${CLOUDFLARED_LOG}.old"
    fi
  fi
  : > "${CLOUDFLARED_LOG}"

  if [ -n "${CUSTOM_TUNNEL_TOKEN}" ]; then
    log "INFO" "Starting named tunnel with credentials token..."
    "${CLOUDFLARED_BIN}" tunnel --no-autoupdate run --token "${CUSTOM_TUNNEL_TOKEN}" >> "${CLOUDFLARED_LOG}" 2>&1 &
    CLOUDFLARED_PID=$!
  elif [ -n "${CUSTOM_TUNNEL_NAME}" ]; then
    log "INFO" "Starting named tunnel: ${CUSTOM_TUNNEL_NAME}..."
    "${CLOUDFLARED_BIN}" tunnel --no-autoupdate run "${CUSTOM_TUNNEL_NAME}" >> "${CLOUDFLARED_LOG}" 2>&1 &
    CLOUDFLARED_PID=$!
  else
    # Quick Tunnel Fallback Mode
    log "INFO" "Starting Quick Tunnel fallback: ${CLOUDFLARED_BIN} tunnel --url ${TARGET_URL}"
    "${CLOUDFLARED_BIN}" tunnel --url "${TARGET_URL}" --no-autoupdate >> "${CLOUDFLARED_LOG}" 2>&1 &
    CLOUDFLARED_PID=$!
  fi

  log "INFO" "cloudflared spawned with PID ${CLOUDFLARED_PID}"

  # Poll logs to capture live public URL
  local elapsed=0
  local detected_url=""
  if [ -n "${CUSTOM_DOMAIN}" ]; then
    detected_url="https://${CUSTOM_DOMAIN}"
  fi

  log "INFO" "Awaiting public ingress URL (timeout: ${TUNNEL_START_TIMEOUT}s)..."
  while [ ${elapsed} -lt "${TUNNEL_START_TIMEOUT}" ]; do
    if ! kill -0 "${CLOUDFLARED_PID}" 2>/dev/null; then
      log "ERROR" "cloudflared process died prematurely during startup. Tail of ${CLOUDFLARED_LOG}:"
      tail -n 15 "${CLOUDFLARED_LOG}" | while read -r line; do log "ERROR" "  $line"; done
      return 1
    fi

    if [ -z "${detected_url}" ]; then
      detected_url="$(extract_tunnel_url "${CLOUDFLARED_LOG}" || true)"
    fi

    if [ -n "${detected_url}" ]; then
      log "INFO" "Cloudflare Tunnel successfully established: ${detected_url}"
      save_tunnel_url "${detected_url}"
      CURRENT_TUNNEL_URL="${detected_url}"
      return 0
    fi

    sleep 1
    elapsed=$((elapsed + 1))
  done

  log "ERROR" "Timed out waiting for tunnel URL after ${TUNNEL_START_TIMEOUT} seconds"
  return 1
}

# ------------------------------------------------------------------------------
# 8. Main Watchdog Supervision Loop
# ------------------------------------------------------------------------------
run_watchdog() {
  trap cleanup SIGINT SIGTERM SIGHUP EXIT

  log "INFO" "Initializing Disha AI Cloudflare Tunnel Watchdog..."
  log "INFO" "Target Local Ingress: ${TARGET_URL}"
  log "INFO" "Local Health URL:     ${HEALTH_URL}"
  log "INFO" "Tunnel URL File:      ${TUNNEL_URL_FILE}"
  log "INFO" "Logging Directory:    ${LOG_DIR}"

  echo "$$" > "${PID_FILE}"

  # Phase A: Wait for Local Backend to be operational
  local wait_backend=0
  log "INFO" "Probing local backend at ${HEALTH_URL}..."
  while ! check_local_health; do
    log "WARN" "Local backend not healthy yet; waiting 3s... (attempt $((wait_backend + 1)))"
    sleep 3
    wait_backend=$((wait_backend + 1))
    if [ ${wait_backend} -ge 20 ]; then
      log "ERROR" "Local backend failed to become healthy within 60s. Aborting watchdog start."
      exit 1
    fi
  done
  log "INFO" "Local backend confirmed healthy."

  # Phase B: Initial Tunnel Launch
  local backoff=1
  while true; do
    if start_cloudflared; then
      backoff=1
      break
    else
      log "WARN" "Tunnel initialization failed. Retrying in ${backoff}s..."
      sleep "${backoff}"
      backoff=$((backoff * 2))
      if [ "${backoff}" -gt "${MAX_RESTART_BACKOFF}" ]; then
        backoff="${MAX_RESTART_BACKOFF}"
      fi
    fi
  done

  # Phase C: Continuous Monitoring Loop
  local consecutive_health_failures=0
  local consecutive_edge_failures=0
  local cycle=0

  log "INFO" "Watchdog actively monitoring cloudflared PID ${CLOUDFLARED_PID} every ${CHECK_INTERVAL}s"

  while true; do
    sleep "${CHECK_INTERVAL}"
    cycle=$((cycle + 1))

    # 1. Process Liveness Check
    if ! kill -0 "${CLOUDFLARED_PID}" 2>/dev/null; then
      log "ERROR" "cloudflared process (PID ${CLOUDFLARED_PID}) died unexpectedly!"
      log "INFO" "Auto-restarting cloudflared tunnel..."
      if start_cloudflared; then
        consecutive_health_failures=0
        consecutive_edge_failures=0
        continue
      else
        sleep "${backoff}"
        continue
      fi
    fi

    # 2. Local Backend Health Check
    if check_local_health; then
      consecutive_health_failures=0
    else
      consecutive_health_failures=$((consecutive_health_failures + 1))
      log "WARN" "Consecutive local health failures: ${consecutive_health_failures}/${MAX_CONSECUTIVE_FAILURES}"
      if [ "${consecutive_health_failures}" -ge "${MAX_CONSECUTIVE_FAILURES}" ]; then
        log "ERROR" "Local backend is failing health checks! Inspect docker backend containers."
      fi
    fi

    # 3. Public Edge Ingress Health Check (Every 6 cycles / ~30s)
    if [ $((cycle % 6)) -eq 0 ] && [ -n "${CURRENT_TUNNEL_URL}" ]; then
      if check_edge_connectivity "${CURRENT_TUNNEL_URL}"; then
        consecutive_edge_failures=0
      else
        consecutive_edge_failures=$((consecutive_edge_failures + 1))
        log "WARN" "Consecutive edge ingress check failures: ${consecutive_edge_failures}/3"
        if [ "${consecutive_edge_failures}" -ge 3 ]; then
          log "ERROR" "Public edge ingress unreachable for 3 checks. Restarting tunnel..."
          kill -TERM "${CLOUDFLARED_PID}" 2>/dev/null || true
          wait "${CLOUDFLARED_PID}" 2>/dev/null || true
          start_cloudflared || true
          consecutive_edge_failures=0
        fi
      fi
    fi
  done
}

# ------------------------------------------------------------------------------
# 9. CLI Subcommands & Dispatcher
# ------------------------------------------------------------------------------
show_status() {
  echo "======================================================================"
  echo "DISHA AI — CLOUDFLARE TUNNEL WATCHDOG STATUS"
  echo "======================================================================"
  if [ -f "${PID_FILE}" ]; then
    local wpid
    wpid="$(cat "${PID_FILE}")"
    if kill -0 "${wpid}" 2>/dev/null; then
      echo "[+] Watchdog Status: RUNNING (PID ${wpid})"
    else
      echo "[-] Watchdog Status: STOPPED (stale PID file: ${wpid})"
    fi
  else
    echo "[-] Watchdog Status: NOT RUNNING"
  fi

  if pgrep -f "${CLOUDFLARED_BIN} tunnel" >/dev/null; then
    local cpid
    cpid="$(pgrep -f "${CLOUDFLARED_BIN} tunnel" | tr '\n' ' ')"
    echo "[+] cloudflared Status: RUNNING (PIDs: ${cpid})"
  else
    echo "[-] cloudflared Status: NOT RUNNING"
  fi

  if [ -f "${TUNNEL_URL_FILE}" ]; then
    echo "[+] Live Tunnel URL:  $(cat "${TUNNEL_URL_FILE}")"
  else
    echo "[-] Live Tunnel URL:  Not available (File ${TUNNEL_URL_FILE} missing)"
  fi
  echo "======================================================================"
}

stop_watchdog() {
  log "INFO" "Stopping Disha AI tunnel watchdog and cloudflared processes..."
  if [ -f "${PID_FILE}" ]; then
    local wpid
    wpid="$(cat "${PID_FILE}")"
    if kill -0 "${wpid}" 2>/dev/null; then
      kill -TERM "${wpid}" 2>/dev/null || true
      echo "[+] Sent SIGTERM to watchdog PID ${wpid}"
    fi
    rm -f "${PID_FILE}"
  fi

  # Terminate any remaining cloudflared instances
  pkill -f "cloudflared tunnel" 2>/dev/null || true
  echo "[+] cloudflared processes terminated."
}

install_launchd_service() {
  local plist_src="${REPO_ROOT}/infra/com.disha.tunnel.plist"
  local plist_dst="${HOME}/Library/LaunchAgents/com.disha.tunnel.plist"
  mkdir -p "${HOME}/Library/LaunchAgents"
  cp -f "${plist_src}" "${plist_dst}"
  chmod 644 "${plist_dst}"
  launchctl unload "${plist_dst}" 2>/dev/null || true
  launchctl load "${plist_dst}"
  echo "[+] Successfully installed and loaded macOS launchd service: ${plist_dst}"
  echo "[+] Check status with: launchctl list | grep com.disha.tunnel"
}

uninstall_launchd_service() {
  local plist_dst="${HOME}/Library/LaunchAgents/com.disha.tunnel.plist"
  if [ -f "${plist_dst}" ]; then
    launchctl unload "${plist_dst}" 2>/dev/null || true
    rm -f "${plist_dst}"
    echo "[+] Successfully unloaded and removed launchd service: ${plist_dst}"
  else
    echo "[-] Service definition not found at ${plist_dst}"
  fi
}

verify_telephony() {
  "${SCRIPT_DIR}/verify-telephony-live.sh" "$@"
}

# CLI Argument parsing
case "${1:-}" in
  --save-url|--persist-url)
    shift
    if [ -z "${1:-}" ]; then
      echo "Error: URL argument required" >&2
      exit 1
    fi
    save_tunnel_url "$1"
    exit 0
    ;;
  --status|status)
    show_status
    exit 0
    ;;
  --stop|stop)
    stop_watchdog
    exit 0
    ;;
  --install-service)
    install_launchd_service
    exit 0
    ;;
  --uninstall-service)
    uninstall_launchd_service
    exit 0
    ;;
  --verify|verify)
    shift
    verify_telephony "$@"
    exit 0
    ;;
  *)
    run_watchdog
    ;;
esac
