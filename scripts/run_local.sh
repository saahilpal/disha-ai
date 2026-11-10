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
WATCHDOG_STDOUT="${LOG_DIR}/watchdog_stdout.log"
WATCHDOG_LOG="${LOG_DIR}/watchdog.log"

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

is_endpoint_healthy() {
  local url="$1"
  local timeout="${2:-5}"
  local resp
  resp="$(curl -s -S -f -m "${timeout}" "${url}" 2>&1 || true)"
  if [[ "${resp}" == *"\"ok\":true"* ]] || [[ "${resp}" == *"\"ok\": true"* ]] || [[ "${resp}" == *"\"database\":true"* ]] || [[ "${resp}" == *"\"database\": true"* ]]; then
    return 0
  fi
  # Fallback: if local DNS resolver cached NXDOMAIN for newly registered trycloudflare host, query Cloudflare DoH
  if [[ "${url}" == *".trycloudflare.com"* ]]; then
    resp="$(curl -s -S -f -m "${timeout}" --doh-url https://cloudflare-dns.com/dns-query "${url}" 2>&1 || true)"
    if [[ "${resp}" == *"\"ok\":true"* ]] || [[ "${resp}" == *"\"ok\": true"* ]] || [[ "${resp}" == *"\"database\":true"* ]] || [[ "${resp}" == *"\"database\": true"* ]]; then
      return 0
    fi
  fi
  return 1
}

wait_for_health() {
  local url="$1"
  local attempts="${2:-30}"
  local name="$3"
  log "INFO" "Waiting for ${name} at ${url}..."
  for ((i = 1; i <= attempts; i++)); do
    if is_endpoint_healthy "${url}" 3; then
      log "INFO" "✓ ${name} is healthy."
      return 0
    fi
    sleep 1
  done
  log "WARN" "Timed out waiting for ${name} at ${url}."
  return 1
}

get_watchdog_pid() {
  if [ -f "${PID_FILE}" ]; then
    local pid
    pid="$(tr -d ' \n\r' < "${PID_FILE}" 2>/dev/null || true)"
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
      local cmd
      cmd="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
      if [[ "${cmd}" == *"tunnel-watchdog.sh"* ]]; then
        echo "${pid}"
        return 0
      fi
    fi
  fi
  return 1
}

get_watchdog_pids() {
  pgrep -f "[t]unnel-watchdog\.sh" 2>/dev/null || true
}

get_cloudflared_pids() {
  pgrep -x cloudflared 2>/dev/null || true
}

kill_pids_gracefully() {
  local pids="$1"
  local name="$2"
  if [ -z "${pids}" ]; then
    return 0
  fi
  log "INFO" "Sending SIGTERM to ${name} (PID(s): ${pids})..."
  echo "${pids}" | xargs kill -TERM 2>/dev/null || true

  local waited=0
  while [ ${waited} -lt 5 ]; do
    local still_alive=""
    for p in ${pids}; do
      if kill -0 "${p}" 2>/dev/null; then
        still_alive="${still_alive} ${p}"
      fi
    done
    still_alive="$(echo "${still_alive}" | xargs)"
    if [ -z "${still_alive}" ]; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done

  # Force kill lingering processes if needed
  local lingering=""
  for p in ${pids}; do
    if kill -0 "${p}" 2>/dev/null; then
      lingering="${lingering} ${p}"
    fi
  done
  lingering="$(echo "${lingering}" | xargs)"
  if [ -n "${lingering}" ]; then
    log "WARN" "Force killing ${name} (PID(s): ${lingering})..."
    echo "${lingering}" | xargs kill -KILL 2>/dev/null || true
  fi
}

stop_tunnel() {
  log "INFO" "Stopping Cloudflare tunnel watchdog and cloudflared processes..."

  # 1. Stop tracked watchdog
  local wpid
  wpid="$(get_watchdog_pid || true)"
  if [ -n "${wpid}" ]; then
    kill_pids_gracefully "${wpid}" "tunnel watchdog"
  fi
  rm -f "${PID_FILE}"

  # 2. Stop any rogue watchdog scripts
  local rogue_watchdogs
  rogue_watchdogs="$(get_watchdog_pids)"
  if [ -n "${rogue_watchdogs}" ]; then
    kill_pids_gracefully "${rogue_watchdogs}" "rogue watchdog"
  fi

  # 3. Stop all cloudflared processes
  local cf_pids
  cf_pids="$(get_cloudflared_pids)"
  if [ -n "${cf_pids}" ]; then
    kill_pids_gracefully "${cf_pids}" "cloudflared"
  fi

  # 4. Clean up persisted tunnel URL file so stale URLs are never reported
  if [ -f "${TUNNEL_URL_FILE}" ]; then
    rm -f "${TUNNEL_URL_FILE}"
    log "INFO" "Cleaned up stale tunnel URL file."
  fi
}

