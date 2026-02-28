import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Trash2,
  Loader2,
  Server,
  Box,
  Upload,
} from "lucide-react";
import {
  useServers,
  useAddServer,
  useDeleteServer,
  useServerStatus,
  useSSHKeys,
  useUploadSSHKey,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";
import Modal from "@/components/Modal";
import EmptyState from "@/components/EmptyState";
import type { CreateServerInput, Server as ServerType } from "@/api/client";

const PROVIDERS = ["", "hetzner", "digitalocean", "linode", "vultr", "aws", "gcp", "azure", "bare-metal", "other"];

const defaultForm: CreateServerInput = {
  name: "",
  host: "",
  user: "root",
  port: 22,
  ssh_key_path: "",
  provider: "",
};

// ─── MiniBar ──────────────────────────────────────────────────────────────────

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

// ─── ServerCard ───────────────────────────────────────────────────────────────

function ServerCard({
  server,
  onDelete,
  isDeleting,
}: {
  server: ServerType;
  onDelete: (name: string) => void;
  isDeleting: boolean;
}) {
  const { data: statusData } = useServerStatus(server.name, {
    enabled: server.status === "active",
  });

  return (
    <div className="relative rounded-xl border border-zinc-700 bg-zinc-800 p-5 transition-all hover:border-orange-500/20">
      {/* Delete button */}
      <button
        onClick={() => onDelete(server.name)}
        disabled={isDeleting}
        title="Delete server"
        className="absolute right-3 top-3 rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
        aria-label={`Delete ${server.name}`}
      >
        {isDeleting ? (
          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
        ) : (
          <Trash2 size={14} aria-hidden="true" />
        )}
      </button>

      {/* Name + Status */}
      <div className="mb-3 flex items-center gap-2.5">
        <Link
          to={`/servers/${encodeURIComponent(server.name)}`}
          className="text-base font-semibold text-orange-400 hover:text-orange-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
        >
          {server.name}
        </Link>
        <StatusBadge status={server.status} />
      </div>

      {/* Connection string */}
      <p className="mb-1 font-mono text-xs text-zinc-400">
        {server.user}@{server.host}:{server.port}
      </p>

      {/* Provider */}
      {server.provider && (
        <p className="mb-3 text-xs text-zinc-500">{server.provider}</p>
      )}
      {!server.provider && <div className="mb-3" />}

      {/* Resource bars or offline */}
      <div className="mb-3 space-y-1.5">
        {statusData ? (
          <>
            {statusData.cpu != null && (
              <MiniBar label="CPU" percent={statusData.cpu} />
            )}
            {statusData.memory && (
              <MiniBar label="MEM" percent={statusData.memory.percent} />
            )}
            {statusData.disk && (
              <MiniBar label="DSK" percent={statusData.disk.percent} />
            )}
          </>
        ) : server.status === "active" ? (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Loader2 size={12} className="animate-spin" aria-hidden="true" />
            Loading metrics...
          </div>
        ) : (
          <p className="text-xs text-zinc-500">Offline</p>
        )}
      </div>

      {/* Footer: app count + tags */}
      <div className="flex items-center justify-between border-t border-zinc-700/50 pt-3">
        <span className="flex items-center gap-1.5 text-xs text-zinc-400">
          <Box size={12} aria-hidden="true" />
          {server.app_count} app{server.app_count !== 1 ? "s" : ""}
        </span>
        <div className="flex flex-wrap gap-1">
          {(server.tags ?? []).map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center rounded-md bg-zinc-700 px-2 py-0.5 text-[11px] font-medium text-zinc-300"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Servers Page ─────────────────────────────────────────────────────────────

export default function Servers() {
  const { data: servers = [], isLoading, isError, error } = useServers();
  const addServer = useAddServer();
  const deleteServer = useDeleteServer();
  const toast = useToast();

  const { data: sshKeys = [] } = useSSHKeys();
  const uploadKey = useUploadSSHKey();
  const [showUploadKeyInline, setShowUploadKeyInline] = useState(false);
  const [inlineKeyName, setInlineKeyName] = useState("");
  const [inlineKeyFile, setInlineKeyFile] = useState<File | null>(null);

  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<CreateServerInput>(defaultForm);
  const [deletingName, setDeletingName] = useState<string | null>(null);

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
      await addServer.mutateAsync(form);
      toast.success(`Server "${form.name}" added successfully.`);
      setShowModal(false);
      setForm(defaultForm);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to add server."
      );
    }
  }

  async function handleInlineUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!inlineKeyName.trim() || !inlineKeyFile) return;
    try {
      await uploadKey.mutateAsync({ name: inlineKeyName.trim(), file: inlineKeyFile });
      setForm((prev) => ({ ...prev, ssh_key_path: `~/.infrakt/keys/${inlineKeyName.trim()}` }));
      setShowUploadKeyInline(false);
      setInlineKeyName("");
      setInlineKeyFile(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to upload key.");
    }
  }

  async function handleDelete(name: string) {
    if (!window.confirm(`Delete server "${name}"? This cannot be undone.`)) return;
    setDeletingName(name);
    try {
      await deleteServer.mutateAsync(name);
      toast.success(`Server "${name}" deleted.`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete server."
      );
    } finally {
      setDeletingName(null);
    }
  }

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Header */}
      <div className="mb-7 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Servers</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Manage your infrastructure hosts
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
        >
          <Plus size={16} aria-hidden="true" />
          Add Server
        </button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 size={28} className="animate-spin text-orange-400" aria-label="Loading servers" />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-5 text-red-400">
          <p className="font-medium">Failed to load servers</p>
          <p className="mt-1 text-sm text-red-400/70">
            {error instanceof Error ? error.message : "Unknown error"}
          </p>
        </div>
      )}

      {/* Empty */}
      {!isLoading && !isError && servers.length === 0 && (
        <EmptyState
          icon={<Server size={28} />}
          title="No servers yet"
          description="Add your first server to start deploying applications."
          action={{ label: "Add Server", onClick: () => setShowModal(true) }}
        />
      )}

      {/* Card Grid */}
      {servers.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {servers.map((server) => (
            <ServerCard
              key={server.id}
              server={server}
              onDelete={handleDelete}
              isDeleting={deletingName === server.name}
            />
          ))}
        </div>
      )}

      {/* Add Server Modal */}
      {showModal && (
        <Modal title="Add Server" onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {/* Name */}
            <div>
              <label
                htmlFor="server-name"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Name <span className="text-red-400">*</span>
              </label>
              <input
                id="server-name"
                name="name"
                type="text"
                required
                value={form.name}
                onChange={handleChange}
                placeholder="my-server"
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
            </div>

            {/* Host */}
            <div>
              <label
                htmlFor="server-host"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Host / IP <span className="text-red-400">*</span>
              </label>
              <input
                id="server-host"
                name="host"
                type="text"
                required
                value={form.host}
                onChange={handleChange}
                placeholder="203.0.113.1"
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
            </div>

            {/* User + Port */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="server-user"
                  className="mb-1.5 block text-xs font-medium text-zinc-300"
                >
                  SSH User <span className="text-red-400">*</span>
                </label>
                <input
                  id="server-user"
                  name="user"
                  type="text"
                  required
                  value={form.user}
                  onChange={handleChange}
                  placeholder="root"
                  className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                />
              </div>
              <div>
                <label
                  htmlFor="server-port"
                  className="mb-1.5 block text-xs font-medium text-zinc-300"
                >
                  SSH Port
                </label>
                <input
                  id="server-port"
                  name="port"
                  type="number"
                  min={1}
                  max={65535}
                  value={form.port ?? ""}
                  onChange={handleChange}
                  placeholder="22"
                  className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                />
              </div>
            </div>

            {/* SSH Key */}
            <div>
              <label
                htmlFor="server-key"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                SSH Key
              </label>
              <div className="flex gap-2">
                <select
                  id="server-key"
                  name="ssh_key_path"
                  value={form.ssh_key_path ?? ""}
                  onChange={handleChange}
                  className="flex-1 rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                >
                  <option value="">None (use SSH agent)</option>
                  {sshKeys.map((k) => (
                    <option key={k.id} value={`~/.infrakt/keys/${k.name}`}>
                      {k.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => setShowUploadKeyInline(true)}
                  title="Upload a key"
                  className="rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-400 transition-colors hover:bg-zinc-600 hover:text-orange-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
                >
                  <Upload size={16} aria-hidden="true" />
                </button>
              </div>
            </div>

            {/* Provider */}
            <div>
              <label
                htmlFor="server-provider"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Provider
              </label>
              <select
                id="server-provider"
                name="provider"
                value={form.provider ?? ""}
                onChange={handleChange}
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              >
                {PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {p === "" ? "Select provider (optional)" : p}
                  </option>
                ))}
              </select>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={addServer.isPending}
                className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
              >
                {addServer.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Add Server
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Upload SSH Key (inline from Add Server) */}
      {showUploadKeyInline && (
        <Modal title="Upload SSH Key" onClose={() => setShowUploadKeyInline(false)}>
          <form onSubmit={(e) => void handleInlineUpload(e)} className="space-y-4">
            <div>
              <label htmlFor="inline-key-name" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Key Name <span className="text-red-400">*</span>
              </label>
              <input
                id="inline-key-name"
                type="text"
                required
                value={inlineKeyName}
                onChange={(e) => setInlineKeyName(e.target.value)}
                placeholder="my-server-key"
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
            </div>
            <div>
              <label htmlFor="inline-key-file" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Private Key File <span className="text-red-400">*</span>
              </label>
              <input
                id="inline-key-file"
                type="file"
                required
                onChange={(e) => setInlineKeyFile(e.target.files?.[0] ?? null)}
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-600 file:px-3 file:py-1 file:text-sm file:text-zinc-300 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowUploadKeyInline(false)}
                className="rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!inlineKeyName.trim() || !inlineKeyFile || uploadKey.isPending}
                className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
              >
                {uploadKey.isPending && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}
                Upload
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
