# Deploying infrakt to a VPS

Step-by-step guide to deploy the infrakt dashboard to a VPS with a custom domain and automatic HTTPS.

## Prerequisites

- A VPS running Ubuntu 22.04+ (or any Linux with systemd)
- A domain name with DNS access
- SSH access to the VPS as root

## Step 1: Point your domain to the VPS

At your domain registrar (Cloudflare, Namecheap, etc.):

1. Add an **A record**: `infrakt.yourdomain.com` → `<your-vps-ip>`
2. If using Cloudflare, set proxy to **DNS only** (gray cloud) so Caddy can obtain the TLS certificate

## Step 2: SSH into your VPS

```bash
ssh root@<your-vps-ip>
```

## Step 3: Run the setup script

Since the repo is private, copy the files from your local machine first:

```bash
# From your local machine (not the VPS):
scp scripts/setup-vps.sh docker-compose.prod.yml root@<your-vps-ip>:/tmp/
```

Then on the VPS:

```bash
bash /tmp/setup-vps.sh
```

> **Alternative (with GitHub PAT):** If you prefer a one-liner, create a [Personal Access Token](https://github.com/settings/tokens) with `repo` scope, then:
> ```bash
> curl -fsSL -H "Authorization: token <YOUR_PAT>" \
>   https://raw.githubusercontent.com/E4Dev-Solutions/e4dev-infrakt/main/scripts/setup-vps.sh \
>   | bash -s -- --token <YOUR_PAT>
> ```

This will:
- Install Docker (if not already installed)
- Create `/opt/infrakt/` directory structure
- Download `docker-compose.prod.yml`
- Generate a GitHub webhook secret
- Pull the infrakt Docker image from GHCR
- Start the infrakt container on port 8000

## Step 4: Install Caddy for HTTPS + domain

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install caddy
```

Configure the reverse proxy:

```bash
cat > /etc/caddy/Caddyfile << 'EOF'
infrakt.yourdomain.com {
    reverse_proxy localhost:8000
}
EOF

systemctl reload caddy
```

Caddy automatically obtains a Let's Encrypt TLS certificate. Your dashboard is now available at `https://infrakt.yourdomain.com`.

## Step 5: Copy your SSH keys

These are the keys infrakt uses to manage your remote servers:

```bash
scp ~/.ssh/id_ed25519 root@<your-vps-ip>:/opt/infrakt/ssh/
```

Alternatively, you can generate and manage SSH keys through the dashboard later (Settings → SSH Keys → Generate Key).

## Step 6: Get your API key and log in

```bash
docker compose -f /opt/infrakt/docker-compose.prod.yml exec infrakt cat /home/infrakt/.infrakt/api_key.txt
```

Open `https://infrakt.yourdomain.com` in your browser and paste the API key to log in.

## Step 7: Set up auto-deploy webhook

Every push to `main` will automatically update infrakt on your VPS.

1. Get the webhook secret from the VPS:
   ```bash
   grep GITHUB_WEBHOOK_SECRET /opt/infrakt/.env
   ```

2. In your GitHub repo, go to **Settings → Webhooks → Add webhook**:
   - **Payload URL:** `https://infrakt.yourdomain.com/api/self-update`
   - **Content type:** `application/json`
   - **Secret:** the value from the previous step
   - **Events:** select **Just the push event**
   - Click **Add webhook**

Now every push to `main` triggers: GitHub Actions builds and pushes the Docker image to GHCR → GitHub sends a webhook to your VPS → infrakt pulls the new image and restarts itself.

## Step 8: (Optional) Configure CORS

If you need CORS for a separate frontend, edit `/opt/infrakt/.env`:

```bash
CORS_ORIGINS=https://infrakt.yourdomain.com
```

Then restart:

```bash
cd /opt/infrakt && docker compose -f docker-compose.prod.yml up -d
```

> **Note:** CORS is not needed when accessing the dashboard directly at the domain since FastAPI serves the frontend as same-origin static files.

## Firewall

Make sure your VPS firewall allows ports 22 (SSH), 80 (HTTP), and 443 (HTTPS):

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

## Troubleshooting

**Check if infrakt is running:**
```bash
docker compose -f /opt/infrakt/docker-compose.prod.yml ps
```

**View infrakt logs:**
```bash
docker compose -f /opt/infrakt/docker-compose.prod.yml logs -f
```

**Check Caddy status:**
```bash
systemctl status caddy
journalctl -u caddy --no-pager -n 50
```

**Restart infrakt:**
```bash
cd /opt/infrakt && docker compose -f docker-compose.prod.yml restart
```

**Manually pull latest image:**
```bash
cd /opt/infrakt && docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d
```