clean_stale_processes() {
  local wpid
  wpid="$(get_watchdog_pid || true)"
  local cf_pids
  cf_pids="$(get_cloudflared_pids)"

  # Remove stale PID file if process is dead
  if [ -f "${PID_FILE}" ] && [ -z "${wpid}" ]; then
    log "WARN" "Removing stale watchdog PID file (${PID_FILE})."
    rm -f "${PID_FILE}"
  fi

  # If watchdog is not running, any cloudflared process is orphaned
  if [ -z "${wpid}" ] && [ -n "${cf_pids}" ]; then
    log "WARN" "Found orphaned cloudflared process(es) without watchdog: ${cf_pids}. Cleaning up..."
    kill_pids_gracefully "${cf_pids}" "orphaned cloudflared"
  fi

  # If multiple watchdogs are running, clean all to start fresh
  local all_watchdogs
  all_watchdogs="$(get_watchdog_pids)"
  local w_count
  w_count="$(echo "${all_watchdogs}" | wc -w | tr -d ' ')"
  if [ "${w_count}" -gt 1 ]; then
    log "WARN" "Found multiple watchdogs running (${all_watchdogs}). Resetting watchdogs..."
    kill_pids_gracefully "${all_watchdogs}" "duplicate watchdogs"
    rm -f "${PID_FILE}"
  fi

  # If watchdog is running, but multiple cloudflared processes exist
  if [ -n "${wpid}" ]; then
    cf_pids="$(get_cloudflared_pids)"
    local cf_count
    cf_count="$(echo "${cf_pids}" | wc -w | tr -d ' ')"
    if [ "${cf_count}" -gt 1 ]; then
      log "WARN" "Multiple cloudflared processes detected (${cf_pids}). Resetting tunnel state..."
      stop_tunnel
    fi
  fi
}

wait_for_tunnel() {
  local timeout="${1:-45}"
  local elapsed=0
  local tunnel_url=""

  log "INFO" "Waiting for Cloudflare Tunnel to establish edge connection and become publicly reachable (up to ${timeout}s)..."
  while [ ${elapsed} -lt ${timeout} ]; do
    # Check if watchdog died unexpectedly
    if [ -f "${PID_FILE}" ]; then
      local wpid
      wpid="$(tr -d ' \n\r' < "${PID_FILE}" 2>/dev/null || true)"
      if [ -n "${wpid}" ] && ! kill -0 "${wpid}" 2>/dev/null; then
        log "ERROR" "Watchdog process (PID ${wpid}) died unexpectedly during startup."
        [ -f "${WATCHDOG_LOG}" ] && tail -n 10 "${WATCHDOG_LOG}"
        return 1
      fi
    fi

    # Check for assigned tunnel URL
    if [ -f "${TUNNEL_URL_FILE}" ]; then
      tunnel_url="$(tr -d ' \n\r' < "${TUNNEL_URL_FILE}" 2>/dev/null || true)"
      if [ -n "${tunnel_url}" ]; then
        # Check genuine public reachability (HTTP 200 + ok JSON)
        if is_endpoint_healthy "${tunnel_url}/health" 4; then
          log "INFO" "✓ Cloudflare Tunnel is ONLINE and publicly reachable: ${tunnel_url}"
          return 0
        fi
      fi
    fi

    sleep 2
    elapsed=$((elapsed + 2))
    if [ $((elapsed % 6)) -eq 0 ]; then
      if [ -n "${tunnel_url}" ]; then
        log "INFO" "Assigned URL ${tunnel_url} — awaiting Cloudflare edge routing propagation... (${elapsed}s/${timeout}s)"
      else
        log "INFO" "Awaiting tunnel assignment from Cloudflare edge... (${elapsed}s/${timeout}s)"
      fi
    fi
  done

  if [ -n "${tunnel_url}" ]; then
    log "WARN" "Tunnel URL obtained (${tunnel_url}), but public edge health check timed out after ${timeout}s. Edge routing may still be propagating."
  else
    log "WARN" "Timed out waiting for Cloudflare Tunnel URL generation after ${timeout}s."
  fi
  return 1
}

