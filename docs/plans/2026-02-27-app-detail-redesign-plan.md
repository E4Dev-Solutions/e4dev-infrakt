# App Detail Page Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the App Detail page with an Overview tab, Settings tab, improved header, and safer action button hierarchy.

**Architecture:** Refactor the single 1300-line `AppDetail.tsx` into the main page component plus 5 tab components. New Overview and Settings tabs replace the Health tab and Edit modal respectively. All existing API hooks are reused — no backend changes needed.

**Tech Stack:** React 19, TanStack Query, Tailwind CSS 4, Lucide React icons, Playwright E2E tests

**Design doc:** `docs/plans/2026-02-27-app-detail-redesign.md`

---

## Key Files Reference

- Page: `frontend/src/pages/AppDetail.tsx` (1300 lines — will be refactored)
- Types: `frontend/src/api/client.ts` (App, UpdateAppInput, AppHealth, Deployment)
- Hooks: `frontend/src/hooks/useApi.ts` (useApps, useAppHealth, useAppDeployments, useUpdateApp, etc.)
- Components: `frontend/src/components/StatusBadge.tsx`, `Modal.tsx`, `DeploymentLogStream.tsx`
- E2E tests: `frontend/e2e/app-detail.spec.ts`
- E2E fixtures: `frontend/e2e/fixtures.ts`
- Theme: zinc-950 base, orange-500/600 accent, Outfit + JetBrains Mono fonts

---

### Task 1: Restructure Header + Action Buttons

**Files:**
- Modify: `frontend/src/pages/AppDetail.tsx`

**Step 1: Refactor the header subtitle**

Replace the single-line metadata chips (lines 960-999) with a structured 3-line subtitle:

```tsx
{app && (
  <div className="mt-1.5 space-y-1">
    {/* Line 1: Status + Server */}
    <div className="flex items-center gap-3">
      <StatusBadge status={app.status} />
      <span className="flex items-center gap-1 text-sm text-zinc-400">
        <Server size={12} aria-hidden="true" />
        {app.server_name}
      </span>
    </div>
    {/* Line 2: Domain + Port */}
    <div className="flex items-center gap-2 text-sm text-zinc-400">
      {app.domains && Object.keys(app.domains).length > 1 ? (
        Object.entries(app.domains).map(([svc, d]) => (
          <a key={svc} href={`https://${d}`} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-zinc-300 hover:text-orange-400 transition-colors">
            <Globe size={12} aria-hidden="true" />
            <span className="text-zinc-500">{svc}:</span> {d}
          </a>
        ))
      ) : app.domain ? (
        <a href={`https://${app.domain}`} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1 text-zinc-300 hover:text-orange-400 transition-colors">
          <Globe size={12} aria-hidden="true" />
          {app.domain}
        </a>
      ) : null}
      {app.port && <span className="text-zinc-500">:{app.port}</span>}
    </div>
    {/* Line 3: App type + Branch */}
    <div className="flex items-center gap-3 text-xs text-zinc-500">
      {app.app_type && (
        <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px]">
          {app.app_type}
        </span>
      )}
      {app.branch && (
        <span className="flex items-center gap-1">
          <GitBranch size={11} aria-hidden="true" /> {app.branch}
        </span>
      )}
    </div>
  </div>
)}
```

Remove the `{app && <StatusBadge status={app.status} />}` that was next to the action buttons — status now lives in the subtitle.

**Step 2: Refactor action buttons into grouped layout**

Replace the 5 equal-weight buttons with: Deploy (green CTA), Restart+Stop (secondary), kebab dropdown with Destroy.

```tsx
import { MoreVertical } from "lucide-react";

// Add state for dropdown
const [showMenu, setShowMenu] = useState(false);
const menuRef = useRef<HTMLDivElement>(null);

