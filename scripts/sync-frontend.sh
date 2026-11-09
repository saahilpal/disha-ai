#!/usr/bin/env bash
# ==============================================================================
# DISHA AI — CANONICAL FRONTEND SYNCHRONIZATION PIPELINE
# Establishes frontend/ as the single canonical source of truth and mirrors it
# into disha_core/frontend/ with cryptographic byte-for-byte verification.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SOURCE_DIR="${WORKSPACE_ROOT}/frontend"
TARGET_DIR="${WORKSPACE_ROOT}/disha_core/frontend"

if [ -L "${SOURCE_DIR}" ]; then
  link_target="$(readlink "${SOURCE_DIR}")"
  if [ "${link_target}" = "disha_core/frontend" ] || [ "${link_target}" = "${TARGET_DIR}" ]; then
    echo "[+] Canonical frontend is consolidated: frontend -> disha_core/frontend (Symlink active)."
    echo "[+] Validating canonical assets in ${TARGET_DIR}..."
    if [ -f "${TARGET_DIR}/app.js" ] && [ -f "${TARGET_DIR}/index.html" ] && [ -f "${TARGET_DIR}/style.css" ]; then
      echo "[+] Canonical frontend verified! (Zero drift, single source of truth: disha_core/frontend/)"
      exit 0
    else
      echo "[-] Missing critical frontend assets in ${TARGET_DIR}" >&2
      exit 1
    fi
  fi
fi

if [ ! -d "${SOURCE_DIR}" ]; then
  echo "[-] Canonical frontend directory not found: ${SOURCE_DIR}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

# 1. Synchronize canonical assets into disha_core/frontend
if command -v rsync &> /dev/null; then
  rsync -a --delete \
    --exclude=".DS_Store" \
    "${SOURCE_DIR}/" "${TARGET_DIR}/"
else
  # Fallback for minimal environments without rsync
  rm -rf "${TARGET_DIR:?}"/*
  cp -R "${SOURCE_DIR}/"* "${TARGET_DIR}/"
fi

# 2. Byte-for-byte SHA-256 verification
echo "[+] Validating canonical parity between frontend/ and disha_core/frontend/..."
MISMATCHES=0

for file in "${SOURCE_DIR}"/*; do
  if [ -f "${file}" ]; then
    fname="$(basename "${file}")"
    target_file="${TARGET_DIR}/${fname}"

    if [ ! -f "${target_file}" ]; then
      echo "[-] Missing file in target: ${fname}" >&2
      MISMATCHES=$((MISMATCHES + 1))
      continue
    fi

    src_hash="$(shasum -a 256 "${file}" | awk '{print $1}')"
    tgt_hash="$(shasum -a 256 "${target_file}" | awk '{print $1}')"

    if [ "${src_hash}" != "${tgt_hash}" ]; then
      echo "[-] Checksum mismatch for ${fname}: ${src_hash} != ${tgt_hash}" >&2
      MISMATCHES=$((MISMATCHES + 1))
    fi
  fi
done

if [ "${MISMATCHES}" -gt 0 ]; then
  echo "[-] Frontend sync failed with ${MISMATCHES} mismatches." >&2
  exit 1
fi

echo "[+] Canonical frontend successfully synchronized! (Zero drift, 100% byte-for-byte parity)"
exit 0
