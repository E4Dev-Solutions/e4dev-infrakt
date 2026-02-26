#!/usr/bin/env bash
# =============================================================================
# First-time VPS setup for infrakt
#
# Provisions the host (Docker, Traefik, UFW, fail2ban), authenticates to GHCR,
# downloads the production compose file, starts the stack, registers the host
# as a managed server, triggers provisioning via the API, and configures
# GitHub Actions secrets for CD auto-deploy.
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

# =============================================================================
# Phase 1: Provision the host
# =============================================================================

# --- Install Docker if not present -------------------------------------------
if ! command -v docker &>/dev/null; then
    echo "==> Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    echo "==> Docker already installed ($(docker --version))"
fi

# --- Stop conflicting services -----------------------------------------------
echo "==> Stopping conflicting services on ports 80/443..."
for svc in nginx apache2 httpd caddy; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        echo "    Stopping $svc..."
        systemctl stop "$svc"
        systemctl disable "$svc"
    fi
done

# --- Install fail2ban --------------------------------------------------------
echo "==> Installing fail2ban..."
apt-get install -y -qq fail2ban
systemctl enable fail2ban && systemctl start fail2ban

# --- Configure UFW firewall --------------------------------------------------
echo "==> Configuring UFW firewall..."
apt-get install -y -qq ufw
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw default allow outgoing
echo 'y' | ufw enable || true

# --- Create directory structure -----------------------------------------------
echo "==> Creating ${INSTALL_DIR}/"
mkdir -p "${INSTALL_DIR}/apps" "${INSTALL_DIR}/traefik/conf.d" "${INSTALL_DIR}/traefik/letsencrypt" "${INSTALL_DIR}/backups" "${INSTALL_DIR}/ssh"

# --- Create Docker network ---------------------------------------------------
docker network create infrakt 2>/dev/null || true

# --- Configure Traefik -------------------------------------------------------
echo "==> Configuring Traefik for ${DOMAIN}..."

# Sanitize domain for use as identifier
SANITIZED_DOMAIN=$(echo "${DOMAIN}" | sed 's/[^a-zA-Z0-9-]/-/g' | sed 's/^-//;s/-$//')

# Write Traefik static config
if [ ! -f "${INSTALL_DIR}/traefik/traefik.yml" ]; then
    cat > "${INSTALL_DIR}/traefik/traefik.yml" <<TRAEFIKEOF
api:
  dashboard: true
  insecure: true

entryPoints:
  web:
    address: ':80'
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: ':443'

certificatesResolvers:
  letsencrypt:
    acme:
      email: ''
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web

providers:
  file:
    directory: /opt/infrakt/traefik/conf.d
    watch: true

log:
  level: INFO
TRAEFIKEOF
    echo "    Traefik static config written"
else
    echo "    Traefik static config already exists, skipping"
fi

# Write Traefik docker-compose.yml
if [ ! -f "${INSTALL_DIR}/traefik/docker-compose.yml" ]; then
    cat > "${INSTALL_DIR}/traefik/docker-compose.yml" <<COMPOSEEOF
services:
  traefik:
    image: traefik:v3.2
    container_name: infrakt-traefik
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "127.0.0.1:8080:8080"
    volumes:
      - /opt/infrakt/traefik/traefik.yml:/etc/traefik/traefik.yml:ro
      - /opt/infrakt/traefik/conf.d:/opt/infrakt/traefik/conf.d:ro
      - /opt/infrakt/traefik/letsencrypt:/letsencrypt
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - infrakt

networks:
  infrakt:
    external: true
COMPOSEEOF
    echo "    Traefik docker-compose.yml written"
else
    echo "    Traefik docker-compose.yml already exists, skipping"
fi

# Initialize ACME storage
touch "${INSTALL_DIR}/traefik/letsencrypt/acme.json"
chmod 600 "${INSTALL_DIR}/traefik/letsencrypt/acme.json"

# Write domain config for the infrakt dashboard
if [ ! -f "${INSTALL_DIR}/traefik/conf.d/${SANITIZED_DOMAIN}.yml" ]; then
    cat > "${INSTALL_DIR}/traefik/conf.d/${SANITIZED_DOMAIN}.yml" <<ROUTEEOF
http:
  routers:
    ${SANITIZED_DOMAIN}:
      rule: "Host(\`${DOMAIN}\`)"
      entryPoints:
        - websecure
      service: svc-${SANITIZED_DOMAIN}
      tls:
        certResolver: letsencrypt
    ${SANITIZED_DOMAIN}-http:
      rule: "Host(\`${DOMAIN}\`)"
      entryPoints:
        - web
      service: svc-${SANITIZED_DOMAIN}

  services:
    svc-${SANITIZED_DOMAIN}:
      loadBalancer:
        servers:
          - url: "http://infrakt-app:8000"
        passHostHeader: true
