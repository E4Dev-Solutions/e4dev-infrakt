#!/usr/bin/env bash
# =============================================================================
# First-time VPS setup for infrakt
#
# Installs Docker, authenticates to GHCR, downloads the production compose
# file, generates a Caddyfile for automatic HTTPS, and starts the stack.
#
# Usage:
#   bash setup-vps.sh --domain infrakt.example.com --token ghp_xxx
#
# Prerequisites:
#   - Fresh Ubuntu 22.04+ VPS with root SSH access
#   - A domain with DNS A record pointing to this server's IP
#   - A GitHub PAT with read:packages scope
# =============================================================================
set -euo pipefail

# --- Parse arguments ---------------------------------------------------------
DOMAIN=""
TOKEN=""
REPO="E4Dev-Solutions/e4dev-infrakt"
BRANCH="main"
INSTALL_DIR="/opt/infrakt"

usage() {
    echo "Usage: $0 --domain <domain> --token <github-pat>"
    echo ""
    echo "  --domain   Domain for HTTPS (e.g. infrakt.example.com)"
    echo "  --token    GitHub PAT with read:packages scope"
    echo "  --repo     GitHub repo (default: ${REPO})"
    echo "  --branch   Git branch (default: ${BRANCH})"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --token)  TOKEN="$2"; shift 2 ;;
        --repo)   REPO="$2"; shift 2 ;;
        --branch) BRANCH="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$DOMAIN" ]]; then
    echo "Error: --domain is required"
    usage
fi

if [[ -z "$TOKEN" ]]; then
    echo "Error: --token is required"
    usage
fi

echo "==> Setting up infrakt on $(hostname)"
echo "    Domain: ${DOMAIN}"
echo "    Repo:   ${REPO} (${BRANCH})"

# --- Install Docker if not present -------------------------------------------
if ! command -v docker &>/dev/null; then
    echo "==> Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    echo "==> Docker already installed ($(docker --version))"
fi

# --- Authenticate to GHCR ----------------------------------------------------
echo "==> Logging in to GitHub Container Registry..."
echo "${TOKEN}" | docker login ghcr.io -u _token --password-stdin

# --- Create directory structure -----------------------------------------------
echo "==> Creating ${INSTALL_DIR}/"
mkdir -p "${INSTALL_DIR}/ssh"
cd "${INSTALL_DIR}"

# --- Download docker-compose.prod.yml from private repo -----------------------
echo "==> Downloading docker-compose.prod.yml..."
curl -fsSL \
    -H "Authorization: token ${TOKEN}" \
    -H "Accept: application/vnd.github.v3.raw" \
    "https://api.github.com/repos/${REPO}/contents/docker-compose.prod.yml?ref=${BRANCH}" \
    -o docker-compose.prod.yml

# --- Generate Caddyfile -------------------------------------------------------
echo "==> Generating Caddyfile for ${DOMAIN}..."
cat > Caddyfile <<CADDYEOF
${DOMAIN} {
    reverse_proxy infrakt:8000
}
CADDYEOF

# --- Generate .env ------------------------------------------------------------
WEBHOOK_SECRET=$(openssl rand -hex 32)

if [ ! -f .env ]; then
    cat > .env <<ENVEOF
# SSH key directory mounted into the container (read-only).
SSH_KEY_PATH=${INSTALL_DIR}/ssh

# GitHub webhook secret for automatic self-updates.
# Add this same value to your GitHub repo webhook settings.
GITHUB_WEBHOOK_SECRET=${WEBHOOK_SECRET}
ENVEOF
    echo "==> Created .env with webhook secret"
else
    echo "==> .env already exists, skipping"
    WEBHOOK_SECRET="(check your existing .env file)"
fi

# --- Pull and start -----------------------------------------------------------
echo "==> Pulling images..."
docker compose -f docker-compose.prod.yml pull

echo "==> Starting infrakt..."
docker compose -f docker-compose.prod.yml up -d

# --- Wait for health check ----------------------------------------------------
echo "==> Waiting for infrakt to be healthy..."
ATTEMPTS=0
MAX_ATTEMPTS=30
until docker compose -f docker-compose.prod.yml exec -T infrakt \
    python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" 2>/dev/null; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
        echo "==> WARNING: Health check did not pass within ${MAX_ATTEMPTS} attempts"
        echo "    Check logs: docker compose -f docker-compose.prod.yml logs"
        break
    fi
    sleep 2
done

# --- Retrieve API key ---------------------------------------------------------
echo "==> Retrieving API key..."
API_KEY=""
for i in $(seq 1 10); do
    API_KEY=$(docker compose -f docker-compose.prod.yml exec -T infrakt \
        cat /home/infrakt/.infrakt/api_key.txt 2>/dev/null || true)
    if [[ -n "$API_KEY" ]]; then
        break
    fi
    sleep 2
done

# --- Print summary ------------------------------------------------------------
VPS_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=============================================="
echo "  infrakt is running!"
echo "=============================================="
echo ""
echo "  Dashboard: https://${DOMAIN}"
echo "  (IP: ${VPS_IP})"
echo ""
if [[ -n "$API_KEY" ]]; then
    echo "  API Key: ${API_KEY}"
else
    echo "  API Key: (not ready yet — retrieve manually)"
    echo "    docker compose -f docker-compose.prod.yml exec infrakt cat /home/infrakt/.infrakt/api_key.txt"
fi
echo ""
echo "  SSH Keys: Copy your keys to ${INSTALL_DIR}/ssh/"
echo "    scp ~/.ssh/id_ed25519 root@${VPS_IP}:${INSTALL_DIR}/ssh/"
echo ""
echo "  GitHub Webhook (auto-deploy):"
echo "    URL:     https://${DOMAIN}/api/self-update"
echo "    Secret:  ${WEBHOOK_SECRET}"
echo "    Events:  Just the push event"
echo ""
echo "=============================================="