// Close menu on outside click
useEffect(() => {
  function handleClick(e: MouseEvent) {
    if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
      setShowMenu(false);
    }
  }
  document.addEventListener("mousedown", handleClick);
  return () => document.removeEventListener("mousedown", handleClick);
}, []);
```

Action buttons JSX:

```tsx
<div className="flex flex-wrap items-center gap-2">
  {/* Primary CTA */}
  <button onClick={handleDeploy} disabled={!!actionPending}
    className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50">
    {actionPending === "deploy" ? (
      <Loader2 size={14} className="animate-spin" aria-hidden="true" />
    ) : (
      <Play size={14} aria-hidden="true" />
    )}
    Deploy
  </button>
  {/* Secondary actions */}
  <button onClick={handleRestart} disabled={!!actionPending}
    className="flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-600 disabled:opacity-50">
    {actionPending === "restart" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
    Restart
  </button>
  <button onClick={handleStop} disabled={!!actionPending}
    className="flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-600 disabled:opacity-50">
    {actionPending === "stop" ? <Loader2 size={14} className="animate-spin" /> : <Square size={14} />}
    Stop
  </button>
  {/* Kebab menu with Destroy */}
  <div className="relative" ref={menuRef}>
    <button onClick={() => setShowMenu(!showMenu)}
      className="rounded-lg border border-zinc-600 bg-zinc-700 p-2 text-zinc-400 transition-colors hover:bg-zinc-600 hover:text-zinc-200"
      aria-label="More actions">
      <MoreVertical size={16} />
    </button>
    {showMenu && (
      <div className="absolute right-0 top-full z-10 mt-1 w-44 rounded-lg border border-zinc-600 bg-zinc-800 py-1 shadow-xl">
        <button onClick={() => { setShowMenu(false); handleDestroy(); }}
          disabled={!!actionPending}
          className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-zinc-700 disabled:opacity-50">
          <Trash2 size={14} /> Destroy App
        </button>
      </div>
    )}
  </div>
</div>
```

Remove the Edit button from the header (Edit modal is being replaced by Settings tab).

**Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/pages/AppDetail.tsx
git commit -m "refactor: redesign AppDetail header and group action buttons"
```

---

### Task 2: Add Overview Tab

**Files:**
- Modify: `frontend/src/pages/AppDetail.tsx`

**Step 1: Change tab type and default**

Replace:
```tsx
type ActiveTab = "logs" | "env" | "deployments" | "health";
```
With:
```tsx
type ActiveTab = "overview" | "logs" | "env" | "deployments" | "settings";
```

Change default: `const [activeTab, setActiveTab] = useState<ActiveTab>("overview");`

**Step 2: Create the OverviewTab component**

Add before the main `AppDetail` component. Uses existing hooks: `useAppHealth`, `useAppDeployments`.

```tsx
function OverviewTab({ app }: { app: App }) {
  const { data: healthData, refetch: refetchHealth, isFetching: healthFetching } = useAppHealth(app.name, { enabled: false });
  const { data: deployments = [] } = useAppDeployments(app.name);
  const lastDeploy = deployments[0];
  const recentDeploys = deployments.slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Status */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Status</p>
          <StatusBadge status={app.status} />
        </div>
        {/* Last Deploy */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Last Deploy</p>
          {lastDeploy ? (
            <div>
              <p className="text-sm font-medium text-zinc-200">{formatRelativeTime(lastDeploy.started_at)}</p>
              {lastDeploy.commit_hash && (
                <p className="mt-0.5 font-mono text-xs text-zinc-400">{lastDeploy.commit_hash.slice(0, 7)}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-zinc-500">No deploys yet</p>
          )}
        </div>
        {/* App Type */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">App Type</p>
          <p className="rounded bg-zinc-700/50 px-2 py-0.5 text-sm font-mono text-zinc-300 inline-block">{app.app_type || "compose"}</p>
        </div>
      </div>

      {/* Container Metrics */}
      <div className="rounded-lg border border-zinc-700 bg-zinc-800/50">
        <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
          <h3 className="text-sm font-semibold text-zinc-200">Container Metrics</h3>
          <button onClick={() => void refetchHealth()} disabled={healthFetching}
            className="flex items-center gap-1.5 rounded-md border border-zinc-600 bg-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:bg-zinc-600 disabled:opacity-50">
            <RefreshCw size={12} className={healthFetching ? "animate-spin" : ""} />
            {healthFetching ? "Loading..." : "Refresh"}
          </button>
        </div>
        <div className="p-4">
          {!healthData ? (
            <p className="py-4 text-center text-sm text-zinc-500">Click Refresh to load container metrics from the server.</p>
          ) : healthData.containers.length === 0 ? (
            <p className="py-4 text-center text-sm text-zinc-500">No containers found.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  <th className="pb-2">Container</th>
                  <th className="pb-2">State</th>
                  <th className="pb-2">Status</th>
                  <th className="pb-2">Image</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-700/40">
                {healthData.containers.map((c) => (
                  <tr key={c.name}>
                    <td className="py-2 font-mono text-xs text-zinc-200">{c.name}</td>
                    <td className="py-2"><StatusBadge status={c.state} /></td>
                    <td className="py-2 text-xs text-zinc-400">{c.status}</td>
                    <td className="py-2 font-mono text-xs text-zinc-500">{c.image || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Recent Deploys */}
      {recentDeploys.length > 0 && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50">
          <div className="border-b border-zinc-700 px-4 py-3">
            <h3 className="text-sm font-semibold text-zinc-200">Recent Deploys</h3>
          </div>
          <div className="divide-y divide-zinc-700/40">
            {recentDeploys.map((dep) => (
              <div key={dep.id} className="flex items-center gap-3 px-4 py-2.5">
                <span className={`h-2 w-2 rounded-full ${dep.status === "success" ? "bg-emerald-500" : dep.status === "failed" ? "bg-red-500" : "bg-amber-500"}`} />
                <span className="text-xs text-zinc-400">#{dep.id}</span>
                <StatusBadge status={dep.status} />
                {dep.commit_hash && <span className="font-mono text-xs text-zinc-500">{dep.commit_hash.slice(0, 7)}</span>}
                <span className="ml-auto text-xs text-zinc-500">{formatRelativeTime(dep.started_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Info */}
      <div className="rounded-lg border border-zinc-700 bg-zinc-800/50">
        <div className="border-b border-zinc-700 px-4 py-3">
          <h3 className="text-sm font-semibold text-zinc-200">Quick Info</h3>
        </div>
        <div className="divide-y divide-zinc-700/30 px-4">
          <div className="flex items-center justify-between py-2.5 text-sm">
            <span className="text-zinc-400">Server</span>
            <span className="font-medium text-zinc-200">{app.server_name}</span>
          </div>
          {app.domain && (
            <div className="flex items-center justify-between py-2.5 text-sm">
              <span className="text-zinc-400">Domain</span>
              <a href={`https://${app.domain}`} target="_blank" rel="noopener noreferrer"
                className="font-medium text-zinc-200 hover:text-orange-400 transition-colors">
                {app.domain} <span className="text-zinc-500">↗</span>
              </a>
            </div>
          )}
          <div className="flex items-center justify-between py-2.5 text-sm">
            <span className="text-zinc-400">Port</span>
            <span className="font-medium text-zinc-200">{app.port}</span>
          </div>
          {app.branch && (
            <div className="flex items-center justify-between py-2.5 text-sm">
              <span className="text-zinc-400">Branch</span>
              <span className="font-medium text-zinc-200">{app.branch}</span>
            </div>
          )}
          <div className="flex items-center justify-between py-2.5 text-sm">
            <span className="text-zinc-400">Replicas</span>
            <span className="font-medium text-zinc-200">{app.replicas ?? 1}</span>
          </div>
          <div className="flex items-center justify-between py-2.5 text-sm">
            <span className="text-zinc-400">Deploy Strategy</span>
            <span className="font-medium text-zinc-200">{app.deploy_strategy ?? "restart"}</span>
          </div>
        </div>
      </div>

      {/* HTTP Health Check (conditional) */}
      {healthData?.http_health && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <h3 className="mb-3 text-sm font-semibold text-zinc-200">HTTP Health Check</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <p className="text-xs text-zinc-500">Status</p>
              <StatusBadge status={healthData.http_health.healthy ? "healthy" : "unhealthy"} />
            </div>
            {healthData.http_health.status_code != null && (
              <div>
                <p className="text-xs text-zinc-500">HTTP Code</p>
                <p className="font-mono text-sm text-zinc-200">{healthData.http_health.status_code}</p>
              </div>
            )}
            {healthData.http_health.response_time_ms != null && (
              <div>
                <p className="text-xs text-zinc-500">Response Time</p>
                <p className="font-mono text-sm text-zinc-200">{healthData.http_health.response_time_ms.toFixed(0)}ms</p>
              </div>
            )}
            {healthData.http_health.error && (
              <div className="col-span-full">
                <p className="text-xs text-zinc-500">Error</p>
                <p className="text-sm text-red-400">{healthData.http_health.error}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 3: Add `formatRelativeTime` helper**

Add near the existing `formatDate` function:

```tsx
function formatRelativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60_000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  } catch {
    return iso;
  }
}
```

**Step 4: Wire up Overview tab in the tab list and panels**

Add the Overview TabButton as first tab. Replace the Health tab. Wire up the panel:

```tsx
<TabButton id="overview" label="Overview"
  icon={<Activity size={14} aria-hidden="true" />}
  isActive={activeTab === "overview"} onClick={setActiveTab} />
```

Panel:
```tsx
<div id="tabpanel-overview" role="tabpanel" aria-label="Overview" hidden={activeTab !== "overview"}>
  {activeTab === "overview" && app && <OverviewTab app={app} />}
</div>
```

Import `App` type: `import type { App, UpdateAppInput } from "@/api/client";`

**Step 5: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 6: Commit**

```bash
git add frontend/src/pages/AppDetail.tsx
git commit -m "feat: add Overview tab as default landing page for AppDetail"
```

---

### Task 3: Add Settings Tab (Replace Edit Modal)

**Files:**
- Modify: `frontend/src/pages/AppDetail.tsx`

**Step 1: Create the SettingsTab component**

Add the `SettingsTab` component. It receives the app data and update mutation:

```tsx
function SettingsTab({ app }: { app: App }) {
  const updateApp = useUpdateApp();
  const destroyApp = useDestroyApp();
  const navigate = useNavigate();
  const toast = useToast();
  const [dangerOpen, setDangerOpen] = useState(false);

  const [form, setForm] = useState<UpdateAppInput>({
    domain: app.domain ?? "",
    port: app.port ?? 3000,
    git_repo: app.git_repo ?? "",
    branch: app.branch ?? "main",
    image: app.image ?? "",
    cpu_limit: app.cpu_limit ?? "",
    memory_limit: app.memory_limit ?? "",
    health_check_url: app.health_check_url ?? "",
    health_check_interval: app.health_check_interval,
    replicas: app.replicas ?? 1,
    deploy_strategy: app.deploy_strategy ?? "restart",
  });

  const isTemplate = app.app_type?.startsWith("template:");

  // Dirty detection
  const isDirty =
    form.domain !== (app.domain ?? "") ||
    form.port !== (app.port ?? 3000) ||
    form.git_repo !== (app.git_repo ?? "") ||
    form.branch !== (app.branch ?? "main") ||
    form.image !== (app.image ?? "") ||
    form.cpu_limit !== (app.cpu_limit ?? "") ||
    form.memory_limit !== (app.memory_limit ?? "") ||
    form.health_check_url !== (app.health_check_url ?? "") ||
    form.health_check_interval !== app.health_check_interval ||
    form.replicas !== (app.replicas ?? 1) ||
    form.deploy_strategy !== (app.deploy_strategy ?? "restart");

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name, value } = e.target;
    const numericFields = ["port", "health_check_interval", "replicas"];
    setForm((prev) => ({
      ...prev,
      [name]: numericFields.includes(name)
        ? value === "" ? undefined : Number(value)
        : value,
    }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateApp.mutateAsync({ name: app.name, input: form });
      toast.success("Settings saved.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save.");
    }
  }

  async function handleDestroy() {
    if (!window.confirm(`Destroy app "${app.name}"? This cannot be undone.`)) return;
    try {
      await destroyApp.mutateAsync(app.name);
      toast.success(`App "${app.name}" destroyed.`);
      void navigate("/apps");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Destroy failed.");
    }
  }

  const inputClass = "w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none";
  const labelClass = "mb-1.5 block text-xs font-medium text-zinc-300";
  const sectionClass = "rounded-lg border border-zinc-700 bg-zinc-800/50 p-4 space-y-4";

  return (
    <form onSubmit={handleSave} className="space-y-6">
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Save button (sticky top) */}
      <div className="flex justify-end">
        <button type="submit" disabled={!isDirty || updateApp.isPending}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40 ${
            isDirty ? "bg-orange-600 text-white hover:bg-orange-500" : "bg-zinc-700 text-zinc-400"
          }`}>
          {updateApp.isPending && <Loader2 size={14} className="animate-spin" />}
          Save Changes
        </button>
      </div>

      {/* General */}
      <div className={sectionClass}>
        <h3 className="text-sm font-semibold text-zinc-200">General</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="settings-domain" className={labelClass}>Domain</label>
            <input id="settings-domain" name="domain" type="text" value={form.domain ?? ""}
              onChange={handleChange} placeholder="app.example.com" className={inputClass} />
          </div>
          <div>
            <label htmlFor="settings-port" className={labelClass}>Port</label>
            <input id="settings-port" name="port" type="number" min={1} max={65535}
              value={form.port ?? ""} onChange={handleChange} className={inputClass} />
          </div>
        </div>
      </div>

      {/* Source (hidden for template apps) */}
      {!isTemplate && (
        <div className={sectionClass}>
          <h3 className="text-sm font-semibold text-zinc-200">Source</h3>
          <div>
            <label htmlFor="settings-git-repo" className={labelClass}>Git Repository</label>
            <input id="settings-git-repo" name="git_repo" type="text" value={form.git_repo ?? ""}
              onChange={handleChange} placeholder="https://github.com/user/repo.git" className={inputClass} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="settings-branch" className={labelClass}>Branch</label>
              <input id="settings-branch" name="branch" type="text" value={form.branch ?? ""}
                onChange={handleChange} placeholder="main" className={inputClass} />
            </div>
            <div>
              <label htmlFor="settings-image" className={labelClass}>Docker Image</label>
              <input id="settings-image" name="image" type="text" value={form.image ?? ""}
                onChange={handleChange} placeholder="nginx:latest" className={inputClass} />
            </div>
          </div>
        </div>
      )}

      {/* Resources */}
      <div className={sectionClass}>
        <h3 className="text-sm font-semibold text-zinc-200">Resources</h3>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <label htmlFor="settings-cpu" className={labelClass}>CPU Limit</label>
            <input id="settings-cpu" name="cpu_limit" type="text" value={form.cpu_limit ?? ""}
              onChange={handleChange} placeholder="0.5" className={inputClass} />
          </div>
          <div>
            <label htmlFor="settings-memory" className={labelClass}>Memory Limit</label>
            <input id="settings-memory" name="memory_limit" type="text" value={form.memory_limit ?? ""}
              onChange={handleChange} placeholder="512M" className={inputClass} />
          </div>
          <div>
            <label htmlFor="settings-replicas" className={labelClass}>Replicas</label>
            <input id="settings-replicas" name="replicas" type="number" min={1} max={10}
              value={form.replicas ?? 1} onChange={handleChange} className={inputClass} />
          </div>
          <div>
            <label htmlFor="settings-strategy" className={labelClass}>Deploy Strategy</label>
            <select id="settings-strategy" name="deploy_strategy" value={form.deploy_strategy ?? "restart"}
              onChange={handleChange} className={inputClass}>
              <option value="restart">restart</option>
              <option value="rolling">rolling</option>
            </select>
          </div>
        </div>
      </div>

      {/* Health Check */}
      <div className={sectionClass}>
        <h3 className="text-sm font-semibold text-zinc-200">Health Check</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="settings-hc-url" className={labelClass}>URL</label>
            <input id="settings-hc-url" name="health_check_url" type="text" value={form.health_check_url ?? ""}
              onChange={handleChange} placeholder="https://app.example.com/health" className={inputClass} />
          </div>
          <div>
            <label htmlFor="settings-hc-interval" className={labelClass}>Interval (seconds)</label>
            <input id="settings-hc-interval" name="health_check_interval" type="number" min={5}
              value={form.health_check_interval ?? ""} onChange={handleChange} placeholder="30" className={inputClass} />
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="rounded-lg border border-red-500/20 bg-red-500/5">
        <button type="button" onClick={() => setDangerOpen(!dangerOpen)}
          className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold text-red-400">
          Danger Zone
          {dangerOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        {dangerOpen && (
          <div className="border-t border-red-500/20 px-4 py-4">
            <p className="mb-3 text-sm text-zinc-400">
              This will stop all containers, remove volumes, and delete all data for <strong className="text-zinc-200">{app.name}</strong>. This cannot be undone.
            </p>
            <button type="button" onClick={handleDestroy}
              className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/20">
              <Trash2 size={14} /> Destroy App
            </button>
          </div>
        )}
      </div>
    </form>
  );
}
```

**Step 2: Wire up Settings tab in tab list and panels**

Add Settings tab button (replace Health):

```tsx
<TabButton id="settings" label="Settings"
  icon={<Settings size={14} aria-hidden="true" />}
  isActive={activeTab === "settings"} onClick={setActiveTab} />
```

Panel:
```tsx
<div id="tabpanel-settings" role="tabpanel" aria-label="Settings" hidden={activeTab !== "settings"}>
  {activeTab === "settings" && app && <SettingsTab app={app} />}
</div>
```

**Step 3: Remove Edit modal and related state**

Delete:
- `showEditModal` state
- `editForm` state
- `openEditModal` function
- `handleEditChange` function
- `handleEditSubmit` function
- The entire `{showEditModal && <Modal>...</Modal>}` JSX block
- The Edit button from the header action buttons

**Step 4: Remove Destroy from header action buttons**

Delete the Destroy button from the action buttons area (it's now in Settings > Danger Zone). Also remove `handleDestroy` from the main component — it's now in SettingsTab.

**Step 5: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 6: Commit**

```bash
git add frontend/src/pages/AppDetail.tsx
git commit -m "feat: add Settings tab replacing Edit modal, move Destroy to Danger Zone"
```

---

### Task 4: Fix Logs Tab Height

**Files:**
- Modify: `frontend/src/pages/AppDetail.tsx`

**Step 1: Make log viewer height responsive**

In the `LogsTab` component, replace the fixed height:

```tsx
// Before:
className="h-[480px] overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-950 p-4"
// After:
className="h-[calc(100vh-340px)] min-h-[300px] overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-950 p-4"
```

**Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/pages/AppDetail.tsx
git commit -m "fix: make log viewer height responsive instead of fixed 480px"
```

---

### Task 5: Update E2E Tests

**Files:**
- Modify: `frontend/e2e/app-detail.spec.ts`
- Modify: `frontend/e2e/fixtures.ts` (add mock health data if needed)

**Step 1: Update tests for new tab structure**

The E2E tests need updates for:
- Overview is now the default tab (not Logs)
- Health tab removed → container info on Overview
- Edit modal removed → Settings tab
- Destroy button hidden in kebab menu
- Edit button removed

Replace the full test file:

```typescript
import { test, expect } from "@playwright/test";
import {
  login,
  mockApi,
  MOCK_APPS,
  MOCK_ENV_VARS,
  MOCK_DEPLOYMENTS,
} from "./fixtures";

const APP = MOCK_APPS[0]; // web-api

test.describe("App Detail", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${APP.name}`);
  });

  // ─── Header & info ──────────────────────────────────────────────────────────

  test("displays app name heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: APP.name }),
    ).toBeVisible();
  });

  test("shows server name and domain in subtitle", async ({ page }) => {
    await expect(page.getByText(APP.server_name)).toBeVisible();
    await expect(page.getByText(APP.domain!)).toBeVisible();
  });

  test("shows app type and branch", async ({ page }) => {
    await expect(page.getByText(APP.app_type)).toBeVisible();
    await expect(page.getByText(APP.branch!)).toBeVisible();
  });

  test("shows status badge", async ({ page }) => {
    await expect(page.getByText("running").first()).toBeVisible();
  });

  // ─── Action buttons ─────────────────────────────────────────────────────────

  test("has Deploy, Restart, Stop buttons and kebab menu", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Deploy" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Restart" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
    await expect(page.getByRole("button", { name: "More actions" })).toBeVisible();
  });

  test("Restart button shows toast", async ({ page }) => {
    await page.getByRole("button", { name: "Restart" }).click();
    await expect(page.getByText(/restarted/i)).toBeVisible();
  });

  test("Stop button shows toast", async ({ page }) => {
    await page.getByRole("button", { name: "Stop" }).click();
    await expect(page.getByText(/stopped/i)).toBeVisible();
  });

  test("Destroy is in kebab menu and shows confirmation", async ({ page }) => {
    let dialogMessage = "";
    page.on("dialog", (dialog) => {
      dialogMessage = dialog.message();
      void dialog.accept();
    });
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByText("Destroy App").click();
    expect(dialogMessage).toContain(APP.name);
  });

  // ─── Overview tab (default) ────────────────────────────────────────────────

  test("Overview tab is active by default", async ({ page }) => {
    await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("Overview shows stat cards", async ({ page }) => {
    await expect(page.getByText("Status")).toBeVisible();
    await expect(page.getByText("Last Deploy")).toBeVisible();
    await expect(page.getByText("App Type")).toBeVisible();
  });

  test("Overview shows Quick Info section", async ({ page }) => {
    await expect(page.getByText("Quick Info")).toBeVisible();
    await expect(page.getByText(APP.server_name)).toBeVisible();
  });

  test("Overview shows container metrics after refresh", async ({ page }) => {
    await page.getByRole("button", { name: "Refresh" }).click();
    await expect(page.getByText("infrakt-web-api")).toBeVisible();
  });

  // ─── Logs tab ───────────────────────────────────────────────────────────────

  test("Logs tab shows log content", async ({ page }) => {
    await page.getByRole("tab", { name: "Logs" }).click();
    await expect(page.getByText("Container started")).toBeVisible();
  });

  test("Live toggle button is visible on Logs tab", async ({ page }) => {
    await page.getByRole("tab", { name: "Logs" }).click();
    await expect(
      page.getByRole("button", { name: /live/i }),
    ).toBeVisible();
  });

  // ─── Environment tab ───────────────────────────────────────────────────────

  test("Environment tab shows env variables", async ({ page }) => {
    await page.getByRole("tab", { name: "Environment" }).click();
    for (const v of MOCK_ENV_VARS) {
      await expect(page.getByText(v.key)).toBeVisible();
    }
  });

  test("Environment tab has add form", async ({ page }) => {
    await page.getByRole("tab", { name: "Environment" }).click();
    await expect(page.getByPlaceholder("DATABASE_URL")).toBeVisible();
    await expect(page.getByPlaceholder("postgres://...")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add", exact: true })).toBeVisible();
  });

  test("Environment tab has delete buttons for each variable", async ({ page }) => {
    await page.getByRole("tab", { name: "Environment" }).click();
    const deleteButtons = page.getByLabel("Delete", { exact: false });
    await expect(deleteButtons).toHaveCount(MOCK_ENV_VARS.length);
  });

  // ─── Deployments tab ───────────────────────────────────────────────────────

  test("Deployments tab shows deployment history", async ({ page }) => {
    await page.getByRole("tab", { name: "Deployments" }).click();
    for (const dep of MOCK_DEPLOYMENTS) {
      await expect(page.getByText(`#${dep.id}`)).toBeVisible();
    }
  });

  test("Deployments tab shows commit refs", async ({ page }) => {
    await page.getByRole("tab", { name: "Deployments" }).click();
    const shortHash = MOCK_DEPLOYMENTS[0].commit_hash.slice(0, 8);
    await expect(page.getByText(shortHash)).toBeVisible();
  });

  test("Deployments tab shows status badges", async ({ page }) => {
    await page.getByRole("tab", { name: "Deployments" }).click();
    await expect(page.getByText("success").first()).toBeVisible();
    await expect(page.getByText("failed")).toBeVisible();
  });

  test("Rollback button visible on non-latest successful deployments", async ({ page }) => {
    await page.getByRole("tab", { name: "Deployments" }).click();
    await expect(page.getByLabel("Rollback")).toBeVisible();
  });

  // ─── Settings tab ──────────────────────────────────────────────────────────

  test("Settings tab shows form sections", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByText("General")).toBeVisible();
    await expect(page.getByText("Resources")).toBeVisible();
    await expect(page.getByText("Health Check")).toBeVisible();
  });

  test("Settings pre-populates with app data", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByLabel("Domain")).toHaveValue(APP.domain!);
    await expect(page.getByLabel("Port")).toHaveValue(String(APP.port));
  });

  test("Settings Save button is disabled when no changes", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeDisabled();
  });

  test("Settings Save button enables on change and shows toast", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await page.getByLabel("Domain").fill("new.example.com");
    const saveBtn = page.getByRole("button", { name: "Save Changes" });
    await expect(saveBtn).toBeEnabled();
    await saveBtn.click();
    await expect(page.getByText("Settings saved")).toBeVisible();
  });

  test("Settings Danger Zone is collapsed by default", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByText("Danger Zone")).toBeVisible();
    await expect(page.getByRole("button", { name: "Destroy App" })).not.toBeVisible();
  });

  test("Settings Danger Zone expands and shows Destroy button", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await page.getByText("Danger Zone").click();
    await expect(page.getByRole("button", { name: "Destroy App" })).toBeVisible();
  });
});
```

**Step 2: Run E2E tests**

Run: `cd frontend && npx playwright test e2e/app-detail.spec.ts`
Expected: All tests pass

**Step 3: Commit**

```bash
git add frontend/e2e/app-detail.spec.ts
git commit -m "test: update E2E tests for AppDetail redesign"
```

---

### Task 6: Final Cleanup

**Files:**
- Modify: `frontend/src/pages/AppDetail.tsx`

**Step 1: Remove dead code**

- Remove the old `HealthTab` component entirely
- Remove unused imports (Activity, MoreVertical may need adjusting)
- Clean up any remaining references to `showEditModal`, `editForm`, the old `health` tab

**Step 2: Run type check + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: No errors

**Step 3: Run full E2E suite**

Run: `cd frontend && npx playwright test`
Expected: All tests pass (including other spec files that aren't affected)

**Step 4: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add frontend/
git commit -m "chore: clean up dead code from AppDetail redesign"
```