ROUTEEOF
    echo "    Domain route config written for ${DOMAIN}"
else
    echo "    Domain route config already exists for ${DOMAIN}, skipping"
fi

# Start Traefik
echo "==> Starting Traefik..."
cd "${INSTALL_DIR}/traefik" && docker compose up -d
cd "${INSTALL_DIR}"

echo "==> Host provisioning complete"

# =============================================================================
# Phase 2: Deploy infrakt
# =============================================================================

# --- Authenticate to GHCR ----------------------------------------------------
echo "==> Logging in to GitHub Container Registry..."
echo "${TOKEN}" | docker login ghcr.io -u _token --password-stdin

cd "${INSTALL_DIR}"

# --- Download docker-compose.prod.yml from private repo -----------------------
echo "==> Downloading docker-compose.prod.yml..."
curl -fsSL \
    -H "Authorization: token ${TOKEN}" \
    -H "Accept: application/vnd.github.v3.raw" \
    "https://api.github.com/repos/${REPO}/contents/docker-compose.prod.yml?ref=${BRANCH}" \
    -o docker-compose.prod.yml

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
    # Read the existing secret so we can use it for the GitHub webhook
    WEBHOOK_SECRET=$(grep '^GITHUB_WEBHOOK_SECRET=' .env | cut -d= -f2)
fi

# --- Pull and start -----------------------------------------------------------
echo "==> Pulling images..."
docker compose -f docker-compose.prod.yml pull

echo "==> Starting infrakt..."
docker compose -f docker-compose.prod.yml up -d

# --- Wait for healthy container -----------------------------------------------
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
SSH_KEY_FILE="${INSTALL_DIR}/ssh/id_ed25519"
if [ ! -f "$SSH_KEY_FILE" ]; then
    echo "==> Generating SSH key for server management..."
    ssh-keygen -t ed25519 -f "$SSH_KEY_FILE" -N "" -C "infrakt@$(hostname)" -q
    # The container runs as UID 1000 (infrakt user). Set ownership so the
    # container can read the key through the read-only volume mount.
    chown 1000:1000 "$SSH_KEY_FILE" "${SSH_KEY_FILE}.pub"
    chmod 600 "$SSH_KEY_FILE"

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

# =============================================================================
# Phase 3: Register and provision the host server
# =============================================================================
DOCKER_BRIDGE_IP="172.17.0.1"
SERVER_NAME="$(hostname)"

