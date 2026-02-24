import { useState } from "react";
import {
  Globe,
  Plus,
  Trash2,
  RefreshCw,
  Loader2,
} from "lucide-react";
import {
  useServers,
  useProxyDomains,
  useAddProxyRoute,
  useRemoveProxyRoute,
  useReloadProxy,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import Modal from "@/components/Modal";
import EmptyState from "@/components/EmptyState";

const defaultForm = { domain: "", port: 3000 };

export default function ProxyDomains() {
  const { data: servers = [] } = useServers();
  const toast = useToast();

  const [selectedServer, setSelectedServer] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState(defaultForm);
  const [deletingDomain, setDeletingDomain] = useState<string | null>(null);

  const { data: domains = [], isLoading } = useProxyDomains(selectedServer);
  const addRoute = useAddProxyRoute();
  const removeRoute = useRemoveProxyRoute();
  const reloadProxy = useReloadProxy();

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: name === "port" ? (value === "" ? 0 : Number(value)) : value,
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await addRoute.mutateAsync({
        server_name: selectedServer,
        domain: form.domain,
        port: form.port,
      });
      toast.success(`Route added: ${form.domain} -> :${form.port}`);
      setShowModal(false);
      setForm(defaultForm);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add route.");
    }
  }

  async function handleDelete(domain: string) {
    if (!window.confirm(`Remove proxy route for "${domain}"?`)) return;
    setDeletingDomain(domain);
    try {
      await removeRoute.mutateAsync({ server: selectedServer, domain });
      toast.success(`Route for "${domain}" removed.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to remove route.");
    } finally {
      setDeletingDomain(null);
    }
  }

  async function handleReload() {
    try {
      await reloadProxy.mutateAsync(selectedServer);
      toast.success("Caddy reloaded.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to reload Caddy.");
    }
  }

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Header */}
      <div className="mb-7 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Proxy Domains</h1>
          <p className="mt-1 text-sm text-slate-400">
            Manage Caddy reverse proxy routes
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selectedServer && (
            <>
              <button
                onClick={handleReload}
                disabled={reloadProxy.isPending}
                className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
              >
                {reloadProxy.isPending ? (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                ) : (
                  <RefreshCw size={14} aria-hidden="true" />
                )}
                Reload Caddy
              </button>
              <button
                onClick={() => setShowModal(true)}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
              >
                <Plus size={16} aria-hidden="true" />
                Add Route
              </button>
            </>
          )}
        </div>
      </div>

      {/* Server selector */}
      <div className="mb-6">
        <label
          htmlFor="proxy-server"
          className="mb-1.5 block text-xs font-medium text-slate-300"
        >
          Server
        </label>
        <select
          id="proxy-server"
          value={selectedServer}
          onChange={(e) => setSelectedServer(e.target.value)}
          className="w-full max-w-xs rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
        >
          <option value="">Select a server</option>
          {servers.map((s) => (
            <option key={s.id} value={s.name}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      {/* No server selected */}
      {!selectedServer && (
        <EmptyState
          icon={<Globe size={28} />}
          title="Select a server"
          description="Choose a server above to view and manage its proxy domains."
        />
      )}

      {/* Loading */}
      {selectedServer && isLoading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 size={28} className="animate-spin text-indigo-400" aria-label="Loading domains" />
        </div>
      )}

      {/* Empty */}
      {selectedServer && !isLoading && domains.length === 0 && (
        <EmptyState
          icon={<Globe size={28} />}
          title="No proxy domains"
          description="No reverse proxy routes configured on this server yet."
          action={{ label: "Add Route", onClick: () => setShowModal(true) }}
        />
      )}

      {/* Table */}
      {selectedServer && domains.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-700">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-800/60">
                {["Domain", "Port", "Actions"].map((h) => (
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
              {domains.map((d) => (
                <tr
                  key={d.domain}
                  className="bg-slate-800/30 transition-colors hover:bg-slate-800/70"
                >
                  <td className="px-4 py-3 font-medium text-slate-200">
                    {d.domain}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">
                    :{d.port}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleDelete(d.domain)}
                      disabled={deletingDomain === d.domain}
                      title="Remove route"
                      className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                      aria-label={`Remove ${d.domain}`}
                    >
                      {deletingDomain === d.domain ? (
                        <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                      ) : (
                        <Trash2 size={15} aria-hidden="true" />
                      )}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Route Modal */}
      {showModal && (
        <Modal title="Add Proxy Route" onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label
                htmlFor="route-domain"
                className="mb-1.5 block text-xs font-medium text-slate-300"
              >
                Domain <span className="text-red-400">*</span>
              </label>
              <input
                id="route-domain"
                name="domain"
                type="text"
                required
                value={form.domain}
                onChange={handleChange}
                placeholder="app.example.com"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            <div>
              <label
                htmlFor="route-port"
                className="mb-1.5 block text-xs font-medium text-slate-300"
              >
                Target Port <span className="text-red-400">*</span>
              </label>
              <input
                id="route-port"
                name="port"
                type="number"
                required
                min={1}
                max={65535}
                value={form.port}
                onChange={handleChange}
                placeholder="3000"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={addRoute.isPending || !form.domain.trim()}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
              >
                {addRoute.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Add Route
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
