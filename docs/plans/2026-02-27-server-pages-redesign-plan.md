# Server Pages Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the Servers list page (card grid) and Server Detail page (tab layout with Overview, Apps, Settings) to match the AppDetail redesign patterns.

**Architecture:** Replace Servers.tsx table with a responsive card grid showing mini resource bars. Replace ServerDetail.tsx 3-column grid + Edit modal with a tab layout (Overview, Apps, Settings). Reuse existing hooks (useServerStatus, useServerMetrics, useApps) and components (StatusBadge, SparklineChart, UsageBar). Follow AppDetail's TabButton, dirty-state Settings, and kebab menu patterns exactly.

**Tech Stack:** React 19, TanStack Query, Tailwind CSS 4, Lucide React, Playwright E2E

---

### Task 1: Redesign Servers.tsx — Card Grid

**Files:**
- Modify: `frontend/src/pages/Servers.tsx`

**Context:** Currently a table layout (lines 144-237). Replace with a responsive card grid. Each card shows server name, status, connection string, provider, mini resource bars (CPU/MEM/DSK), app count, and tags. Keep the Add Server modal unchanged. The card grid fetches server status lazily — only for active servers.

**What to build:**

Replace the `<table>` block (lines 144-237) with a card grid:

```tsx
{/* Card grid */}
{servers.length > 0 && (
  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
    {servers.map((server) => (
      <ServerCard
        key={server.id}
        server={server}
        onProvision={() => handleProvision(server.name)}
        onDelete={() => handleDelete(server.name)}
        isDeleting={deletingName === server.name}
        isProvisioning={provisionServer.isPending}
      />
    ))}
  </div>
)}
```

Create a `ServerCard` component within the same file, above the `Servers` function. The card fetches `useServerStatus(server.name)` only if `server.status === "active"` (pass `enabled: server.status === "active"` to the hook).

Card layout:
```
┌─────────────────────────────────────────────┐
│  server-name (link)              ● active   │
│  root@203.0.113.10:22            hetzner    │
│─────────────────────────────────────────────│
│  CPU ▓▓▓▓▓░░░  45%                         │
│  MEM ▓▓▓▓▓▓░░  62%        3 apps           │
│  DSK ▓▓░░░░░░  28%                         │
│─────────────────────────────────────────────│
│  Tags: [production] [eu-west]               │
└─────────────────────────────────────────────┘
```

Card classes: `rounded-xl border border-zinc-700 bg-zinc-800 p-5 transition-all hover:border-orange-500/20`

Mini resource bar (inline, not the full UsageBar component):
```tsx
function MiniBar({ label, percent }: { label: string; percent: number }) {
  const color = percent > 85 ? "bg-red-500" : percent > 65 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-7 text-zinc-500">{label}</span>
      <div className="h-1.5 flex-1 rounded-full bg-zinc-700">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
      <span className="w-8 text-right text-zinc-400">{percent.toFixed(0)}%</span>
    </div>
  );
}
```

When status is not loaded (inactive server or still loading), show "Offline" text in zinc-500 instead of the resource bars.

Add `useServerStatus` to the imports from `@/hooks/useApi`. Add `Box` icon import for the app count.

Remove: `ChevronRight` icon (no longer needed — the whole card is not a link, just the name).

Keep the Add Server modal (lines 239-388) and all handlers untouched.

**Step 1:** Replace the table block with the card grid and ServerCard + MiniBar components as described above.

**Step 2:** Run E2E tests to check for regressions:
```bash
cd frontend && npx playwright test servers.spec.ts --reporter=list
```
Expected: Some tests may fail because they reference table-specific selectors. Note which fail.

**Step 3:** Commit:
```bash
git add frontend/src/pages/Servers.tsx
git commit -m "feat: redesign Servers list page with card grid layout"
```

---

### Task 2: Redesign ServerDetail.tsx — Header, Actions, Tabs Structure

**Files:**
- Modify: `frontend/src/pages/ServerDetail.tsx`

