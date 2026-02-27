import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Trash2,
  Settings,
  Loader2,
  Server,
  ChevronRight,
} from "lucide-react";
import {
  useServers,
  useAddServer,
  useDeleteServer,
  useProvisionServer,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";
import Modal from "@/components/Modal";
import EmptyState from "@/components/EmptyState";
import type { CreateServerInput } from "@/api/client";

const PROVIDERS = ["", "hetzner", "digitalocean", "linode", "vultr", "aws", "gcp", "azure", "bare-metal", "other"];

const defaultForm: CreateServerInput = {
  name: "",
  host: "",
  user: "root",
  port: 22,
  ssh_key_path: "",
  provider: "",
};

export default function Servers() {
  const { data: servers = [], isLoading, isError, error } = useServers();
  const addServer = useAddServer();
  const deleteServer = useDeleteServer();
  const provisionServer = useProvisionServer();
  const toast = useToast();

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

  async function handleProvision(name: string) {
    try {
      await provisionServer.mutateAsync(name);
      toast.success(`Provisioning started for "${name}".`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to provision server."
      );
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

      {/* Table */}
      {servers.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-zinc-700">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-zinc-700 bg-zinc-800/60">
                {["Name", "Host", "Status", "Provider", "Tags", "Apps", "Actions"].map(
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
              {servers.map((server) => (
                <tr
                  key={server.id}
                  className="bg-zinc-800/30 transition-colors hover:bg-zinc-800/70"
                >
                  <td className="px-4 py-3">
                    <Link
                      to={`/servers/${encodeURIComponent(server.name)}`}
                      className="flex items-center gap-1.5 font-medium text-orange-400 hover:text-orange-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
                    >
                      {server.name}
                      <ChevronRight size={14} aria-hidden="true" />
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-zinc-300">
                    {server.user}@{server.host}:{server.port}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={server.status} />
                  </td>
                  <td className="px-4 py-3 text-zinc-400">
                    {server.provider ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(server.tags ?? []).length > 0 ? (
                        server.tags!.map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex items-center rounded-md bg-zinc-700 px-2 py-0.5 text-xs font-medium text-zinc-300"
                          >
                            {tag}
                          </span>
                        ))
                      ) : (
                        <span className="text-zinc-500">—</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-zinc-300">
                    {server.app_count}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleProvision(server.name)}
                        disabled={provisionServer.isPending}
                        title="Provision server"
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-emerald-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
                        aria-label={`Provision ${server.name}`}
                      >
                        <Settings size={15} aria-hidden="true" />
                      </button>
                      <button
                        onClick={() => handleDelete(server.name)}
                        disabled={deletingName === server.name}
                        title="Delete server"
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
                        aria-label={`Delete ${server.name}`}
                      >
                        {deletingName === server.name ? (
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

            {/* SSH Key Path */}
            <div>
              <label
                htmlFor="server-key"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                SSH Key Path
              </label>
              <input
                id="server-key"
                name="ssh_key_path"
                type="text"
                value={form.ssh_key_path ?? ""}
                onChange={handleChange}
                placeholder="~/.ssh/id_rsa"
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
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
    </div>
  );
}