start_tunnel() {
  clean_stale_processes

  local wpid
  wpid="$(get_watchdog_pid || true)"
  local cf_pids
  cf_pids="$(get_cloudflared_pids)"

  # Check if already running and healthy
  if [ -n "${wpid}" ] && [ -n "${cf_pids}" ] && [ -f "${TUNNEL_URL_FILE}" ]; then
    local current_url
    current_url="$(tr -d ' \n\r' < "${TUNNEL_URL_FILE}" 2>/dev/null || true)"
    if [ -n "${current_url}" ] && is_endpoint_healthy "${current_url}/health" 3; then
      log "INFO" "Cloudflare tunnel watchdog (PID ${wpid}) is already active and healthy at ${current_url}."
      return 0
    fi
  fi

  # Clean up inconsistent or dead state
  if [ -n "${wpid}" ] || [ -n "${cf_pids}" ]; then
    log "INFO" "Resetting inactive/unhealthy tunnel state before launch..."
    stop_tunnel
  fi

  # Clear old URL file so we only capture the new URL
  rm -f "${TUNNEL_URL_FILE}"

  log "INFO" "Launching Cloudflare tunnel watchdog on http://127.0.0.1:8080..."
  nohup "${WATCHDOG_SCRIPT}" >> "${WATCHDOG_STDOUT}" 2>&1 &

  wait_for_tunnel 45 || true
}

start_services() {
  log "INFO" "Starting Disha AI services..."
  check_docker

  cd "${REPO_ROOT}"
  docker compose up -d

  wait_for_health "http://127.0.0.1:8000/health" 30 "Backend API"
  wait_for_health "http://127.0.0.1:8080/health" 30 "Nginx Reverse Proxy"

  start_tunnel

  print_status
}

stop_services() {
  log "INFO" "Stopping Disha AI tunnel and services..."
  stop_tunnel

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
  if is_endpoint_healthy "http://127.0.0.1:8080/health" 2; then
    echo "  Local Web App:   http://localhost:8080"
    echo "  Local Health:    http://localhost:8080/health (OK)"
  else
    echo "  Local Web App:   DOWN (http://localhost:8080)"
  fi

  # Check backend directly
  if is_endpoint_healthy "http://127.0.0.1:8000/health" 2; then
    echo "  Backend Direct:  http://localhost:8000 (OK)"
  else
    echo "  Backend Direct:  DOWN (http://localhost:8000)"
  fi

  # Check Cloudflare Tunnel
  local wpid
  wpid="$(get_watchdog_pid || true)"
  local cf_pids
  cf_pids="$(get_cloudflared_pids)"

  if [ -f "${TUNNEL_URL_FILE}" ]; then
    local tunnel_url
    tunnel_url="$(tr -d ' \n\r' < "${TUNNEL_URL_FILE}" 2>/dev/null || true)"
    if [ -n "${tunnel_url}" ]; then
      if is_endpoint_healthy "${tunnel_url}/health" 4; then
        echo "  Public URL:      ${tunnel_url} (ONLINE)"
      elif [ -n "${wpid}" ] || [ -n "${cf_pids}" ]; then
        echo "  Public URL:      ${tunnel_url} (UNREACHABLE / PROPAGATING)"
      else
        echo "  Public URL:      DOWN (stale: ${tunnel_url})"
      fi
    elif [ -n "${wpid}" ] || [ -n "${cf_pids}" ]; then
      echo "  Public URL:      INITIALIZING (Connecting to edge...)"
    else
      echo "  Public URL:      DOWN (Tunnel stopped)"
    fi
  elif [ -n "${wpid}" ] || [ -n "${cf_pids}" ]; then
    echo "  Public URL:      INITIALIZING (Awaiting URL assignment...)"
  else
    echo "  Public URL:      DOWN (Tunnel stopped)"
  fi

  # Process overview
  if [ -n "${wpid}" ]; then
    echo "  Watchdog:        RUNNING (PID ${wpid})"
  else
    echo "  Watchdog:        STOPPED"
  fi

  if [ -n "${cf_pids}" ]; then
    local cf_count
    cf_count="$(echo "${cf_pids}" | wc -w | tr -d ' ')"
    if [ "${cf_count}" -gt 1 ]; then
      echo "  Cloudflared:     WARNING (${cf_count} processes: ${cf_pids})"
    else
      echo "  Cloudflared:     RUNNING (PID ${cf_pids})"
    fi
  else
    echo "  Cloudflared:     STOPPED"
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
  tunnel-start)
    start_tunnel
    print_status
    ;;
  tunnel-stop)
    stop_tunnel
    print_status
    ;;
  tunnel-restart)
    stop_tunnel
    sleep 2
    start_tunnel
    print_status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|tunnel-start|tunnel-stop|tunnel-restart}"
    exit 1
    ;;
esac