**Context:** Currently a flat layout with Edit modal (lines 657-760), 3-column grid (lines 372-655), and inline provisioning panel. Redesign into: header with grouped actions + kebab menu, tab bar (Overview, Apps, Settings), tab panels.

**What to build:**

**2a. Add ActiveTab type and TabButton component** (reuse pattern from AppDetail.tsx lines 82-113):

```tsx
type ActiveTab = "overview" | "apps" | "settings";

function TabButton({ id, label, icon, isActive, onClick }: {
  id: ActiveTab;
  label: string;
  icon: React.ReactNode;
  isActive: boolean;
  onClick: (id: ActiveTab) => void;
}) {
  return (
    <button
      role="tab"
      aria-selected={isActive}
      aria-controls={`tabpanel-${id}`}
      onClick={() => onClick(id)}
      className={[
        "flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors",
        isActive
          ? "border-orange-500 text-orange-400"
          : "border-transparent text-zinc-400 hover:border-zinc-500 hover:text-zinc-200",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  );
}
```

**2b. Restructure header** — match AppDetail pattern:
- Back link (keep existing)
- Server name h1 with icon box
- Subtitle: single line with `<StatusBadge>`, provider, connection string
- Action buttons: Provision (emerald CTA), Test Connection (secondary zinc-700), kebab menu with "Delete Server"
- Remove Edit button from header (will be in Settings tab)
- Keep provisioning progress panel below header

Add these imports: `MoreVertical`, `Settings` (if not already), `Trash2` (for delete in menu).

Add kebab menu state and outside-click handler (same pattern as AppDetail):
```tsx
const [showMenu, setShowMenu] = useState(false);
const menuRef = useRef<HTMLDivElement>(null);
const closeMenu = useCallback(() => setShowMenu(false), []);
useEffect(() => {
  function handler(e: MouseEvent) {
    if (menuRef.current && !menuRef.current.contains(e.target as Node)) closeMenu();
  }
  document.addEventListener("mousedown", handler);
  return () => document.removeEventListener("mousedown", handler);
}, [closeMenu]);
```

**2c. Add tab bar and panel structure** below provisioning progress:
```tsx
const [activeTab, setActiveTab] = useState<ActiveTab>("overview");
```

```tsx
{/* Tabs */}
<div className="rounded-xl border border-zinc-700 bg-zinc-800">
  <div role="tablist" aria-label="Server details" className="flex border-b border-zinc-700">
    <TabButton id="overview" label="Overview" icon={<Activity size={14} />} isActive={activeTab === "overview"} onClick={setActiveTab} />
    <TabButton id="apps" label="Apps" icon={<Box size={14} />} isActive={activeTab === "apps"} onClick={setActiveTab} />
    <TabButton id="settings" label="Settings" icon={<Settings size={14} />} isActive={activeTab === "settings"} onClick={setActiveTab} />
  </div>

  {/* Tab panels */}
  {activeTab === "overview" && (
    <div role="tabpanel" id="tabpanel-overview" aria-label="Overview" className="p-5">
      <p className="text-zinc-500">Overview coming in Task 3</p>
    </div>
  )}
  {activeTab === "apps" && (
    <div role="tabpanel" id="tabpanel-apps" aria-label="Apps" className="p-5">
      <p className="text-zinc-500">Apps coming in Task 4</p>
    </div>
  )}
  {activeTab === "settings" && (
    <div role="tabpanel" id="tabpanel-settings" aria-label="Settings" className="p-5">
      <p className="text-zinc-500">Settings coming in Task 5</p>
    </div>
  )}
</div>
```

Remove: the entire 3-column grid (lines 372-655) and the Edit modal (lines 657-760). These will be rebuilt as tab contents.

Remove: `showEditModal`, `editForm` state, `openEditModal`, `handleEditChange`, `handleEditSubmit` functions, and `Modal` import.

