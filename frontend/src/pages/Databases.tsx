import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Trash2,
  Database,
  Loader2,
  Download,
  Upload,
  Clock,
} from "lucide-react";
import {
  useDatabases,
  useServers,
  useCreateDatabase,
  useDeleteDatabase,
  useBackupDatabase,
  useRestoreDatabase,
  useScheduleBackup,
  useUnscheduleBackup,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";
import Modal from "@/components/Modal";
import EmptyState from "@/components/EmptyState";
import type { CreateDatabaseInput, DbType } from "@/api/client";

const DB_TYPES: { value: DbType; label: string }[] = [
  { value: "postgres", label: "PostgreSQL" },
  { value: "mysql", label: "MySQL" },
  { value: "redis", label: "Redis" },
  { value: "mongo", label: "MongoDB" },
];

const defaultForm: CreateDatabaseInput = {
  server_name: "",
  name: "",
  db_type: "postgres",
  version: "",
};

export default function Databases() {
  const { data: databases = [], isLoading, isError, error } = useDatabases();
  const { data: servers = [] } = useServers();

  const createDatabase = useCreateDatabase();
  const deleteDatabase = useDeleteDatabase();
  const backupDatabase = useBackupDatabase();
  const restoreDatabase = useRestoreDatabase();
  const scheduleBackup = useScheduleBackup();
  const unscheduleBackup = useUnscheduleBackup();
  const toast = useToast();

  const [showModal, setShowModal] = useState(false);
  const [showRestoreModal, setShowRestoreModal] = useState<{ name: string; server: string } | null>(null);
  const [restoreFilename, setRestoreFilename] = useState("");
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [scheduleDb, setScheduleDb] = useState<{ name: string; server: string; currentSchedule?: string | null } | null>(null);
  const [cronExpression, setCronExpression] = useState("0 2 * * *");
  const [retentionDays, setRetentionDays] = useState(7);
  const [form, setForm] = useState<CreateDatabaseInput>(defaultForm);
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const [backingUpName, setBackingUpName] = useState<string | null>(null);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const payload: CreateDatabaseInput = {
        ...form,
        version: form.version || undefined,
      };
      await createDatabase.mutateAsync(payload);
      toast.success(`Database "${form.name}" created.`);
      setShowModal(false);
      setForm(defaultForm);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create database."
      );
    }
  }

  async function handleDelete(name: string, serverName: string) {
    if (!window.confirm(`Delete database "${name}"? This cannot be undone.`)) return;
    setDeletingName(name);
    try {
      await deleteDatabase.mutateAsync({ name, server: serverName });
      toast.success(`Database "${name}" deleted.`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete database."
      );
    } finally {
      setDeletingName(null);
    }
  }

  async function handleBackup(name: string, serverName: string) {
    setBackingUpName(name);
    try {
      const result = await backupDatabase.mutateAsync({ name, server: serverName });
      toast.success(`Backup created: ${result.filename}`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create backup."
      );
    } finally {
      setBackingUpName(null);
    }
  }

  async function handleRestore(e: React.FormEvent) {
    e.preventDefault();
    if (!showRestoreModal || !restoreFilename) return;
    try {
      await restoreDatabase.mutateAsync({
        name: showRestoreModal.name,
        filename: restoreFilename,
        serverName: showRestoreModal.server,
      });
      toast.success(`Database "${showRestoreModal.name}" restored.`);
      setShowRestoreModal(null);
      setRestoreFilename("");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to restore database."
      );
    }
  }

  function openScheduleModal(db: { name: string; server_name: string; backup_schedule?: string | null }) {
    setScheduleDb({ name: db.name, server: db.server_name, currentSchedule: db.backup_schedule });
    setCronExpression(db.backup_schedule ?? "0 2 * * *");
    setRetentionDays(7);
    setShowScheduleModal(true);
  }

  function closeScheduleModal() {
    setShowScheduleModal(false);
    setScheduleDb(null);
    setCronExpression("0 2 * * *");
    setRetentionDays(7);
  }

  async function handleSetSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!scheduleDb) return;
    try {
      await scheduleBackup.mutateAsync({
        name: scheduleDb.name,
        cronExpression,
        retentionDays,
        server: scheduleDb.server,
      });
      toast.success(`Backup schedule set for "${scheduleDb.name}".`);
      closeScheduleModal();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to set backup schedule.");
    }
  }

  async function handleUnschedule() {
    if (!scheduleDb) return;
    try {
      await unscheduleBackup.mutateAsync({ name: scheduleDb.name, server: scheduleDb.server });
      toast.success(`Backup schedule removed for "${scheduleDb.name}".`);
      closeScheduleModal();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to remove backup schedule.");
    }
  }

  function getDbTypeLabel(type: string): string {
    return DB_TYPES.find((d) => d.value === type)?.label ?? type;
  }

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Header */}
      <div className="mb-7 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Databases</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Manage database instances across your servers
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
        >
          <Plus size={16} aria-hidden="true" />
          Create Database
        </button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 size={28} className="animate-spin text-orange-400" aria-label="Loading databases" />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-5 text-red-400">
          <p className="font-medium">Failed to load databases</p>
          <p className="mt-1 text-sm text-red-400/70">
            {error instanceof Error ? error.message : "Unknown error"}
          </p>
        </div>
      )}

      {/* Empty */}
      {!isLoading && !isError && databases.length === 0 && (
        <EmptyState
          icon={<Database size={28} />}
          title="No databases yet"
          description="Create a database to provision a managed instance on one of your servers."
          action={{
            label: "Create Database",
            onClick: () => setShowModal(true),
          }}
        />
      )}

      {/* Table */}
      {databases.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-zinc-700">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-zinc-700 bg-zinc-800/60">
                {["Name", "Server", "Type", "Port", "Status", "Actions"].map(
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
              {databases.map((db) => (
                <tr
                  key={db.id}
                  className="bg-zinc-800/30 transition-colors hover:bg-zinc-800/70"
                >
                  {/* Name */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Database
                        size={14}
                        className="shrink-0 text-zinc-500"
                        aria-hidden="true"
                      />
                      <Link
                        to={`/databases/${encodeURIComponent(db.name)}`}
                        className="font-medium text-zinc-200 hover:text-orange-400 transition-colors"
                      >
                        {db.name}
                      </Link>
                    </div>
                  </td>
                  {/* Server */}
                  <td className="px-4 py-3 text-zinc-300">
                    {db.server_name}
                  </td>
                  {/* Type */}
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center rounded-md bg-zinc-700 px-2.5 py-0.5 text-xs font-medium text-zinc-300">
                      {getDbTypeLabel(db.db_type)}
                    </span>
                  </td>
                  {/* Port */}
                  <td className="px-4 py-3 font-mono text-xs text-zinc-400">
                    {db.port ?? "—"}
                  </td>
                  {/* Status */}
                  <td className="px-4 py-3">
                    <StatusBadge status={db.status} />
                  </td>
                  {/* Actions */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleBackup(db.name, db.server_name)}
                        disabled={backingUpName === db.name}
                        title="Backup database"
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-orange-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
                        aria-label={`Backup ${db.name}`}
                      >
                        {backingUpName === db.name ? (
                          <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                        ) : (
                          <Download size={15} aria-hidden="true" />
                        )}
                      </button>
                      <button
                        onClick={() => setShowRestoreModal({ name: db.name, server: db.server_name })}
                        title="Restore database"
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-amber-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
                        aria-label={`Restore ${db.name}`}
                      >
                        <Upload size={15} aria-hidden="true" />
                      </button>
                      <button
                        onClick={() => openScheduleModal(db)}
                        title={db.backup_schedule ? `Edit schedule (${db.backup_schedule})` : "Schedule backups"}
                        className={[
                          "rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500",
                          db.backup_schedule ? "text-orange-400 hover:text-orange-300" : "hover:text-orange-400",
                        ].join(" ")}
                        aria-label={`Schedule backups for ${db.name}`}
                        aria-pressed={Boolean(db.backup_schedule)}
                      >
                        <Clock size={15} aria-hidden="true" />
                      </button>
                      <button
                        onClick={() => handleDelete(db.name, db.server_name)}
                        disabled={deletingName === db.name}
                        title="Delete database"
                        className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
                        aria-label={`Delete ${db.name}`}
                      >
                        {deletingName === db.name ? (
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

      {/* Create Database Modal */}
      {/* Restore Database Modal */}
      {showRestoreModal && (
        <Modal
          title="Restore Database"
          onClose={() => { setShowRestoreModal(null); setRestoreFilename(""); }}
        >
          <form onSubmit={handleRestore} className="space-y-4" noValidate>
            <p className="text-sm text-zinc-400">
              Restore <span className="font-medium text-zinc-200">{showRestoreModal.name}</span> from
              a backup file on the server.
            </p>
            <div>
              <label
                htmlFor="restore-filename"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Backup Filename <span className="text-red-400">*</span>
              </label>
              <input
                id="restore-filename"
                type="text"
                required
                value={restoreFilename}
                onChange={(e) => setRestoreFilename(e.target.value)}
                placeholder="main-pg_20260224_120000.sql.gz"
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
              <p className="mt-1 text-xs text-zinc-500">
                File must exist in /opt/infrakt/backups/ on the server.
              </p>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => { setShowRestoreModal(null); setRestoreFilename(""); }}
                className="rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={restoreDatabase.isPending || !restoreFilename}
                className="flex items-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
              >
                {restoreDatabase.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Restore
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Schedule Backup Modal */}
      {showScheduleModal && scheduleDb && (
        <Modal
          title="Schedule Backups"
          onClose={closeScheduleModal}
        >
          <form onSubmit={handleSetSchedule} className="space-y-4" noValidate>
            <p className="text-sm text-zinc-400">
              Configure automated backups for{" "}
              <span className="font-medium text-zinc-200">{scheduleDb.name}</span>.
            </p>

            {/* Current schedule indicator */}
            {scheduleDb.currentSchedule && (
              <div className="flex items-center justify-between rounded-lg border border-orange-500/30 bg-orange-500/10 px-3 py-2.5">
                <div className="flex items-center gap-2 text-sm text-orange-300">
                  <Clock size={14} aria-hidden="true" />
                  <span>
                    Current schedule:{" "}
                    <span className="font-mono font-medium">{scheduleDb.currentSchedule}</span>
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => void handleUnschedule()}
                  disabled={unscheduleBackup.isPending}
                  className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/10 hover:text-red-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
                >
                  {unscheduleBackup.isPending && (
                    <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                  )}
                  Remove Schedule
                </button>
              </div>
            )}

            {/* Cron expression */}
            <div>
              <label
                htmlFor="schedule-cron"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Cron Expression <span className="text-red-400">*</span>
              </label>
              <input
                id="schedule-cron"
                type="text"
                required
                value={cronExpression}
                onChange={(e) => setCronExpression(e.target.value)}
                placeholder="0 2 * * *"
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 font-mono text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
              <p className="mt-1 text-xs text-zinc-500">
                Standard 5-field cron syntax (minute hour day month weekday).
              </p>
            </div>

            {/* Preset buttons */}
            <div>
              <p className="mb-2 text-xs font-medium text-zinc-400">Presets</p>
              <div className="flex flex-wrap gap-2">
                {[
                  { label: "Daily 2am", value: "0 2 * * *" },
                  { label: "Every 12h", value: "0 */12 * * *" },
                  { label: "Weekly Sun", value: "0 2 * * 0" },
                ].map(({ label, value }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setCronExpression(value)}
                    className={[
                      "rounded-md border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500",
                      cronExpression === value
                        ? "border-orange-500 bg-orange-500/20 text-orange-300"
                        : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:bg-zinc-600",
                    ].join(" ")}
                  >
                    {label}
                    <span className="ml-1.5 font-mono text-zinc-400">{value}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Retention days */}
            <div>
              <label
                htmlFor="schedule-retention"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Retention Days
              </label>
              <input
                id="schedule-retention"
                type="number"
                min={1}
                max={365}
                value={retentionDays}
                onChange={(e) => setRetentionDays(Math.max(1, Number(e.target.value)))}
                className="w-32 rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
              <p className="mt-1 text-xs text-zinc-500">
                Backups older than this many days will be automatically removed.
              </p>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={closeScheduleModal}
                className="rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={scheduleBackup.isPending || !cronExpression.trim()}
                className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
              >
                {scheduleBackup.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Set Schedule
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Create Database Modal */}
      {showModal && (
        <Modal
          title="Create Database"
          onClose={() => setShowModal(false)}
        >
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {/* Server */}
            <div>
              <label
                htmlFor="db-server"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Server <span className="text-red-400">*</span>
              </label>
              <select
                id="db-server"
                name="server_name"
                required
                value={form.server_name}
                onChange={handleChange}
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              >
                <option value="">Select a server</option>
                {servers.map((s) => (
                  <option key={s.id} value={s.name}>
                    {s.name} ({s.host})
                  </option>
                ))}
              </select>
            </div>

            {/* Name */}
            <div>
              <label
                htmlFor="db-name"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Database Name <span className="text-red-400">*</span>
              </label>
              <input
                id="db-name"
                name="name"
                type="text"
                required
                value={form.name}
                onChange={handleChange}
                placeholder="my-database"
                className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              />
            </div>

            {/* Type + Version */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="db-type"
                  className="mb-1.5 block text-xs font-medium text-zinc-300"
                >
                  Database Type <span className="text-red-400">*</span>
                </label>
                <select
                  id="db-type"
                  name="db_type"
                  required
                  value={form.db_type}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                >
                  {DB_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="db-version"
                  className="mb-1.5 block text-xs font-medium text-zinc-300"
                >
                  Version
                </label>
                <input
                  id="db-version"
                  name="version"
                  type="text"
                  value={form.version ?? ""}
                  onChange={handleChange}
                  placeholder="15 / 8.0 / 7.2 / 7"
                  className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                />
              </div>
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
                disabled={createDatabase.isPending}
                className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
              >
                {createDatabase.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Create Database
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
