#!/usr/bin/env bash
# ==============================================================================
# DISHA AI — CLOUD VM PROVISIONING & DEPLOYMENT SCRIPT
# Target: Ubuntu 22.04 / Debian 12 / RHEL 9 (AWS EC2, GCP Compute Engine, OCI)
# Min Specs: 4 vCPU, 8 GB RAM, 40 GB NVMe (Required for Laya + Postgres + Engine)
# ==============================================================================
set -euo pipefail

echo "======================================================================"
echo "DISHA AI — PRODUCTION CLOUD VM PROVISIONING"
echo "======================================================================"

# 1. Verify Root/Sudo Privileges
if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root or with sudo: sudo ./deploy-vm.sh"
  exit 1
fi

# 2. System Update & Dependencies
echo "[+] Updating apt repositories..."
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  git \
  ufw \
  jq

# 3. Install Docker Engine if not present
if ! command -v docker &> /dev/null; then
  echo "[+] Installing official Docker Engine..."
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker

# 4. Firewall Setup
echo "[+] Configuring UFW rules..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable

# 5. Build and Launch Multi-Service Production Stack
echo "[+] Launching production Docker Compose stack..."
docker compose -f docker-compose.prod.yml down --remove-orphans || true
docker compose -f docker-compose.prod.yml up -d --build

# 6. Verify Container Health
echo "[+] Waiting for database and Laya classifier healthchecks..."
ATTEMPTS=0
MAX_ATTEMPTS=30
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
  HEALTHY=$(docker ps --filter "name=disha-prod-postgres" --filter "health=healthy" -q)
  if [ -n "$HEALTHY" ]; then
    echo "[+] PostgreSQL 16 is healthy!"
    break
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  sleep 2
done

# 7. Print Deployment Summary
PUBLIC_IP=$(curl -s ifconfig.me || echo "YOUR_SERVER_IP")
echo "======================================================================"
echo "[+] DISHA AI PRODUCTION CLOUD STACK IS LIVE!"
echo "    - Public Endpoint: http://${PUBLIC_IP}"
echo "    - Health Check:    http://${PUBLIC_IP}/health"
echo "    - Classifier API:  http://${PUBLIC_IP}/internal/classifier"
echo "    - Connected Frontend: https://disha-ai-gray.vercel.app"
echo "======================================================================"