Add new imports: `useCallback` from React, `MoreVertical` from lucide-react, `useNavigate` from react-router-dom.

Handle delete in kebab: use the existing `window.confirm` pattern from old Servers.tsx, but adapted. We need `useDeleteServer` imported:

```tsx
const deleteServer = useDeleteServer();

async function handleDelete() {
  if (!window.confirm(`Delete server "${decodedName}"? This cannot be undone.`)) return;
  try {
    await deleteServer.mutateAsync(decodedName);
    toast.success(`Server "${decodedName}" deleted.`);
    void navigate("/servers");
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "Failed to delete server.");
  }
}
```

Add `useDeleteServer` to the import from `@/hooks/useApi`.

**Step 1:** Implement all changes described above (header restructure, tab bar, remove grid and modal, add kebab menu with delete).

**Step 2:** Verify TypeScript compiles:
```bash
cd frontend && npx tsc --noEmit
```

**Step 3:** Commit:
```bash
git add frontend/src/pages/ServerDetail.tsx
git commit -m "feat: restructure ServerDetail with tab layout and grouped actions"
```

---

### Task 3: ServerDetail — Overview Tab

**Files:**
- Modify: `frontend/src/pages/ServerDetail.tsx`

**Context:** Replace the placeholder Overview panel with the full content: stat cards, resource usage + quick info (2-column), 24h metrics sparklines, running containers table.

**What to build:**

