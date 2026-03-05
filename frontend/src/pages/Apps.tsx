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
  ChevronDown,
  Container,
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
  useTemplates,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";
import Modal from "@/components/Modal";
import EmptyState from "@/components/EmptyState";
import type { CreateAppInput, AppTemplate } from "@/api/client";

const defaultForm: CreateAppInput = {
  name: "",
  server_name: "",
  domain: "",
  port: undefined,
  git_repo: "",
  branch: "main",
  image: "",
  template: undefined,
  cpu_limit: "",
  memory_limit: "",
  build_type: undefined,
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
  const [sourceType, setSourceType] = useState<"template" | "github" | "image">("template");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<AppTemplate | null>(null);
  const [domainRows, setDomainRows] = useState<{ service: string; domain: string; port: string }[]>([]);

  // Templates
  const { data: templates = [] } = useTemplates();

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
    setSourceType("template");
    setSelectedTemplate(null);
    setShowAdvanced(false);
    setDomainRows([]);
    if (githubConnected && githubRepos.length === 0) {
      void refetchRepos();
    }
  }

  function handleTemplateSelect(tmpl: AppTemplate) {
    setSelectedTemplate(tmpl);
    setForm((prev) => ({
      ...prev,
      name: prev.name || tmpl.name,
      template: tmpl.name,
      port: tmpl.port,
      image: "",
      git_repo: "",
      domains: Object.keys(tmpl.domain_map).length > 1
        ? Object.fromEntries(Object.keys(tmpl.domain_map).map((k) => [k, ""]))
        : undefined,
    }));
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
      // For multi-domain templates, send domains dict instead of domain string
      const hasMultiDomain = form.domains && Object.values(form.domains).some(Boolean);
      // For git/image domain rows
      const filledRows = domainRows.filter((r) => r.service && r.domain);
      const hasRowDomains = filledRows.length > 0;
      const payload: CreateAppInput = {
        ...form,
        domain: hasMultiDomain || hasRowDomains ? undefined : (form.domain || undefined),
        domains: hasMultiDomain
          ? Object.fromEntries(Object.entries(form.domains!).filter(([, v]) => v))
          : hasRowDomains
            ? Object.fromEntries(filledRows.map((r) => [r.service, r.domain]))
            : undefined,
        domain_ports: hasRowDomains
          ? Object.fromEntries(filledRows.filter((r) => r.port).map((r) => [r.service, Number(r.port)]))
          : undefined,
        git_repo: form.git_repo || undefined,
        branch: form.branch || undefined,
        image: form.image || undefined,
        template: form.template || undefined,
        cpu_limit: form.cpu_limit || undefined,
        memory_limit: form.memory_limit || undefined,
        build_type: form.build_type || undefined,
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
          <h1 className="text-2xl font-bold text-zinc-100">Apps</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Deploy and manage your applications
          </p>
        </div>
        <button
          onClick={handleOpenModal}
          className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
        >
          <Plus size={16} aria-hidden="true" />
          Create App
        </button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 size={28} className="animate-spin text-orange-400" aria-label="Loading apps" />
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
        <div className="overflow-hidden rounded-xl border border-zinc-700">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-zinc-700 bg-zinc-800/60">
                {["Name", "Server", "Domain", "Type", "Replicas", "Status", "Actions"].map(
                  (h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-700/40">
              {apps.map((app) => (
                <tr
                  key={app.id}
                  className="bg-zinc-800/30 transition-colors hover:bg-zinc-800/70"
                >
                  {/* Name */}
                  <td className="px-4 py-3">
                    <div>
                      <Link
                        to={`/apps/${encodeURIComponent(app.name)}`}
                        className="flex items-center gap-1 font-medium text-orange-400 hover:text-orange-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
                      >
                        {app.name}
                        <ChevronRight size={13} aria-hidden="true" />
                      </Link>
                      {app.git_repo && (
                        <div className="mt-0.5 flex items-center gap-1 text-xs text-zinc-500">
                          <GitBranch size={11} aria-hidden="true" />
                          {app.branch ?? "main"}
                        </div>
                      )}
                    </div>
                  </td>
                  {/* Server */}
                  <td className="px-4 py-3 text-zinc-300">
                    {app.server_name}
                  </td>
                  {/* Domain */}
                  <td className="px-4 py-3">
                    {app.domains && Object.keys(app.domains).length > 1 ? (
                      <div className="flex flex-col gap-1">
                        {Object.entries(app.domains).map(([svc, d]) => (
                          <div key={svc} className="flex items-center gap-1.5 text-xs text-zinc-300">
                            <Globe size={12} className="shrink-0" aria-hidden="true" />
                            <span className="text-zinc-500">{svc}:</span>
                            {d}
                          </div>
                        ))}
                      </div>
                    ) : app.domain ? (
                      <div className="flex items-center gap-1.5 text-xs text-zinc-300">
                        <Globe size={12} aria-hidden="true" />
                        {app.domain}
                      </div>
                    ) : (
                      <span className="text-zinc-500">—</span>
                    )}
                  </td>
                  {/* Type */}
                  <td className="px-4 py-3 text-zinc-400">
                    {app.app_type ?? "—"}
                  </td>
                  {/* Replicas */}
                  <td className="px-4 py-3 text-zinc-300">
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
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-emerald-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
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
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-amber-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
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
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
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
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
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
        <Modal title="Create App" onClose={() => { setShowModal(false); setForm(defaultForm); setRepoSearch(""); setSelectedTemplate(null); }}>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {/* Name + Server row */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="app-name" className="mb-1.5 block text-xs font-medium text-zinc-300">
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
                  className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                />
              </div>
              <div>
                <label htmlFor="app-server" className="mb-1.5 block text-xs font-medium text-zinc-300">
                  Server <span className="text-red-400">*</span>
                </label>
                <select
                  id="app-server"
                  name="server_name"
                  required
                  value={form.server_name}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                >
                  <option value="">Select…</option>
                  {servers.map((s) => (
                    <option key={s.id} value={s.name}>
                      {s.name} ({s.host})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Source type toggle */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-300">Source</label>
              <div className="flex rounded-lg border border-zinc-600 bg-zinc-800/60 p-0.5">
                <button
                  type="button"
                  onClick={() => { setSourceType("template"); setForm((prev) => ({ ...prev, image: "", git_repo: "", branch: "main" })); }}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${sourceType === "template" ? "bg-orange-600 text-white" : "text-zinc-400 hover:text-zinc-200"}`}
                >
                  <Box size={13} aria-hidden="true" />
                  Template
                </button>
                <button
                  type="button"
                  onClick={() => { setSourceType("github"); setSelectedTemplate(null); setForm((prev) => ({ ...prev, image: "", template: undefined })); }}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${sourceType === "github" ? "bg-orange-600 text-white" : "text-zinc-400 hover:text-zinc-200"}`}
                >
                  <Github size={13} aria-hidden="true" />
                  GitHub
                </button>
                <button
                  type="button"
                  onClick={() => { setSourceType("image"); setSelectedTemplate(null); setForm((prev) => ({ ...prev, git_repo: "", branch: "main", template: undefined })); }}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${sourceType === "image" ? "bg-orange-600 text-white" : "text-zinc-400 hover:text-zinc-200"}`}
                >
                  <Container size={13} aria-hidden="true" />
                  Image
                </button>
              </div>
            </div>

            {/* Template picker */}
            {sourceType === "template" && (
              <div className="grid grid-cols-2 gap-2">
                {templates.map((tmpl) => (
                  <button
                    key={tmpl.name}
                    type="button"
                    onClick={() => handleTemplateSelect(tmpl)}
                    className={`rounded-lg border p-3 text-left transition-colors ${selectedTemplate?.name === tmpl.name ? "border-orange-500 bg-orange-500/10" : "border-zinc-700 bg-zinc-800/40 hover:border-zinc-500"}`}
                  >
                    <div className="text-sm font-medium text-zinc-200">{tmpl.name}</div>
                    <div className="mt-0.5 text-xs text-zinc-400">{tmpl.description}</div>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {tmpl.services.map((svc) => (
                        <span key={svc} className="rounded bg-zinc-700/60 px-1.5 py-0.5 text-[10px] text-zinc-400">
                          {svc}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            )}

            {/* GitHub source */}
            {sourceType === "github" && (
              <>
                {githubConnected ? (
                  <div className="space-y-2 rounded-lg border border-zinc-700 bg-zinc-800/40 p-3">
                    <div className="relative">
                      <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" aria-hidden="true" />
                      <input
                        type="text"
                        value={repoSearch}
                        onChange={(e) => setRepoSearch(e.target.value)}
                        placeholder="Search repositories…"
                        aria-label="Filter GitHub repositories"
                        className="w-full rounded-md border border-zinc-600 bg-zinc-700 py-1.5 pl-8 pr-3 text-xs text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                      />
                    </div>
                    <div className="relative">
                      {reposFetching && (
                        <div className="absolute inset-y-0 right-8 flex items-center">
                          <Loader2 size={12} className="animate-spin text-orange-400" aria-hidden="true" />
                        </div>
                      )}
                      <select
                        aria-label="Select a GitHub repository"
                        onChange={handleRepoSelect}
                        defaultValue=""
                        className="w-full rounded-md border border-zinc-600 bg-zinc-700 px-3 py-1.5 text-xs text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                      >
                        <option value="">Select a repository…</option>
                        {filteredRepos.map((repo) => (
                          <option key={repo.full_name} value={repo.full_name}>
                            {repo.full_name}{repo.private ? " 🔒" : ""}
                          </option>
                        ))}
                      </select>
                    </div>
                    {filteredRepos.length === 0 && !reposFetching && (
                      <p className="text-xs text-zinc-500">
                        {repoSearch ? "No match." : "No repositories found."}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="rounded-lg border border-zinc-700 bg-zinc-800/40 p-3">
                    <p className="text-xs text-zinc-500">
                      <Lock size={11} className="mr-1 inline-block" aria-hidden="true" />
                      Connect GitHub in{" "}
                      <a href="/settings" className="text-orange-400 hover:text-orange-300">Settings</a>{" "}
                      to browse repos, or enter a URL manually.
                    </p>
                  </div>
                )}
                {/* Manual URL + Branch (collapsed if repo was selected) */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-2">
                    <label htmlFor="app-git-repo" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Git URL
                    </label>
                    <input
                      id="app-git-repo"
                      name="git_repo"
                      type="url"
                      value={form.git_repo ?? ""}
                      onChange={handleChange}
                      placeholder="https://github.com/org/repo"
                      className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                    />
                  </div>
                  <div>
                    <label htmlFor="app-branch" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Branch
                    </label>
                    <input
                      id="app-branch"
                      name="branch"
                      type="text"
                      value={form.branch ?? ""}
                      onChange={handleChange}
                      placeholder="main"
                      className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                    />
                  </div>
                </div>
              </>
            )}

            {/* Docker image source */}
            {sourceType === "image" && (
              <div>
                <label htmlFor="app-image" className="mb-1.5 block text-xs font-medium text-zinc-300">
                  Image
                </label>
                <input
                  id="app-image"
                  name="image"
                  type="text"
                  value={form.image ?? ""}
                  onChange={handleChange}
                  placeholder="nginx:alpine"
                  className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                />
              </div>
            )}

            {/* Domain + Port */}
            {selectedTemplate && Object.keys(selectedTemplate.domain_map).length > 1 ? (
              /* Multi-domain template: one field per service */
              <div className="space-y-2">
                {Object.entries(selectedTemplate.domain_map).map(([svc]) => (
                  <div key={svc}>
                    <label className="mb-1.5 block text-xs font-medium text-zinc-300 capitalize">
                      {svc} domain
                    </label>
                    <input
                      type="text"
                      value={form.domains?.[svc] ?? ""}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          domains: { ...prev.domains, [svc]: e.target.value },
                        }))
                      }
                      placeholder={`${svc}.example.com`}
                      className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                    />
                  </div>
                ))}
              </div>
            ) : domainRows.length > 0 ? (
              /* Multi-domain rows for git/image apps */
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-zinc-300">Service Domains</label>
                  <button
                    type="button"
                    onClick={() => setDomainRows((prev) => [...prev, { service: "", domain: "", port: "" }])}
                    className="flex items-center gap-1 text-xs text-orange-400 hover:text-orange-300"
                  >
                    <Plus size={12} /> Add
                  </button>
                </div>
                <div className="grid grid-cols-12 gap-2 text-[10px] uppercase tracking-wider text-zinc-500 px-0.5">
                  <span className="col-span-3">Service</span>
                  <span className="col-span-5">Domain</span>
                  <span className="col-span-3">Port</span>
                  <span className="col-span-1" />
                </div>
                {domainRows.map((row, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2">
                    <input
                      className="col-span-3 rounded-lg border border-zinc-600 bg-zinc-700 px-2 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                      placeholder="api"
                      value={row.service}
                      onChange={(e) => setDomainRows((prev) => prev.map((r, j) => (j === i ? { ...r, service: e.target.value } : r)))}
                    />
                    <input
                      className="col-span-5 rounded-lg border border-zinc-600 bg-zinc-700 px-2 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                      placeholder="api.example.com"
                      value={row.domain}
                      onChange={(e) => setDomainRows((prev) => prev.map((r, j) => (j === i ? { ...r, domain: e.target.value } : r)))}
                    />
                    <input
                      type="number"
                      className="col-span-3 rounded-lg border border-zinc-600 bg-zinc-700 px-2 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                      placeholder="4000"
                      value={row.port}
                      onChange={(e) => setDomainRows((prev) => prev.map((r, j) => (j === i ? { ...r, port: e.target.value } : r)))}
                    />
                    <button
                      type="button"
                      className="col-span-1 flex items-center justify-center text-zinc-500 hover:text-red-400"
                      onClick={() => setDomainRows((prev) => prev.filter((_, j) => j !== i))}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-2">
                    <label htmlFor="app-domain" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Domain
                    </label>
                    <input
                      id="app-domain"
                      name="domain"
                      type="text"
                      value={form.domain ?? ""}
                      onChange={handleChange}
                      placeholder="app.example.com"
                      className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                    />
                  </div>
                  <div>
                    <label htmlFor="app-port" className="mb-1.5 block text-xs font-medium text-zinc-300">
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
                      className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                    />
                  </div>
                </div>
                {(sourceType === "github" || sourceType === "image") && (
                  <button
                    type="button"
                    onClick={() => setDomainRows([{ service: "", domain: "", port: "" }])}
                    className="flex items-center gap-1 text-xs text-zinc-400 hover:text-orange-400 transition-colors"
                    aria-label="Add service domain"
                  >
                    <Plus size={12} /> Add service domain
                  </button>
                )}
              </div>
            )}

            {/* Advanced toggle */}
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-1 text-xs text-zinc-400 transition-colors hover:text-zinc-200"
            >
              <ChevronDown size={13} className={`transition-transform ${showAdvanced ? "rotate-180" : ""}`} aria-hidden="true" />
              Advanced options
            </button>

            {showAdvanced && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="app-cpu-limit" className="mb-1.5 block text-xs font-medium text-zinc-300">
                    CPU Limit
                  </label>
                  <input id="app-cpu-limit" name="cpu_limit" type="text" value={form.cpu_limit ?? ""} onChange={handleChange} placeholder="0.5" className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none" />
                </div>
                <div>
                  <label htmlFor="app-memory-limit" className="mb-1.5 block text-xs font-medium text-zinc-300">
                    Memory Limit
                  </label>
                  <input id="app-memory-limit" name="memory_limit" type="text" value={form.memory_limit ?? ""} onChange={handleChange} placeholder="512M" className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none" />
                </div>
                {sourceType === "github" && (
                  <div className="col-span-2">
                    <label htmlFor="app-build-type" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Build Type
                    </label>
                    <select
                      id="app-build-type"
                      name="build_type"
                      value={form.build_type ?? "auto"}
                      onChange={handleChange}
                      className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                    >
                      <option value="auto">Auto-detect</option>
                      <option value="dockerfile">Dockerfile</option>
                      <option value="nixpacks">Nixpacks</option>
                    </select>
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => { setShowModal(false); setForm(defaultForm); setRepoSearch(""); setSelectedTemplate(null); }}
                className="rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createApp.isPending}
                className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
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
