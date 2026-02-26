import { useState } from "react";
import { Settings as SettingsIcon, Plus, Trash2, Send, Bell, Loader2, Key, Server as ServerIcon, GitBranch, Copy, Check, Eye, EyeOff, Github, Link as LinkIcon } from "lucide-react";
import {
  useWebhooks,
  useCreateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  useSSHKeys,
  useGenerateSSHKey,
  useDeleteSSHKey,
  useDeploySSHKey,
  useServers,
  useSelfUpdateConfig,
  useGitHubStatus,
  useConnectGitHub,
  useDisconnectGitHub,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import Modal from "@/components/Modal";
import EmptyState from "@/components/EmptyState";
import type { CreateWebhookInput } from "@/api/client";

// ─── Available webhook event types ────────────────────────────────────────────

const WEBHOOK_EVENTS: { value: string; label: string }[] = [
  { value: "deploy.success", label: "Deploy Success" },
  { value: "deploy.failure", label: "Deploy Failure" },
  { value: "backup.complete", label: "Backup Complete" },
  { value: "backup.restore", label: "Backup Restore" },
  { value: "health.down", label: "Health Down" },
  { value: "health.up", label: "Health Up" },
];

// ─── Event badge color map ─────────────────────────────────────────────────────

function eventBadgeClass(event: string): string {
  switch (event) {
    case "deploy.success":
      return "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30";
    case "deploy.failure":
      return "bg-red-500/15 text-red-300 ring-1 ring-red-500/30";
    case "backup.complete":
      return "bg-blue-500/15 text-blue-300 ring-1 ring-blue-500/30";
    case "backup.restore":
      return "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30";
    case "health.down":
      return "bg-red-500/15 text-red-300 ring-1 ring-red-500/30";
    case "health.up":
      return "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30";
    default:
      return "bg-slate-700 text-slate-300";
  }
}

// ─── Relative time helper ─────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ─── Default form state ────────────────────────────────────────────────────────

const defaultForm: CreateWebhookInput & { urlError: string } = {
  url: "",
  events: [],
  secret: "",
  urlError: "",
};

// ─── Settings page ────────────────────────────────────────────────────────────

export default function Settings() {
  const { data: webhooks = [], isLoading, isError, error } = useWebhooks();
  const createWebhook = useCreateWebhook();
  const deleteWebhook = useDeleteWebhook();
  const testWebhook = useTestWebhook();
  const toast = useToast();

  // SSH Keys state
  const { data: sshKeys = [], isLoading: keysLoading } = useSSHKeys();
  const { data: servers = [] } = useServers();
  const generateKey = useGenerateSSHKey();
  const deleteKey = useDeleteSSHKey();
  const deployKey = useDeploySSHKey();

  const [showGenerateKeyModal, setShowGenerateKeyModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [deletingKeyName, setDeletingKeyName] = useState<string | null>(null);
  const [showDeployKeyModal, setShowDeployKeyModal] = useState(false);
  const [deployKeyName, setDeployKeyName] = useState<string | null>(null);
  const [deployServerName, setDeployServerName] = useState("");

  // Self-update config
  const { data: selfUpdateConfig } = useSelfUpdateConfig();
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [showSecret, setShowSecret] = useState(false);

  // GitHub connection
  const { data: githubStatus, isLoading: githubLoading } = useGitHubStatus();
  const connectGitHub = useConnectGitHub();
  const disconnectGitHub = useDisconnectGitHub();
  const [githubToken, setGithubToken] = useState("");
  const [showGithubToken, setShowGithubToken] = useState(false);

  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState(defaultForm);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // ─── SSH Key handlers ────────────────────────────────────────────────────────

  async function handleGenerateKey(e: React.FormEvent) {
    e.preventDefault();
    if (!newKeyName.trim()) return;
    try {
      await generateKey.mutateAsync(newKeyName.trim());
      toast.success(`SSH key "${newKeyName.trim()}" generated.`);
      setShowGenerateKeyModal(false);
      setNewKeyName("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to generate key.");
    }
  }

  async function handleDeleteKey(name: string) {
    if (!window.confirm(`Delete SSH key "${name}"? This cannot be undone.`)) return;
    setDeletingKeyName(name);
    try {
      await deleteKey.mutateAsync(name);
      toast.success(`SSH key "${name}" deleted.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete key.");
    } finally {
      setDeletingKeyName(null);
    }
  }

  function openDeployKeyModal(name: string) {
    setDeployKeyName(name);
    setDeployServerName(servers[0]?.name ?? "");
    setShowDeployKeyModal(true);
  }

  async function handleDeployKey(e: React.FormEvent) {
    e.preventDefault();
    if (deployKeyName == null || !deployServerName) return;
    try {
      const result = await deployKey.mutateAsync({ name: deployKeyName, serverName: deployServerName });
      toast.success(result.message ?? "Key deployed.");
      setShowDeployKeyModal(false);
      setDeployKeyName(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to deploy key.");
    }
  }

  // ─── Copy to clipboard ─────────────────────────────────────────────────────

  function copyToClipboard(text: string, field: string) {
    void navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    });
  }

  // ─── GitHub handlers ────────────────────────────────────────────────────────

  async function handleConnectGitHub(e: React.FormEvent) {
    e.preventDefault();
    if (!githubToken.trim()) return;
    try {
      await connectGitHub.mutateAsync(githubToken.trim());
      toast.success("GitHub account connected.");
      setGithubToken("");
      setShowGithubToken(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to connect GitHub account.");
    }
  }

  async function handleDisconnectGitHub() {
    if (!window.confirm("Disconnect your GitHub account? Your token will be removed.")) return;
    try {
      await disconnectGitHub.mutateAsync();
      toast.success("GitHub account disconnected.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to disconnect GitHub account.");
    }
  }

  // ─── Form handlers ──────────────────────────────────────────────────────────

  function handleUrlChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { value } = e.target;
    setForm((prev) => ({
      ...prev,
      url: value,
      urlError:
        value && !value.startsWith("https://")
          ? "URL must start with https://"
          : "",
    }));
  }

  function handleSecretChange(e: React.ChangeEvent<HTMLInputElement>) {
    setForm((prev) => ({ ...prev, secret: e.target.value }));
  }

  function handleEventToggle(eventValue: string) {
    setForm((prev) => {
      const already = prev.events.includes(eventValue);
      return {
        ...prev,
        events: already
          ? prev.events.filter((ev) => ev !== eventValue)
          : [...prev.events, eventValue],
      };
    });
  }

  function closeModal() {
    setShowModal(false);
    setForm(defaultForm);
  }

  function validateForm(): boolean {
    if (!form.url.startsWith("https://")) {
      setForm((prev) => ({
        ...prev,
        urlError: "URL must start with https://",
      }));
      return false;
    }
    if (form.events.length === 0) {
      toast.error("Select at least one event.");
      return false;
    }
    return true;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validateForm()) return;

    const payload: CreateWebhookInput = {
      url: form.url,
      events: form.events,
      ...(form.secret ? { secret: form.secret } : {}),
    };

    try {
      await createWebhook.mutateAsync(payload);
      toast.success("Webhook added.");
      closeModal();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add webhook.");
    }
  }

  // ─── Action handlers ────────────────────────────────────────────────────────

  async function handleTest(id: number) {
    setTestingId(id);
    try {
      const result = await testWebhook.mutateAsync(id);
      toast.success(result.message ?? "Test delivery sent.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Test delivery failed.");
    } finally {
      setTestingId(null);
    }
  }

  async function handleDelete(id: number, url: string) {
    if (
      !window.confirm(`Remove webhook for "${url}"? This cannot be undone.`)
    )
      return;
    setDeletingId(id);
    try {
      await deleteWebhook.mutateAsync(id);
      toast.success("Webhook removed.");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to remove webhook."
      );
    } finally {
      setDeletingId(null);
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Page header */}
      <div className="mb-7 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-700">
          <SettingsIcon size={20} className="text-indigo-400" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Settings</h1>
          <p className="mt-0.5 text-sm text-slate-400">
            Platform configuration and integrations
          </p>
        </div>
      </div>

      {/* SSH Keys section */}
      <section aria-labelledby="ssh-keys-heading" className="mb-10">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 id="ssh-keys-heading" className="text-base font-semibold text-slate-100">
              SSH Keys
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Generate and manage SSH key pairs for server access. Deploy keys to servers to enable passwordless authentication.
            </p>
          </div>
          <button
            onClick={() => setShowGenerateKeyModal(true)}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
          >
            <Plus size={16} aria-hidden="true" />
            Generate Key
          </button>
        </div>

        {keysLoading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={28} className="animate-spin text-indigo-400" aria-label="Loading SSH keys" />
          </div>
        )}

        {!keysLoading && sshKeys.length === 0 && (
          <EmptyState
            icon={<Key size={28} />}
            title="No SSH keys"
            description="Generate an SSH key pair to use for server authentication."
            action={{ label: "Generate Key", onClick: () => setShowGenerateKeyModal(true) }}
          />
        )}

        {sshKeys.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-slate-700">
            <table className="w-full text-sm" role="table">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-800/60">
                  {["Name", "Type", "Fingerprint", "Created", "Actions"].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/40">
                {sshKeys.map((key) => (
                  <tr key={key.id} className="bg-slate-800/30 transition-colors hover:bg-slate-800/70">
                    <td className="px-4 py-3 font-medium text-slate-200">{key.name}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded-md bg-slate-700 px-2 py-0.5 font-mono text-xs text-slate-300">
                        {key.key_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-400" title={key.fingerprint}>
                      {key.fingerprint.length > 32 ? `${key.fingerprint.slice(0, 32)}…` : key.fingerprint}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                      {relativeTime(key.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => openDeployKeyModal(key.name)}
                          title="Deploy to server"
                          aria-label={`Deploy ${key.name} to server`}
                          className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
                        >
                          <ServerIcon size={15} aria-hidden="true" />
                        </button>
                        <button
                          onClick={() => void handleDeleteKey(key.name)}
                          disabled={deletingKeyName === key.name}
                          title="Delete key"
                          aria-label={`Delete ${key.name}`}
                          className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                        >
                          {deletingKeyName === key.name ? (
                            <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                          ) : (
                            <Trash2 size={15} aria-hidden="true" />
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
      </section>

      {/* GitHub section */}
      <section aria-labelledby="github-heading" className="mb-10">
        <div className="mb-4">
          <h2 id="github-heading" className="text-base font-semibold text-slate-100">
            GitHub
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Connect your GitHub account to deploy private repositories.
          </p>
        </div>

        {githubLoading && (
          <div className="flex items-center justify-center py-10">
            <Loader2 size={24} className="animate-spin text-indigo-400" aria-label="Loading GitHub status" />
          </div>
        )}

        {!githubLoading && githubStatus && (
          githubStatus.connected ? (
            /* Connected state */
            <div className="overflow-hidden rounded-xl border border-slate-700 bg-slate-800/30">
              <div className="flex items-center justify-between px-4 py-4">
                <div className="flex items-center gap-3">
                  <Github size={20} className="shrink-0 text-slate-300" aria-hidden="true" />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-200">
                        Connected as{" "}
                        <span className="text-indigo-300">{githubStatus.username}</span>
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-300 ring-1 ring-emerald-500/30">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
                        Connected
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-500">Your token is encrypted at rest.</p>
                  </div>
                </div>
                <button
                  onClick={() => void handleDisconnectGitHub()}
                  disabled={disconnectGitHub.isPending}
                  className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm font-medium text-slate-300 transition-colors hover:border-red-500/50 hover:bg-red-500/10 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
                >
                  {disconnectGitHub.isPending && (
                    <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                  )}
                  Disconnect
                </button>
              </div>
            </div>
          ) : (
            /* Disconnected state */
            <div className="overflow-hidden rounded-xl border border-slate-700 bg-slate-800/30">
              <form onSubmit={(e) => void handleConnectGitHub(e)} className="p-4 space-y-4" noValidate>
                <div className="flex items-start gap-3">
                  <Github size={20} className="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
                  <p className="text-sm text-slate-400">
                    Connect your GitHub account to browse and deploy private repositories directly from the Create App dialog.
                  </p>
                </div>
                <div>
                  <label htmlFor="github-token" className="mb-1.5 block text-xs font-medium text-slate-300">
                    Personal Access Token <span className="text-red-400">*</span>
                  </label>
                  <div className="relative">
                    <input
                      id="github-token"
                      type={showGithubToken ? "text" : "password"}
                      required
                      value={githubToken}
                      onChange={(e) => setGithubToken(e.target.value)}
                      placeholder="ghp_••••••••••••••••••••••••••••••••••••••"
                      className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 pr-10 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => setShowGithubToken((v) => !v)}
                      title={showGithubToken ? "Hide token" : "Show token"}
                      className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-200"
                    >
                      {showGithubToken ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
                    </button>
                  </div>
                  <p className="mt-1.5 text-xs text-slate-500">
                    Required scopes: <code className="font-mono text-slate-400">repo</code>,{" "}
                    <code className="font-mono text-slate-400">admin:repo_hook</code>
                  </p>
                  <a
                    href="https://github.com/settings/tokens/new?scopes=repo,admin:repo_hook&description=infrakt"
                    target="_blank"
                    rel="noreferrer noopener"
                    className="mt-1 inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300"
                  >
                    <LinkIcon size={11} aria-hidden="true" />
                    Generate a token
                  </a>
                </div>
                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={connectGitHub.isPending || !githubToken.trim()}
                    className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
                  >
                    {connectGitHub.isPending && (
                      <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                    )}
                    Connect
                  </button>
                </div>
              </form>
            </div>
          )
        )}
      </section>

      {/* Self-Update Webhook section */}
      {selfUpdateConfig && (
        <section aria-labelledby="self-update-heading" className="mb-10">
          <div className="mb-4">
            <h2 id="self-update-heading" className="text-base font-semibold text-slate-100">
              Auto-Deploy Webhook
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Configure a GitHub webhook to automatically update infrakt when you push to main.
            </p>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-700 bg-slate-800/30">
            <div className="divide-y divide-slate-700/40">
              {/* Webhook URL */}
              <div className="flex items-center justify-between px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Payload URL</p>
                  <p className="mt-1 truncate font-mono text-sm text-slate-200">{selfUpdateConfig.webhook_url}</p>
                </div>
                <button
                  onClick={() => copyToClipboard(selfUpdateConfig.webhook_url, "url")}
                  title="Copy URL"
                  className="ml-3 shrink-0 rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
                >
                  {copiedField === "url" ? <Check size={15} className="text-emerald-400" /> : <Copy size={15} />}
                </button>
              </div>

              {/* Webhook Secret */}
              <div className="flex items-center justify-between px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Secret</p>
                  <p className="mt-1 truncate font-mono text-sm text-slate-200">
                    {showSecret ? selfUpdateConfig.webhook_secret : "••••••••••••••••••••••••••••••••"}
                  </p>
                </div>
                <div className="ml-3 flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => setShowSecret(!showSecret)}
                    title={showSecret ? "Hide secret" : "Show secret"}
                    className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
                  >
                    {showSecret ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                  <button
                    onClick={() => copyToClipboard(selfUpdateConfig.webhook_secret, "secret")}
                    title="Copy secret"
                    className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
                  >
                    {copiedField === "secret" ? <Check size={15} className="text-emerald-400" /> : <Copy size={15} />}
                  </button>
                </div>
              </div>

              {/* Content Type & Events */}
              <div className="flex items-center gap-8 px-4 py-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Content Type</p>
                  <p className="mt-1 font-mono text-sm text-slate-200">application/json</p>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Events</p>
                  <span className="mt-1 inline-flex items-center gap-1.5 rounded-md bg-indigo-500/15 px-2 py-0.5 text-xs font-medium text-indigo-300 ring-1 ring-indigo-500/30">
                    <GitBranch size={12} />
                    push
                  </span>
                </div>
              </div>
            </div>
          </div>

          <p className="mt-3 text-xs text-slate-500">
            Add these values in your GitHub repo: Settings &rarr; Webhooks &rarr; Add webhook
          </p>
        </section>
      )}

      {/* Webhooks section */}
      <section aria-labelledby="webhooks-heading">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2
              id="webhooks-heading"
              className="text-base font-semibold text-slate-100"
            >
              Notification Webhooks
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Send HTTP POST payloads to external URLs when deployment and backup
              events occur.
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
          >
            <Plus size={16} aria-hidden="true" />
            Add Webhook
          </button>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-20">
            <Loader2
              size={28}
              className="animate-spin text-indigo-400"
              aria-label="Loading webhooks"
            />
          </div>
        )}

        {/* Error */}
        {isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-5 text-red-400">
            <p className="font-medium">Failed to load webhooks</p>
            <p className="mt-1 text-sm text-red-400/70">
              {error instanceof Error ? error.message : "Unknown error"}
            </p>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !isError && webhooks.length === 0 && (
          <EmptyState
            icon={<Bell size={28} />}
            title="No webhooks configured"
            description="Add a webhook to receive notifications when deployment or backup events happen."
            action={{
              label: "Add Webhook",
              onClick: () => setShowModal(true),
            }}
          />
        )}

        {/* Webhooks table */}
        {webhooks.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-slate-700">
            <table className="w-full text-sm" role="table">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-800/60">
                  {["URL", "Events", "Created", "Actions"].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/40">
                {webhooks.map((webhook) => (
                  <tr
                    key={webhook.id}
                    className="bg-slate-800/30 transition-colors hover:bg-slate-800/70"
                  >
                    {/* URL */}
                    <td className="max-w-xs px-4 py-3">
                      <span
                        className="block truncate font-mono text-xs text-slate-200"
                        title={webhook.url}
                      >
                        {webhook.url.length > 50
                          ? `${webhook.url.slice(0, 50)}…`
                          : webhook.url}
                      </span>
                    </td>

                    {/* Events */}
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1.5">
                        {webhook.events.map((ev) => (
                          <span
                            key={ev}
                            className={[
                              "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
                              eventBadgeClass(ev),
                            ].join(" ")}
                          >
                            {ev}
                          </span>
                        ))}
                      </div>
                    </td>

                    {/* Created */}
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                      {relativeTime(webhook.created_at)}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => void handleTest(webhook.id)}
                          disabled={testingId === webhook.id}
                          title="Send test delivery"
                          aria-label={`Send test delivery to ${webhook.url}`}
                          className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                        >
                          {testingId === webhook.id ? (
                            <Loader2
                              size={15}
                              className="animate-spin"
                              aria-hidden="true"
                            />
                          ) : (
                            <Send size={15} aria-hidden="true" />
                          )}
                        </button>
                        <button
                          onClick={() =>
                            void handleDelete(webhook.id, webhook.url)
                          }
                          disabled={deletingId === webhook.id}
                          title="Remove webhook"
                          aria-label={`Remove webhook for ${webhook.url}`}
                          className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                        >
                          {deletingId === webhook.id ? (
                            <Loader2
                              size={15}
                              className="animate-spin"
                              aria-hidden="true"
                            />
                          ) : (
                            <Trash2 size={15} aria-hidden="true" />
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
      </section>

      {/* Generate SSH Key Modal */}
      {showGenerateKeyModal && (
        <Modal title="Generate SSH Key" onClose={() => { setShowGenerateKeyModal(false); setNewKeyName(""); }}>
          <form onSubmit={(e) => void handleGenerateKey(e)} className="space-y-4" noValidate>
            <div>
              <label htmlFor="key-name" className="mb-1.5 block text-xs font-medium text-slate-300">
                Key Name <span className="text-red-400">*</span>
              </label>
              <input
                id="key-name"
                type="text"
                required
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="my-server-key"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>
            <div className="flex justify-end gap-3 pt-1">
              <button
                type="button"
                onClick={() => { setShowGenerateKeyModal(false); setNewKeyName(""); }}
                className="rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={generateKey.isPending || !newKeyName.trim()}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
              >
                {generateKey.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Generate
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Deploy SSH Key Modal */}
      {showDeployKeyModal && (
        <Modal title="Deploy Key to Server" onClose={() => { setShowDeployKeyModal(false); setDeployKeyName(null); }}>
          <form onSubmit={(e) => void handleDeployKey(e)} className="space-y-4" noValidate>
            <p className="text-sm text-slate-400">
              Copy this SSH key to the authorized_keys file on the selected server.
            </p>
            <div>
              <label htmlFor="deploy-server" className="mb-1.5 block text-xs font-medium text-slate-300">
                Server <span className="text-red-400">*</span>
              </label>
              <select
                id="deploy-server"
                required
                value={deployServerName}
                onChange={(e) => setDeployServerName(e.target.value)}
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
            <div className="flex justify-end gap-3 pt-1">
              <button
                type="button"
                onClick={() => { setShowDeployKeyModal(false); setDeployKeyName(null); }}
                className="rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={deployKey.isPending || !deployServerName}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
              >
                {deployKey.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Deploy
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Add Webhook Modal */}
      {showModal && (
        <Modal title="Add Webhook" onClose={closeModal}>
          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            {/* URL */}
            <div>
              <label
                htmlFor="webhook-url"
                className="mb-1.5 block text-xs font-medium text-slate-300"
              >
                Endpoint URL <span className="text-red-400">*</span>
              </label>
              <input
                id="webhook-url"
                type="url"
                required
                value={form.url}
                onChange={handleUrlChange}
                placeholder="https://hooks.slack.com/..."
                className={[
                  "w-full rounded-lg border bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:ring-1 focus-visible:outline-none",
                  form.urlError
                    ? "border-red-500 focus:border-red-500 focus:ring-red-500"
                    : "border-slate-600 focus:border-indigo-500 focus:ring-indigo-500",
                ].join(" ")}
                aria-describedby={form.urlError ? "webhook-url-error" : undefined}
                aria-invalid={Boolean(form.urlError)}
              />
              {form.urlError && (
                <p
                  id="webhook-url-error"
                  className="mt-1 text-xs text-red-400"
                  role="alert"
                >
                  {form.urlError}
                </p>
              )}
            </div>

            {/* Events */}
            <fieldset>
              <legend className="mb-2 text-xs font-medium text-slate-300">
                Events <span className="text-red-400">*</span>
              </legend>
              <div className="grid grid-cols-2 gap-2">
                {WEBHOOK_EVENTS.map(({ value, label }) => {
                  const checked = form.events.includes(value);
                  return (
                    <label
                      key={value}
                      className={[
                        "flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm transition-colors",
                        checked
                          ? "border-indigo-500/60 bg-indigo-500/10 text-slate-200"
                          : "border-slate-600 bg-slate-700/50 text-slate-400 hover:border-slate-500 hover:text-slate-300",
                      ].join(" ")}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => handleEventToggle(value)}
                        className="h-3.5 w-3.5 rounded border-slate-500 bg-slate-600 accent-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
                      />
                      <span>{label}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            {/* Secret */}
            <div>
              <label
                htmlFor="webhook-secret"
                className="mb-1.5 block text-xs font-medium text-slate-300"
              >
                Signing Secret{" "}
                <span className="font-normal text-slate-500">(optional)</span>
              </label>
              <input
                id="webhook-secret"
                type="password"
                value={form.secret ?? ""}
                onChange={handleSecretChange}
                placeholder="Optional HMAC signing secret"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
              <p className="mt-1 text-xs text-slate-500">
                Used to sign the X-Infrakt-Signature header sent with each
                delivery.
              </p>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-1">
              <button
                type="button"
                onClick={closeModal}
                className="rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createWebhook.isPending}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
              >
                {createWebhook.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Add Webhook
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