Create an `OverviewTab` component (same pattern as AppDetail's OverviewTab):

```tsx
function OverviewTab({
  server,
  statusData,
  statusLoading,
  refetchStatus,
  metrics,
}: {
  server: Server;
  statusData: ServerStatusData | undefined;
  statusLoading: boolean;
  refetchStatus: () => void;
  metrics: ServerMetric[];
}) {
```

Content sections:

**Stat cards** (4 in a row):
```tsx
<div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
  {/* Status */}
  <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
    <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Status</p>
    <StatusBadge status={server.status} />
  </div>
  {/* Uptime */}
  <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
    <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Uptime</p>
    <p className="text-sm font-medium text-zinc-200">{statusData?.uptime ?? "—"}</p>
  </div>
  {/* Apps */}
  <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
    <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Apps</p>
    <p className="text-sm font-medium text-zinc-200">{server.app_count}</p>
  </div>
  {/* Containers */}
  <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
    <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Containers</p>
    <p className="text-sm font-medium text-zinc-200">{statusData?.containers?.length ?? "—"}</p>
  </div>
</div>
```

**Resource Usage + Quick Info** (2-column grid):
Left side: the existing `UsageBar` component for CPU, Memory, Disk + a Refresh button.
Right side: Quick Info card with Host, User, Port, Provider, SSH Key rows using the existing `InfoRow` component.

```tsx
<div className="grid gap-6 lg:grid-cols-2">
  {/* Resource Usage */}
  <div className="space-y-3">
    <div className="flex items-center justify-between">
      <h3 className="text-sm font-semibold text-zinc-200">Resource Usage</h3>
      <button onClick={() => void refetchStatus()} className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200" aria-label="Refresh status">
        <RefreshCw size={13} className={statusLoading ? "animate-spin" : ""} />
      </button>
    </div>
    {statusLoading ? (
      <div className="flex items-center justify-center py-8">
        <Loader2 size={24} className="animate-spin text-zinc-500" aria-label="Loading status" />
      </div>
    ) : !statusData ? (
      <p className="py-6 text-center text-sm text-zinc-500">Status unavailable — the server may be unreachable.</p>
    ) : (
      <div className="space-y-3">
        {statusData.cpu != null && <UsageBar label="CPU" used={`${statusData.cpu}%`} total="100%" percent={statusData.cpu} icon={<Cpu size={13} />} />}
        {statusData.memory && <UsageBar label="Memory" used={statusData.memory.used} total={statusData.memory.total} percent={statusData.memory.percent} icon={<Cpu size={13} />} />}
        {statusData.disk && <UsageBar label="Disk" used={statusData.disk.used} total={statusData.disk.total} percent={statusData.disk.percent} icon={<HardDrive size={13} />} />}
      </div>
    )}
  </div>

  {/* Quick Info */}
  <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
    <h3 className="mb-2 text-sm font-semibold text-zinc-200">Quick Info</h3>
    <div className="divide-y divide-zinc-700/50">
      <InfoRow label="Host" value={server.host} />
      <InfoRow label="User" value={server.user} />
      <InfoRow label="Port" value={server.port} />
      <InfoRow label="Provider" value={server.provider ?? "—"} />
      <InfoRow label="SSH Key" value={server.ssh_key_path ? <span className="font-mono text-xs">{server.ssh_key_path}</span> : "—"} />
    </div>
  </div>
</div>
```

**24h Metrics History**: Move the existing SparklineChart block into this component.

**Running Containers**: Move the existing containers section. Show as a table with Name, Image, Status columns. If no containers, show "No running containers."

Add `Server`, `ServerStatusData`, `ServerMetric` type imports from `@/api/client`.

Wire it up in the main component:
```tsx
{activeTab === "overview" && server && (
  <div role="tabpanel" id="tabpanel-overview" aria-label="Overview" className="p-5">
    <OverviewTab server={server} statusData={statusData} statusLoading={statusLoading} refetchStatus={() => void refetchStatus()} metrics={metrics} />
  </div>
)}
```

**Step 1:** Create the OverviewTab component and wire it into the tab panel.

**Step 2:** Run type check:
```bash
cd frontend && npx tsc --noEmit
```

**Step 3:** Commit:
```bash
git add frontend/src/pages/ServerDetail.tsx
git commit -m "feat: add Overview tab to ServerDetail with metrics and containers"
```

---

### Task 4: ServerDetail — Apps Tab

**Files:**
- Modify: `frontend/src/pages/ServerDetail.tsx`

**Context:** Create a dedicated Apps tab showing all apps deployed to this server with richer info than the old simple list.

**What to build:**

Create an `AppsTab` component:

```tsx
function AppsTab({ apps, serverName }: { apps: App[]; serverName: string }) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-zinc-200">Apps on {serverName}</h3>

      {apps.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-12 text-sm text-zinc-500">
          <Box size={24} className="text-zinc-600" />
          <p>No apps deployed to this server yet.</p>
          <Link to="/apps" className="text-orange-400 hover:text-orange-300">Go to Apps →</Link>
        </div>
      ) : (
        <div className="divide-y divide-zinc-700/40 rounded-lg border border-zinc-700">
          {apps.map((app) => (
            <Link
              key={app.id}
              to={`/apps/${encodeURIComponent(app.name)}`}
              className="flex items-center justify-between px-5 py-3 transition-colors hover:bg-zinc-700/30"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-orange-400">{app.name}</span>
                  <StatusBadge status={app.status} />
                </div>
                <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
                  <span className="rounded bg-zinc-700 px-1.5 py-0.5 font-mono text-[11px] text-zinc-300">{app.app_type}</span>
                  {app.branch && <span className="flex items-center gap-1"><GitBranch size={11} />{app.branch}</span>}
                  {app.image && !app.branch && <span>{app.image}</span>}
                  {app.domain && <span>{app.domain}</span>}
                </div>
              </div>
              <ChevronRight size={16} className="text-zinc-500" />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
```

Add imports: `App` type from `@/api/client`, `GitBranch`, `ChevronRight` from lucide-react.

Wire into tab panel:
```tsx
{activeTab === "apps" && (
  <div role="tabpanel" id="tabpanel-apps" aria-label="Apps" className="p-5">
    <AppsTab apps={apps} serverName={decodedName} />
  </div>
)}
```

**Step 1:** Create the AppsTab component and wire it into the tab panel.

**Step 2:** Run type check:
```bash
cd frontend && npx tsc --noEmit
```

**Step 3:** Commit:
```bash
git add frontend/src/pages/ServerDetail.tsx
git commit -m "feat: add Apps tab to ServerDetail with rich app rows"
```

---

### Task 5: ServerDetail — Settings Tab

**Files:**
- Modify: `frontend/src/pages/ServerDetail.tsx`

**Context:** Create inline Settings tab replacing the Edit modal. Has General section (Host, User, Port, SSH Key, Provider), Tags section, Save Changes with dirty detection, and Danger Zone with type-to-confirm delete.

**What to build:**

Create a `SettingsTab` component following AppDetail's SettingsTab pattern (lines 903-1241):

```tsx
function SettingsTab({ server }: { server: Server }) {
  const updateServer = useUpdateServer();
  const deleteServer = useDeleteServer();
  const navigate = useNavigate();
  const toast = useToast();
  const addServerTag = useAddServerTag();
  const removeServerTag = useRemoveServerTag();

  const PROVIDERS = ["", "hetzner", "digitalocean", "linode", "vultr", "aws", "gcp", "azure", "bare-metal", "other"];

  const [form, setForm] = useState<UpdateServerInput>({
    host: server.host,
    user: server.user,
    port: server.port,
    ssh_key_path: server.ssh_key_path ?? "",
    provider: server.provider ?? "",
  });
  const [showDanger, setShowDanger] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [newTag, setNewTag] = useState("");

  // Dirty detection
  const isDirty =
    form.host !== server.host ||
    form.user !== server.user ||
    form.port !== server.port ||
    form.ssh_key_path !== (server.ssh_key_path ?? "") ||
    form.provider !== (server.provider ?? "");

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: name === "port" ? (value === "" ? undefined : Number(value)) : value,
    }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateServer.mutateAsync({ name: server.name, input: form });
      toast.success("Server configuration updated.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update server.");
    }
  }

  async function handleDestroy() {
    if (deleteConfirm !== server.name) return;
    try {
      await deleteServer.mutateAsync(server.name);
      toast.success(`Server "${server.name}" deleted.`);
      void navigate("/servers");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete server.");
    }
  }

  async function handleAddTag(e: React.FormEvent) {
    e.preventDefault();
    const tag = newTag.trim();
    if (!tag) return;
    try {
      await addServerTag.mutateAsync({ name: server.name, tag });
      setNewTag("");
      toast.success(`Tag "${tag}" added.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add tag.");
    }
  }

  async function handleRemoveTag(tag: string) {
    try {
      await removeServerTag.mutateAsync({ name: server.name, tag });
      toast.success(`Tag "${tag}" removed.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to remove tag.");
    }
  }
```

The render includes:
1. **General section** — form fields: Host/IP, SSH User + SSH Port (grid-cols-2), SSH Key Path, Provider (select dropdown)
2. **Tags section** — tag pills with X to remove, input + Add button
3. **Save Changes button** — disabled when `!isDirty`
4. **Danger Zone** — collapsible, type-to-confirm, Delete Server button

Use the same `inputClass` pattern from AppDetail:
```tsx
const inputClass = "w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none";
```

Section headers: `<h3 className="text-sm font-semibold text-zinc-200">General</h3>` inside a `rounded-lg border border-zinc-700 bg-zinc-800/50 p-5` wrapper.

Danger Zone (collapsed by default):
```tsx
<div className="rounded-lg border border-red-500/20 bg-red-500/5">
  <button
    type="button"
    onClick={() => setShowDanger(!showDanger)}
    className="flex w-full items-center justify-between px-5 py-3 text-sm font-semibold text-red-400"
  >
    Danger Zone
    {showDanger ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
  </button>
  {showDanger && (
    <div className="border-t border-red-500/20 px-5 py-4">
      <p className="mb-3 text-sm text-zinc-400">
        Delete this server and remove all local records. This cannot be undone.
      </p>
      <label className="mb-1.5 block text-xs font-medium text-zinc-300">
        Type "{server.name}" to confirm
      </label>
      <input
        type="text"
        value={deleteConfirm}
        onChange={(e) => setDeleteConfirm(e.target.value)}
        placeholder={server.name}
        className={inputClass}
      />
      <button
        type="button"
        onClick={() => void handleDestroy()}
        disabled={deleteConfirm !== server.name || deleteServer.isPending}
        className="mt-3 flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500 disabled:opacity-50"
      >
        {deleteServer.isPending && <Loader2 size={14} className="animate-spin" />}
        Delete Server
      </button>
    </div>
  )}
</div>
```

Wire into tab panel:
```tsx
{activeTab === "settings" && server && (
  <div role="tabpanel" id="tabpanel-settings" aria-label="Settings" className="p-5">
    <SettingsTab server={server} />
  </div>
)}
```

Move tag handling and delete handling from the main component into SettingsTab. Remove `newTag`, `handleAddTag`, `handleRemoveTag`, `handleDelete` (the kebab delete) from the main component — the kebab menu delete can either stay as a shortcut using `window.confirm` or be removed since Settings has type-to-confirm. **Keep the kebab menu delete** with `window.confirm` as a quick-access shortcut. The Settings tab has the type-to-confirm version.

Remove PROVIDERS const from the main function (now inside SettingsTab).

Add `Server` type import from `@/api/client`, `ChevronDown`, `ChevronRight` from lucide-react.

**Step 1:** Create the SettingsTab component and wire it into the tab panel. Clean up moved state/handlers from main component.

**Step 2:** Run type check:
```bash
cd frontend && npx tsc --noEmit
```

**Step 3:** Verify build:
```bash
cd frontend && npm run build
```

**Step 4:** Commit:
```bash
git add frontend/src/pages/ServerDetail.tsx
git commit -m "feat: add Settings tab to ServerDetail with inline editing and danger zone"
```

---

### Task 6: Update E2E Tests — servers.spec.ts

**Files:**
- Modify: `frontend/e2e/servers.spec.ts`

**Context:** The Servers list page changed from table to card grid. Tests need to verify the card-based layout.

**Changes needed:**

- "lists servers from API" — should still pass (checks for server names visible)
- "shows server connection details" — verify connection strings still visible in cards
- "Add Server modal opens and closes" — unchanged (modal is the same)
- "Add Server form submits successfully" — unchanged
- "server name links to detail page" — still a link, should pass
- "delete server shows confirmation" — the delete button may have changed selectors. Cards should still have a delete action. If the delete is moved to a kebab or removed from list page cards, update accordingly.

**Decision on card actions:** The design shows cards without explicit Provision/Delete buttons on each card (unlike the table which had action columns). The cards are primarily navigation — clicking the name goes to detail. However, for the delete test to pass, we need some delete mechanism on the list page.

**Options:**
1. Keep a small delete icon button on each card (for quick access)
2. Remove delete from the list page entirely (delete only from detail Settings)

**Go with option 1** — keep a small trash icon in the card top-right corner for quick delete. This is minimal and keeps the existing test working with minor selector changes.

Rewrite tests to match new card layout. Most should still pass since cards still show server names, connection strings, etc.

**Step 1:** Run existing tests to see which pass/fail:
```bash
cd frontend && npx playwright test servers.spec.ts --reporter=list
```

**Step 2:** Fix any failing tests to match the new card UI.

**Step 3:** Commit:
```bash
git add frontend/e2e/servers.spec.ts
git commit -m "test: update servers.spec.ts for card grid layout"
```

---

### Task 7: Update E2E Tests — server-detail.spec.ts

**Files:**
- Modify: `frontend/e2e/server-detail.spec.ts`
- Possibly modify: `frontend/e2e/fixtures.ts` (add tags mock if needed)

**Context:** Server Detail changed from flat layout + Edit modal to tab layout (Overview, Apps, Settings). Tests need to reflect the new structure.

**Test updates needed:**

**Header tests** — mostly unchanged:
- "displays server name heading" — still works
- "shows connection string in subtitle" — still works
- "shows provider in subtitle" — still works
- "shows status badge" — still works
- "Back to Servers link" — still works

**Server Info card → Overview tab Quick Info:**
- "Server Info card shows host and user" — now in Overview tab Quick Info section. Overview is default, so should still work. Update selector if needed.

**Action buttons:**
- "has Edit, Test Connection, and Provision buttons" → change to: "has Provision, Test Connection buttons and kebab menu"
- No more "Edit" button in header. Provision is now emerald CTA. Add check for kebab "More actions" button.
- "Test Connection shows success toast" — still works.

**Edit modal tests → Settings tab tests:**
- Replace all 5 Edit modal tests with Settings tab equivalents:
  - "Settings tab has form fields" — navigate to Settings tab, check all fields visible
  - "Settings tab pre-populates values" — check field values
  - "Settings Save disabled when no changes" — check button disabled
  - "Settings Save enables on change and shows toast" — change a field, save, verify toast
  - "Settings Danger Zone collapsed by default" — check Danger Zone visible, Delete not visible
  - "Settings Danger Zone expands and shows Delete button" — click, verify

**Resource usage tests** — now in Overview (default tab):
- "shows Resource Usage section" → check for "Resource Usage" text
- "shows memory usage bar" — still works
- "shows disk usage bar" — still works
- "shows uptime" — now in stat cards, check for uptime text
- "Refresh status button" — still works

**Containers tests** — in Overview:
- "shows running containers section" — may need heading text update
- "lists containers with names and images" — still works

**Apps tests** — now in Apps tab:
- "shows Apps on this Server section" → click Apps tab first
- "lists apps deployed to this server" → click Apps tab first
- "app links navigate to app detail" → click Apps tab first

**Provisioning tests** — in header area (unchanged behavior):
- All 5 provisioning tests should still pass

**Add tags mock route if not present.** Check if `**/api/servers/*/tags` is mocked. Looking at fixtures.ts... it's not explicitly mocked. The tag operations in the old UI used `useAddServerTag`/`useRemoveServerTag` hooks which call `/api/servers/{name}/tags`. Add these routes to `mockApi()`:

```ts
// Server tags
await page.route(/\/api\/servers\/[^/]+\/tags(\/.*)?$/, (route) => {
  if (route.request().method() === "GET") {
    return route.fulfill({ json: ["production", "eu-west"] });
  }
  if (route.request().method() === "POST") {
    return route.fulfill({ json: { message: "Tag added" } });
  }
  if (route.request().method() === "DELETE") {
    return route.fulfill({ json: { message: "Tag removed" } });
  }
  return route.continue();
});
```

Also add `tags: ["production", "eu-west"]` to `MOCK_SERVERS[0]` in fixtures.ts.

**Step 1:** Update fixtures.ts: add tags to MOCK_SERVERS[0] and add tags mock route.

**Step 2:** Rewrite server-detail.spec.ts with all the changes above.

**Step 3:** Run tests:
```bash
cd frontend && npx playwright test server-detail.spec.ts --reporter=list
```

**Step 4:** Fix any failures.

**Step 5:** Run full E2E suite:
```bash
cd frontend && npx playwright test --reporter=list
```

**Step 6:** Commit:
```bash
git add frontend/e2e/server-detail.spec.ts frontend/e2e/fixtures.ts
git commit -m "test: update server-detail E2E tests for tab layout redesign"
```

---

### Task 8: Final Verification

**Step 1:** Run TypeScript type check:
```bash
cd frontend && npx tsc --noEmit
```

**Step 2:** Run production build:
```bash
cd frontend && npm run build
```

**Step 3:** Run full E2E suite:
```bash
cd frontend && npx playwright test --reporter=list
```

**Step 4:** Fix any issues found.

**Step 5:** Commit any fixes, then verify clean state.
