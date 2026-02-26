# Deploying infrakt to a VPS

One-command deployment of the infrakt dashboard to a fresh VPS with automatic HTTPS, server registration, and CD pipeline.

## Prerequisites

- A fresh VPS running Ubuntu 22.04+ with root SSH access
- A domain with a DNS A record pointing to the VPS IP
- A GitHub PAT with these scopes:
  - `read:packages` — pull the Docker image from GHCR
  - `repo` — set GitHub Actions secrets for CD auto-deploy (optional; script handles gracefully if missing)

> **Cloudflare users:** Set the DNS proxy to **DNS only** (gray cloud) so Caddy can obtain the TLS certificate directly.

## Deploy

From your local machine:

```bash
scp scripts/setup-vps.sh root@<your-vps-ip>:/tmp/
ssh root@<your-vps-ip> bash /tmp/setup-vps.sh \
  --domain infrakt.yourdomain.com \
  --token <your-github-pat>
```

That's it. The script handles everything:

**Phase 1 — Provision host:**
- Installs Docker, Caddy, fail2ban, UFW (ports 22/80/443)
- Creates `/opt/infrakt/` directory structure and Docker network
- Configures host Caddy with your domain → `localhost:8000`

**Phase 2 — Deploy infrakt:**
- Authenticates to GHCR and pulls the Docker image
- Downloads `docker-compose.prod.yml` from the private repo
- Generates `.env` with a webhook secret
- Starts the container and waits for it to be healthy
- Generates an SSH key for server self-management
- Verifies HTTPS is working

**Phase 3 — Register and activate:**
- Registers the host as a managed server via the API
- Triggers provisioning to set server status to "active"
- Sets GitHub Actions secrets (`DEPLOY_URL`, `DEPLOY_SECRET`) for CD auto-deploy

At the end, the script prints:
- Dashboard URL (with HTTPS status)
- API key (paste into the dashboard login)
- Auto-deploy configuration status

## After Deployment

### Log in to the dashboard

Open `https://infrakt.yourdomain.com` and paste the API key from the setup output.

### Auto-deploy pipeline

Already configured. The flow is:

1. Push to `main`
2. GitHub Actions builds and pushes the Docker image to GHCR (CD workflow)
3. After the image is pushed, CD workflow calls the self-update endpoint
4. infrakt verifies the HMAC signature, pulls the new image, and restarts

The CD workflow uses two GitHub Actions secrets (`DEPLOY_URL` and `DEPLOY_SECRET`) set automatically during setup. This ensures the deploy only triggers **after** the image is built, avoiding race conditions.

> If the setup script couldn't set the secrets automatically, add them manually in your repo's **Settings → Secrets and variables → Actions**:
> - `DEPLOY_URL` = `https://infrakt.yourdomain.com/api/self-update`
> - `DEPLOY_SECRET` = the `GITHUB_WEBHOOK_SECRET` value from `/opt/infrakt/.env`

## Script Options

```
--domain   Domain for HTTPS (required)
--token    GitHub PAT (required)
--repo     GitHub repo (default: E4Dev-Solutions/e4dev-infrakt)
--branch   Git branch (default: main)
```

## Architecture

```
Internet → Caddy (host, ports 80/443, auto-HTTPS)
             → localhost:8000
                → infrakt container (Docker)
                    → manages servers via SSH (Docker bridge 172.17.0.1)
```

- Caddy runs on the host (not as a sidecar container) to avoid port conflicts when provisioning
- The container exposes port 8000 on localhost only
- Server self-management uses an SSH key at `/opt/infrakt/ssh/id_ed25519` mounted read-only into the container

## Teardown

To completely remove infrakt from the server:

```bash
ssh root@<your-vps-ip> "\
  cd /opt/infrakt && \
  docker compose -f docker-compose.prod.yml down -v && \
  systemctl stop caddy && \
  rm -rf /opt/infrakt/*"
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

**Re-run setup on an existing server:**
The script is idempotent — it skips steps that are already done (Docker installed, .env exists, SSH key exists, etc.).
