# Server Pages Redesign — Design Doc

**Goal:** Redesign the Servers list page and Server Detail page to match the Onyx Forge aesthetic and the AppDetail redesign patterns (tab layout, inline settings, grouped actions).

**Pages affected:** `Servers.tsx` (list), `ServerDetail.tsx` (detail)

---

## Servers List Page — Card Grid

Replace the current table with a responsive card grid (`grid-cols-1 md:grid-cols-2 xl:grid-cols-3`).

Each server card shows:
- Server name (link to detail page) + status badge
- Connection string (`user@host:port`) + provider
- Mini resource bars (CPU, MEM, DSK) with percentage — fetched via `useServerStatus` for active servers only; inactive servers show "offline" placeholder
- App count with icon
- Tags row at bottom

Card hover state: subtle border glow (`orange-500/20`).

Header retains the "Add Server" button opening the existing modal.

---

## Server Detail — Header & Actions

Matches AppDetail header pattern:

- Back link: "Back to Servers"
- Server name as `h1`
- Single-line subtitle: status badge, provider, connection string (`user@host:port`)
- Action buttons grouped by importance:
  - **Provision** — primary emerald CTA (like Deploy on AppDetail)
  - **Test Connection**, **Restart Traefik** — secondary zinc-700
  - **Kebab menu** — contains "Delete Server"
- Provisioning progress panel appears inline below header when active

---

## Server Detail — Tabs

Three tabs: **Overview** (default), **Apps**, **Settings**

### Overview Tab

- **Stat cards** (4 in a row): Status, Uptime, Apps count, Containers count
- **Resource Usage + Quick Info** (2-column):
  - Left: CPU/MEM/DSK usage bars with color thresholds (green < 60%, amber < 85%, red >= 85%) + Refresh button
  - Right: Host, User, Port, Provider, SSH Key
- **24h Metrics History**: Reuse existing SparklineChart component for CPU, MEM, DSK
- **Running Containers**: Table with name, image, status columns

### Apps Tab

- List of apps deployed to this server, each row linking to app detail
- Each row shows: name, status badge, app type + branch/image, domain, last deploy relative time
- Empty state: "No apps deployed to this server yet." with link to Apps page

### Settings Tab

Matches AppDetail Settings pattern:

- **General section**: Host/IP, SSH User, SSH Port, SSH Key Path, Provider (dropdown)
- **Tags section**: Pill badges with X to remove, input + Add button
- **Save Changes button**: Disabled until form is dirty (comparing form values against server data)
- **Danger Zone**: Collapsed by default, expands to show type-to-confirm delete (type server name to enable Delete Server button)

Edit modal is removed entirely.

---

## Design Principles

- Consistent with AppDetail redesign (tab layout, inline settings, kebab menu, stat cards)
- Onyx Forge theme: zinc-950 base, orange-500/600 accent, Outfit + JetBrains Mono
- Lazy resource fetching on list page (only active servers)
- Dirty-state detection on Settings form
- Type-to-confirm for destructive actions
