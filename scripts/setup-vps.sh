#!/usr/bin/env bash
# =============================================================================
# First-time VPS setup for infrakt
#
# Run this once on a fresh VPS to install Docker, create the directory
# structure, and start the infrakt dashboard.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/E4Dev-Solutions/e4dev-infrakt/main/scripts/setup-vps.sh | bash
#   # or
#   scp scripts/setup-vps.sh root@<vps-ip>:/tmp/ && ssh root@<vps-ip> bash /tmp/setup-vps.sh
# =============================================================================
set -euo pipefail

echo "==> Setting up infrakt on $(hostname)"

# --- Install Docker if not present -------------------------------------------
if ! command -v docker &>/dev/null; then
    echo "==> Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    echo "==> Docker already installed ($(docker --version))"
fi

# --- Create infrakt directory ------------------------------------------------
echo "==> Creating /opt/infrakt/"
mkdir -p /opt/infrakt/ssh
cd /opt/infrakt

# --- Download production compose file ----------------------------------------
echo "==> Downloading docker-compose.prod.yml"
curl -fsSL https://raw.githubusercontent.com/E4Dev-Solutions/e4dev-infrakt/main/docker-compose.prod.yml \
    -o docker-compose.prod.yml

# --- Generate a random webhook secret ----------------------------------------
WEBHOOK_SECRET=$(openssl rand -hex 32)

# --- Create .env configuration -----------------------------------------------
if [ ! -f .env ]; then
    cat > .env <<ENVEOF
# SSH key directory to mount into the container (read-only).
# Place your SSH private keys here so infrakt can manage remote servers.
SSH_KEY_PATH=/opt/infrakt/ssh

# GitHub webhook secret for automatic self-updates.
# Add this same value to your GitHub repo webhook settings.
GITHUB_WEBHOOK_SECRET=${WEBHOOK_SECRET}

# Optional: comma-separated CORS origins.
# Leave empty for same-origin only (default, recommended).
# CORS_ORIGINS=https://infrakt.example.com
ENVEOF
    echo "==> Created .env with webhook secret"
else
    echo "==> .env already exists, skipping"
    WEBHOOK_SECRET="(check your existing .env file)"
fi

# --- Pull and start ----------------------------------------------------------
echo "==> Pulling infrakt image..."
docker compose -f docker-compose.prod.yml pull

echo "==> Starting infrakt..."
docker compose -f docker-compose.prod.yml up -d

# --- Print next steps --------------------------------------------------------
VPS_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=============================================="
echo "  infrakt is running!"
echo "=============================================="
echo ""
echo "  Dashboard: http://${VPS_IP}:8000"
echo ""
echo "  Next steps:"
echo ""
echo "    1. Copy your SSH keys to /opt/infrakt/ssh/"
echo "       scp ~/.ssh/id_ed25519 root@${VPS_IP}:/opt/infrakt/ssh/"
echo ""
echo "    2. Get your API key:"
echo "       docker compose -f docker-compose.prod.yml exec infrakt \\"
echo "         cat /home/infrakt/.infrakt/api_key.txt"
echo ""
echo "    3. Open the dashboard and log in with the API key"
echo ""
echo "    4. Set up GitHub webhook for auto-deploy:"
echo "       - Go to your repo → Settings → Webhooks → Add webhook"
echo "       - Payload URL: http://${VPS_IP}:8000/api/self-update"
echo "       - Content type: application/json"
echo "       - Secret: ${WEBHOOK_SECRET}"
echo "       - Events: Just the push event"
echo ""
echo "    Now every push to main will auto-deploy!"
echo "=============================================="