if [[ -n "$API_KEY" ]]; then
    echo "==> Registering host as managed server '${SERVER_NAME}'..."
    REG_RESPONSE=$(curl -s -w '\n%{http_code}' \
        -X POST "https://${DOMAIN}/api/servers" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: ${API_KEY}" \
        -d "{\"name\": \"${SERVER_NAME}\", \"host\": \"${DOCKER_BRIDGE_IP}\", \"user\": \"root\", \"port\": 22, \"ssh_key_path\": \"/home/infrakt/.ssh/id_ed25519\"}" \
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

    # --- Provision via API (sets status to "active") ----------------------------
    # The host is already provisioned (Phase 1), so the provisioner steps will
    # mostly be no-ops. This call ensures the server status is set to "active"
    # in the database once provisioning completes successfully.
    echo "==> Provisioning server '${SERVER_NAME}' via API..."
    PROV_RESPONSE=$(curl -s -w '\n%{http_code}' \
        -X POST "https://${DOMAIN}/api/servers/${SERVER_NAME}/provision" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: ${API_KEY}" \
        2>/dev/null || echo -e "\n000")
    PROV_CODE=$(echo "$PROV_RESPONSE" | tail -1)

    if [ "$PROV_CODE" = "200" ]; then
        echo "    Provisioning started, waiting for completion..."
        PROV_ATTEMPTS=0
        PROV_MAX=60
        while true; do
            SRV_STATUS=$(curl -s \
                "https://${DOMAIN}/api/servers" \
                -H "X-API-Key: ${API_KEY}" \
                2>/dev/null | python3 -c "
import sys, json
servers = json.load(sys.stdin)
for s in servers:
    if s['name'] == '${SERVER_NAME}':
        print(s['status'])
        break
" 2>/dev/null || echo "unknown")

            if [ "$SRV_STATUS" = "active" ]; then
                echo "    Server '${SERVER_NAME}' is now active!"
                break
            elif [ "$SRV_STATUS" = "inactive" ] && [ "$PROV_ATTEMPTS" -gt 10 ]; then
                echo "    WARNING: Provisioning may have failed (status: ${SRV_STATUS})"
                echo "    Check logs: docker compose -f docker-compose.prod.yml logs infrakt"
                break
            fi
            PROV_ATTEMPTS=$((PROV_ATTEMPTS + 1))
            if [ "$PROV_ATTEMPTS" -ge "$PROV_MAX" ]; then
                echo "    WARNING: Provisioning did not complete within $((PROV_MAX * 5))s"
                echo "    Current status: ${SRV_STATUS}"
                break
            fi
            sleep 5
        done
    else
        echo "    WARNING: Provision request returned HTTP ${PROV_CODE}"
        echo "    You can provision manually via the dashboard"
    fi
else
    echo "==> Skipping server registration and provisioning (no API key available)"
fi

# --- Set GitHub Actions secrets for CD auto-deploy ----------------------------
# The CD workflow triggers the self-update endpoint after pushing the Docker
# image, so the deploy always uses the freshly-built image (no race condition).
DEPLOY_URL="https://${DOMAIN}/api/self-update"
if [[ -n "$WEBHOOK_SECRET" ]]; then
    echo "==> Setting GitHub Actions secrets for CD auto-deploy..."

    # Use the GitHub API to set repository secrets (encrypted with libsodium).
    # This requires the PAT to have the 'repo' scope.
    _set_gh_secret() {
        local SECRET_NAME="$1"
        local SECRET_VALUE="$2"

        # Get the repo public key for encrypting secrets
        KEY_RESPONSE=$(curl -s \
            -H "Authorization: token ${TOKEN}" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/${REPO}/actions/secrets/public-key" 2>/dev/null)

        KEY_ID=$(echo "$KEY_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['key_id'])" 2>/dev/null || echo "")
        PUBLIC_KEY=$(echo "$KEY_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])" 2>/dev/null || echo "")

        if [[ -z "$KEY_ID" ]] || [[ -z "$PUBLIC_KEY" ]]; then
            echo "    WARNING: Could not retrieve repo public key"
            return 1
        fi

        # Encrypt the secret using libsodium sealed box via Python
        ENCRYPTED=$(python3 -c "
from base64 import b64encode, b64decode
from nacl.public import SealedBox, PublicKey
public_key = b64decode('${PUBLIC_KEY}')
sealed_box = SealedBox(PublicKey(public_key))
encrypted = sealed_box.encrypt(b'${SECRET_VALUE}')
print(b64encode(encrypted).decode())
" 2>/dev/null || echo "")

        if [[ -z "$ENCRYPTED" ]]; then
            # Fallback: try with pip install pynacl
            pip install -q pynacl 2>/dev/null
            ENCRYPTED=$(python3 -c "
from base64 import b64encode, b64decode
from nacl.public import SealedBox, PublicKey
public_key = b64decode('${PUBLIC_KEY}')
sealed_box = SealedBox(PublicKey(public_key))
encrypted = sealed_box.encrypt(b'${SECRET_VALUE}')
print(b64encode(encrypted).decode())
" 2>/dev/null || echo "")
        fi

        if [[ -z "$ENCRYPTED" ]]; then
            echo "    WARNING: Could not encrypt secret (pynacl not available)"
            return 1
        fi

        RESP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
            -X PUT "https://api.github.com/repos/${REPO}/actions/secrets/${SECRET_NAME}" \
            -H "Authorization: token ${TOKEN}" \
            -H "Accept: application/vnd.github.v3+json" \
            -d "{\"encrypted_value\":\"${ENCRYPTED}\",\"key_id\":\"${KEY_ID}\"}" 2>/dev/null)

        if [ "$RESP_CODE" = "201" ] || [ "$RESP_CODE" = "204" ]; then
            echo "    ${SECRET_NAME} set successfully"
            return 0
        else
            echo "    WARNING: Setting ${SECRET_NAME} returned HTTP ${RESP_CODE}"
            return 1
        fi
    }

    if _set_gh_secret "DEPLOY_URL" "$DEPLOY_URL" && _set_gh_secret "DEPLOY_SECRET" "$WEBHOOK_SECRET"; then
        echo "    CD auto-deploy configured via GitHub Actions"
    else
        echo "    WARNING: Could not set GitHub Actions secrets automatically"
        echo "    Set them manually in GitHub repo > Settings > Secrets:"
        echo "      DEPLOY_URL    = ${DEPLOY_URL}"
        echo "      DEPLOY_SECRET = ${WEBHOOK_SECRET}"
    fi
else
    echo "==> Skipping CD auto-deploy setup (no webhook secret available)"
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
echo "  Server: '${SERVER_NAME}' registered and provisioned at ${DOCKER_BRIDGE_IP}"
echo ""
echo "  Auto-deploy: CD workflow triggers self-update after image push"
echo "    Endpoint: https://${DOMAIN}/api/self-update"
echo "    Secrets:  DEPLOY_URL + DEPLOY_SECRET set in GitHub Actions"
echo ""
echo "=============================================="
