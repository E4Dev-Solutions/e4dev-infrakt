import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Trash2,
  Play,
  Square,
  RefreshCw,
  Box,
  ChevronRight,
  Loader2,
  Globe,
  GitBranch,
  Github,
  Search,
  Lock,
} from "lucide-react";
import {
  useApps,
  useServers,
  useCreateApp,
  useDeployApp,
  useStopApp,
  useRestartApp,
  useDestroyApp,
  useGitHubStatus,
  useGitHubRepos,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";
import Modal from "@/components/Modal";
import EmptyState from "@/components/EmptyState";
import type { CreateAppInput } from "@/api/client";

const defaultForm: CreateAppInput = {
  name: "",
  server_name: "",
  domain: "",
  port: undefined,
  git_repo: "",
  branch: "main",
  image: "",
  cpu_limit: "",
  memory_limit: "",
};

export default function Apps() {
  const { data: apps = [], isLoading, isError, error } = useApps();
  const { data: servers = [] } = useServers();

  const createApp = useCreateApp();
  const deployApp = useDeployApp();
  const stopApp = useStopApp();
  const restartApp = useRestartApp();
  const destroyApp = useDestroyApp();
  const toast = useToast();

  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<CreateAppInput>(defaultForm);
  const [actionPending, setActionPending] = useState<string | null>(null);

  // GitHub repo picker
  const { data: githubStatus } = useGitHubStatus();
  const githubConnected = githubStatus?.connected === true;
  const { data: githubRepos = [], isFetching: reposFetching, refetch: refetchRepos } = useGitHubRepos({
    enabled: githubConnected,
  });
  const [repoSearch, setRepoSearch] = useState("");

  const filteredRepos = useMemo(() => {
    const q = repoSearch.toLowerCase().trim();
    if (!q) return githubRepos;
    return githubRepos.filter((r) => r.full_name.toLowerCase().includes(q));
  }, [githubRepos, repoSearch]);

  function handleRepoSelect(e: React.ChangeEvent<HTMLSelectElement>) {
    const fullName = e.target.value;
    if (!fullName) return;
    const repo = githubRepos.find((r) => r.full_name === fullName);
    if (!repo) return;
    setForm((prev) => ({
      ...prev,
      git_repo: repo.clone_url,
      branch: repo.default_branch,
      name: prev.name || repo.name,
    }));
  }

  function handleOpenModal() {
    setShowModal(true);
    if (githubConnected && githubRepos.length === 0) {
      void refetchRepos();
    }
  }

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: name === "port" ? (value === "" ? undefined : Number(value)) : value,
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const payload: CreateAppInput = {
        ...form,
        domain: form.domain || undefined,
        git_repo: form.git_repo || undefined,
        branch: form.branch || undefined,
        image: form.image || undefined,
        cpu_limit: form.cpu_limit || undefined,
        memory_limit: form.memory_limit || undefined,
      };
      await createApp.mutateAsync(payload);
      toast.success(`App "${form.name}" created.`);
      setShowModal(false);
      setForm(defaultForm);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create app.");
    }
  }

  async function handleDeploy(name: string) {
    setActionPending(`deploy-${name}`);
    try {
      const result = await deployApp.mutateAsync(name);
      toast.success(result.message || `Deployment triggered for "${name}".`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Deployment failed.");
    } finally {
      setActionPending(null);
    }
  }

  async function handleRestart(name: string) {
    setActionPending(`restart-${name}`);
    try {
      await restartApp.mutateAsync(name);
      toast.success(`"${name}" restarted.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Restart failed.");
    } finally {
      setActionPending(null);
    }
  }

  async function handleStop(name: string) {
    setActionPending(`stop-${name}`);
    try {
      await stopApp.mutateAsync(name);
      toast.success(`"${name}" stopped.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Stop failed.");
    } finally {
      setActionPending(null);
    }
  }

  async function handleDestroy(name: string) {
    if (!window.confirm(`Destroy app "${name}"? This cannot be undone.`)) return;
    setActionPending(`destroy-${name}`);
    try {
      await destroyApp.mutateAsync(name);
      toast.success(`App "${name}" destroyed.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Destroy failed.");
    } finally {
      setActionPending(null);
    }
  }

  function isActionPending(key: string) {
    return actionPending === key;
  }

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Header */}
      <div className="mb-7 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Apps</h1>
          <p className="mt-1 text-sm text-slate-400">
            Deploy and manage your applications
          </p>
        </div>
        <button
          onClick={handleOpenModal}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
        >
          <Plus size={16} aria-hidden="true" />
          Create App
        </button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 size={28} className="animate-spin text-indigo-400" aria-label="Loading apps" />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-5 text-red-400">
          <p className="font-medium">Failed to load apps</p>
          <p className="mt-1 text-sm text-red-400/70">
            {error instanceof Error ? error.message : "Unknown error"}
          </p>
        </div>
      )}

      {/* Empty */}
      {!isLoading && !isError && apps.length === 0 && (
        <EmptyState
          icon={<Box size={28} />}
          title="No apps yet"
          description="Create your first app to start deploying."
          action={{ label: "Create App", onClick: handleOpenModal }}
        />
      )}

      {/* Table */}
      {apps.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-700">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-800/60">
                {["Name", "Server", "Domain", "Type", "Replicas", "Status", "Actions"].map(
                  (h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/40">
              {apps.map((app) => (
                <tr
                  key={app.id}
                  className="bg-slate-800/30 transition-colors hover:bg-slate-800/70"
                >
                  {/* Name */}
                  <td className="px-4 py-3">
                    <div>
                      <Link
                        to={`/apps/${encodeURIComponent(app.name)}`}
                        className="flex items-center gap-1 font-medium text-indigo-400 hover:text-indigo-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
                      >
                        {app.name}
                        <ChevronRight size={13} aria-hidden="true" />
                      </Link>
                      {app.git_repo && (
                        <div className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                          <GitBranch size={11} aria-hidden="true" />
                          {app.branch ?? "main"}
                        </div>
                      )}
                    </div>
                  </td>
                  {/* Server */}
                  <td className="px-4 py-3 text-slate-300">
                    {app.server_name}
                  </td>
                  {/* Domain */}
                  <td className="px-4 py-3">
                    {app.domain ? (
                      <div className="flex items-center gap-1.5 text-xs text-slate-300">
                        <Globe size={12} aria-hidden="true" />
                        {app.domain}
                      </div>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                  {/* Type */}
                  <td className="px-4 py-3 text-slate-400">
                    {app.app_type ?? "—"}
                  </td>
                  {/* Replicas */}
                  <td className="px-4 py-3 text-slate-300">
                    {app.replicas ?? 1}
                  </td>
                  {/* Status */}
                  <td className="px-4 py-3">
                    <StatusBadge status={app.status} />
                  </td>
                  {/* Actions */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      {/* Deploy */}
                      <button
                        onClick={() => handleDeploy(app.name)}
                        disabled={!!actionPending}
                        title="Deploy"
                        className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-emerald-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                        aria-label={`Deploy ${app.name}`}
                      >
                        {isActionPending(`deploy-${app.name}`) ? (
                          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                        ) : (
                          <Play size={14} aria-hidden="true" />
                        )}
                      </button>
                      {/* Restart */}
                      <button
                        onClick={() => handleRestart(app.name)}
                        disabled={!!actionPending}
                        title="Restart"
                        className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-amber-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                        aria-label={`Restart ${app.name}`}
                      >
                        {isActionPending(`restart-${app.name}`) ? (
                          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                        ) : (
                          <RefreshCw size={14} aria-hidden="true" />
                        )}
                      </button>
                      {/* Stop */}
                      <button
                        onClick={() => handleStop(app.name)}
                        disabled={!!actionPending}
                        title="Stop"
                        className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                        aria-label={`Stop ${app.name}`}
                      >
                        {isActionPending(`stop-${app.name}`) ? (
                          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                        ) : (
                          <Square size={14} aria-hidden="true" />
                        )}
                      </button>
                      {/* Destroy */}
                      <button
                        onClick={() => handleDestroy(app.name)}
                        disabled={!!actionPending}
                        title="Destroy"
                        className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                        aria-label={`Destroy ${app.name}`}
                      >
                        {isActionPending(`destroy-${app.name}`) ? (
                          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                        ) : (
                          <Trash2 size={14} aria-hidden="true" />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create App Modal */}
      {showModal && (
        <Modal title="Create App" onClose={() => { setShowModal(false); setForm(defaultForm); setRepoSearch(""); }}>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {/* Name */}
            <div>
              <label
                htmlFor="app-name"
                className="mb-1.5 block text-xs font-medium text-slate-300"
              >
                App Name <span className="text-red-400">*</span>
              </label>
              <input
                id="app-name"
                name="name"
                type="text"
                required
                value={form.name}
                onChange={handleChange}
                placeholder="my-app"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            {/* Server */}
            <div>
              <label
                htmlFor="app-server"
                className="mb-1.5 block text-xs font-medium text-slate-300"
              >
                Server <span className="text-red-400">*</span>
              </label>
              <select
                id="app-server"
                name="server_name"
                required
                value={form.server_name}
                onChange={handleChange}
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              >
                <option value="">Select a server</option>
                {servers.map((s) => (
                  <option key={s.id} value={s.name}>
                    {s.name} ({s.host})
                  </option>
                ))}
              </select>
            </div>

            {/* Domain + Port */}
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2">
                <label
                  htmlFor="app-domain"
                  className="mb-1.5 block text-xs font-medium text-slate-300"
                >
                  Domain
                </label>
                <input
                  id="app-domain"
                  name="domain"
                  type="text"
                  value={form.domain ?? ""}
                  onChange={handleChange}
                  placeholder="app.example.com"
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
                />
              </div>
              <div>
                <label
                  htmlFor="app-port"
                  className="mb-1.5 block text-xs font-medium text-slate-300"
                >
                  Port
                </label>
                <input
                  id="app-port"
                  name="port"
                  type="number"
                  min={1}
                  max={65535}
                  value={form.port ?? ""}
                  onChange={handleChange}
                  placeholder="3000"
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
                />
              </div>
            </div>

            {/* GitHub Repo Picker */}
            <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-3">
              <div className="mb-2 flex items-center gap-2">
                <Github size={14} className="shrink-0 text-slate-400" aria-hidden="true" />
                <span className="text-xs font-medium text-slate-300">GitHub Repository</span>
              </div>
              {githubConnected ? (
                <div className="space-y-2">
                  {/* Search filter */}
                  <div className="relative">
                    <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" aria-hidden="true" />
                    <input
                      type="text"
                      value={repoSearch}
                      onChange={(e) => setRepoSearch(e.target.value)}
                      placeholder="Filter repositories…"
                      aria-label="Filter GitHub repositories"
                      className="w-full rounded-md border border-slate-600 bg-slate-700 py-1.5 pl-8 pr-3 text-xs text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
                    />
                  </div>
                  {/* Repo select */}
                  <div className="relative">
                    {reposFetching && (
                      <div className="absolute inset-y-0 right-8 flex items-center">
                        <Loader2 size={12} className="animate-spin text-indigo-400" aria-hidden="true" />
                      </div>
                    )}
                    <select
                      aria-label="Select a GitHub repository"
                      onChange={handleRepoSelect}
                      defaultValue=""
                      className="w-full rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-xs text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
                    >
                      <option value="">Select a repository…</option>
                      {filteredRepos.map((repo) => (
                        <option key={repo.full_name} value={repo.full_name}>
                          {repo.full_name}{repo.private ? " (private)" : " (public)"}
                        </option>
                      ))}
                    </select>
                  </div>
                  {filteredRepos.length === 0 && !reposFetching && (
                    <p className="text-xs text-slate-500">
                      {repoSearch ? "No repositories match your filter." : "No repositories found."}
                    </p>
                  )}
                  <p className="text-xs text-slate-500">
                    Selecting a repo auto-fills the URL, branch, and name below.
                  </p>
                </div>
              ) : (
                <p className="text-xs text-slate-500">
                  <Lock size={11} className="mr-1 inline-block" aria-hidden="true" />
                  Connect GitHub in{" "}
                  <a href="/settings" className="text-indigo-400 hover:text-indigo-300">
                    Settings
                  </a>{" "}
                  to browse your repos.
                </p>
              )}
            </div>

            {/* Git Repo + Branch */}
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2">
                <label
                  htmlFor="app-git-repo"
                  className="mb-1.5 block text-xs font-medium text-slate-300"
                >
                  Git Repo URL
                </label>
                <input
                  id="app-git-repo"
                  name="git_repo"
                  type="url"
                  value={form.git_repo ?? ""}
                  onChange={handleChange}
                  placeholder="https://github.com/org/repo"
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
                />
              </div>
              <div>
                <label
                  htmlFor="app-branch"
                  className="mb-1.5 block text-xs font-medium text-slate-300"
                >
                  Branch
                </label>
                <input
                  id="app-branch"
                  name="branch"
                  type="text"
                  value={form.branch ?? ""}
                  onChange={handleChange}
                  placeholder="main"
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
                />
              </div>
            </div>

            {/* Docker Image */}
            <div>
              <label
                htmlFor="app-image"
                className="mb-1.5 block text-xs font-medium text-slate-300"
              >
                Docker Image
              </label>
              <input
                id="app-image"
                name="image"
                type="text"
                value={form.image ?? ""}
                onChange={handleChange}
                placeholder="nginx:latest"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            {/* Resource Limits */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="app-cpu-limit" className="mb-1.5 block text-xs font-medium text-slate-300">
                  CPU Limit
                </label>
                <input id="app-cpu-limit" name="cpu_limit" type="text" value={form.cpu_limit ?? ""} onChange={handleChange} placeholder="0.5" className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none" />
              </div>
              <div>
                <label htmlFor="app-memory-limit" className="mb-1.5 block text-xs font-medium text-slate-300">
                  Memory Limit
                </label>
                <input id="app-memory-limit" name="memory_limit" type="text" value={form.memory_limit ?? ""} onChange={handleChange} placeholder="512M" className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none" />
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => { setShowModal(false); setForm(defaultForm); setRepoSearch(""); }}
                className="rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createApp.isPending}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
              >
                {createApp.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Create App
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
