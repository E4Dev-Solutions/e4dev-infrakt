# Auto-Domain Assignment

## Summary

Automatically assign a random subdomain to every app that doesn't have an explicit domain, using a globally configured base domain (e.g., `infrakt.cloud`). This eliminates the need to manually configure domains for every deployment.

## Prerequisites

- Wildcard DNS A record: `*.infrakt.cloud → server IP`
- No wildcard TLS cert needed — each subdomain gets its own Let's Encrypt cert via HTTP-01 (existing Traefik flow)

## Design

### Global Setting: `base_domain`

Stored in `~/.infrakt/settings.json` alongside existing S3 and backup policy settings.

- **API:** `GET/PUT /api/settings/domain` — `{"base_domain": "infrakt.cloud"}`
- **CLI:** `infrakt config set base-domain infrakt.cloud`
- **Dashboard:** Settings page, new "Domain" section with input field

### Domain Generation

When an app is created without a `domain` (and `base_domain` is configured):

1. Generate 8-char random hex: `secrets.token_hex(4)` → `a3f2b7c1`
2. Compose: `a3f2b7c1.infrakt.cloud`
3. Store in app's `domain` column — identical to manually-set domains
4. Returned in API response so the user sees the assigned URL

No auto-domain if:
- App already has a `domain` or `domains` set
- `base_domain` is not configured
- App type is `db:*` (databases don't need domains)

### Multi-domain templates

For multi-service templates (e.g., devtools), each routable service gets its own random subdomain:

```json
{"gitea": "c4e8f1a2.infrakt.cloud", "portainer": "7b3d9e5f.infrakt.cloud"}
```

### TLS

No changes. Each auto-generated subdomain gets an individual Let's Encrypt cert via the existing HTTP-01 ACME challenge. The per-domain Traefik route file already includes `certResolver: letsencrypt`.

Rate limit: 50 certs/week per registered domain (Let's Encrypt). Unlikely to hit in practice.

## Changes

### Backend

- `api/routes/settings.py` — add `GET/PUT /api/settings/domain` endpoints
- `api/routes/apps.py` — in app create handler, if no domain provided and `base_domain` exists, generate random subdomain and set it on the app before deploy
- `api/schemas.py` — add `DomainSettings` Pydantic model
- `cli/commands/app.py` — same auto-assign logic in CLI `app create`
- Helper function `generate_auto_domain(base_domain: str) -> str` in `cli/core/config.py` or a new utility

### Frontend

- `frontend/src/pages/Settings.tsx` — add "Base Domain" input in Settings page
- `frontend/src/pages/Apps.tsx` — create app form: if no domain entered, show hint that one will be auto-assigned

### No changes needed

- `cli/core/proxy_manager.py` — already handles per-domain route files
- Traefik config — existing HTTP-01 ACME works per-subdomain
- `cli/core/deployer.py` — receives domain from caller, unchanged
