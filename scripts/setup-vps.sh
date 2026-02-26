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

# --- Free ports 80/443 -------------------------------------------------------
# The Caddy sidecar needs ports 80 and 443. Stop any services that might
# be holding them (common on previously-provisioned or pre-configured VPSes).
echo "==> Freeing ports 80/443..."
for svc in caddy nginx apache2 httpd; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        echo "    Stopping $svc..."
        systemctl stop "$svc"
        systemctl disable "$svc"
    fi
done

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

# --- Wait for healthy container -----------------------------------------------
# Poll Docker's own health status rather than exec-ing into the container.
# This is more reliable and doesn't depend on the container being ready for exec.
echo "==> Waiting for infrakt container to be healthy..."
ATTEMPTS=0
MAX_ATTEMPTS=40
while true; do
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' infrakt-infrakt-1 2>/dev/null || echo "starting")
    if [ "$HEALTH" = "healthy" ]; then
        echo "    Container is healthy."
        break
    fi
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
        echo "==> WARNING: Container did not become healthy within $((MAX_ATTEMPTS * 3))s"
        echo "    Current status: ${HEALTH}"
        echo "    Check logs: docker compose -f docker-compose.prod.yml logs"
        break
    fi
    sleep 3
done

# --- Retrieve API key ---------------------------------------------------------
# The API key is generated at app startup and written to the volume.
# Wait for the file to appear (may take a moment after container reports healthy).
echo "==> Retrieving API key..."
API_KEY=""
for _ in $(seq 1 20); do
    API_KEY=$(docker compose -f docker-compose.prod.yml exec -T infrakt \
        cat /home/infrakt/.infrakt/api_key.txt 2>/dev/null || true)
    if [[ -n "$API_KEY" ]]; then
        break
    fi
    sleep 2
done

# --- Generate SSH key for server self-management ------------------------------
# infrakt runs inside a container and needs SSH access to the host to manage it.
# Generate a dedicated key pair, place the private key where the container can
# read it, and add the public key to root's authorized_keys on the host.
SSH_KEY_FILE="${INSTALL_DIR}/ssh/id_ed25519"
if [ ! -f "$SSH_KEY_FILE" ]; then
    echo "==> Generating SSH key for server management..."
    ssh-keygen -t ed25519 -f "$SSH_KEY_FILE" -N "" -C "infrakt@$(hostname)" -q
    chmod 600 "$SSH_KEY_FILE"

    # Authorize the key on the host so the container can SSH to 172.17.0.1
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    cat "${SSH_KEY_FILE}.pub" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    echo "    Key generated and added to /root/.ssh/authorized_keys"
else
    echo "==> SSH key already exists at ${SSH_KEY_FILE}, skipping"
fi

# --- Verify HTTPS -------------------------------------------------------------
echo "==> Verifying HTTPS..."
HTTPS_OK=false
for _ in $(seq 1 10); do
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "https://${DOMAIN}/api/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        HTTPS_OK=true
        break
    fi
    sleep 3
done

# --- Register host as managed server -----------------------------------------
# The container reaches the host via Docker's bridge gateway IP (172.17.0.1).
# The SSH key mounted at /home/infrakt/.ssh/id_ed25519 authenticates the connection.
DOCKER_BRIDGE_IP="172.17.0.1"
SERVER_NAME="$(hostname)"

if [[ -n "$API_KEY" ]]; then
    echo "==> Registering host as managed server '${SERVER_NAME}'..."
    # Use the HTTPS endpoint via Caddy (port 8000 is not exposed to the host)
    REG_RESPONSE=$(curl -s -w '\n%{http_code}' \
        -X POST "https://${DOMAIN}/api/servers" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: ${API_KEY}" \
        -d "{\"name\": \"${SERVER_NAME}\", \"host\": \"${DOCKER_BRIDGE_IP}\", \"user\": \"root\", \"port\": 22, \"ssh_key_path\": \"id_ed25519\"}" \
        2>/dev/null || echo -e "\n000")
    REG_CODE=$(echo "$REG_RESPONSE" | tail -1)

    if [ "$REG_CODE" = "200" ] || [ "$REG_CODE" = "201" ]; then
        echo "    Server '${SERVER_NAME}' registered (host: ${DOCKER_BRIDGE_IP})"
    elif [ "$REG_CODE" = "409" ]; then
        echo "    Server '${SERVER_NAME}' already registered"
    else
        echo "    WARNING: Server registration returned HTTP ${REG_CODE}"
        echo "    You can add it manually via the dashboard"
    fi
else
    echo "==> Skipping server registration (no API key available)"
fi

# --- Print summary ------------------------------------------------------------
VPS_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=============================================="
echo "  infrakt is running!"
echo "=============================================="
echo ""
if [ "$HTTPS_OK" = true ]; then
    echo "  Dashboard: https://${DOMAIN}  [HTTPS verified]"
else
    echo "  Dashboard: https://${DOMAIN}  [HTTPS pending — may need DNS propagation]"
    echo "  Fallback:  http://${VPS_IP}:8000  (direct, no TLS)"
fi
echo ""
if [[ -n "$API_KEY" ]]; then
    echo "  API Key: ${API_KEY}"
else
    echo "  API Key: (not ready yet — retrieve manually)"
    echo "    cd ${INSTALL_DIR} && docker compose -f docker-compose.prod.yml exec infrakt cat /home/infrakt/.infrakt/api_key.txt"
fi
echo ""
echo "  Server: '${SERVER_NAME}' registered at ${DOCKER_BRIDGE_IP}"
echo ""
echo "  GitHub Webhook (auto-deploy):"
echo "    URL:     https://${DOMAIN}/api/self-update"
echo "    Secret:  ${WEBHOOK_SECRET}"
echo "    Events:  Just the push event"
echo ""
echo "=============================================="
