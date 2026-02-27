import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft,
  Database,
  Trash2,
  Download,
  Upload,
  Clock,
  Loader2,
  BarChart2,
} from "lucide-react";
import {
  useDatabase,
  useDatabaseBackups,
  useBackupDatabase,
  useDeleteDatabase,
  useRestoreDatabase,
  useScheduleBackup,
  useUnscheduleBackup,
  useDatabaseStats,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";
import Modal from "@/components/Modal";
import EmptyState from "@/components/EmptyState";

// ─── Constants ────────────────────────────────────────────────────────────────

const DB_TYPE_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  mysql: "MySQL",
  redis: "Redis",
  mongo: "MongoDB",
};

type ActiveTab = "overview" | "backups";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

// ─── Tab Button ───────────────────────────────────────────────────────────────

function TabButton({
  id,
  label,
  isActive,
  onClick,
}: {
  id: ActiveTab;
  label: string;
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
        "border-b-2 px-4 py-3 text-sm font-medium transition-colors",
        isActive
          ? "border-orange-500 text-orange-400"
          : "border-transparent text-zinc-400 hover:border-zinc-500 hover:text-zinc-200",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

// ─── Info Card ────────────────────────────────────────────────────────────────

function InfoCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </p>
      <div className="text-sm text-zinc-200">{children}</div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function DatabaseDetail() {
  const { name = "" } = useParams<{ name: string }>();
  const decodedName = decodeURIComponent(name);
  const navigate = useNavigate();
  const toast = useToast();

  const { data: db, isLoading: dbLoading, isError: dbError } = useDatabase(decodedName);
  const { data: backups = [], isLoading: backupsLoading } = useDatabaseBackups(
    decodedName,
    db?.server_name,
  );
  const {
    data: stats,
    isFetching: statsFetching,
    refetch: refetchStats,
  } = useDatabaseStats(decodedName, db?.server_name, { enabled: false, staleTime: Infinity });

  const backupDatabase = useBackupDatabase();
  const deleteDatabase = useDeleteDatabase();
  const restoreDatabase = useRestoreDatabase();
  const scheduleBackup = useScheduleBackup();
  const unscheduleBackup = useUnscheduleBackup();

  const [activeTab, setActiveTab] = useState<ActiveTab>("overview");
  const [isBackingUp, setIsBackingUp] = useState(false);

  // Restore modal state
  const [showRestoreModal, setShowRestoreModal] = useState(false);
  const [restoreFilename, setRestoreFilename] = useState("");

  // Schedule modal state
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [cronExpression, setCronExpression] = useState("0 2 * * *");
  const [retentionDays, setRetentionDays] = useState(7);

  // ─── Handlers ───────────────────────────────────────────────────────────────

  async function handleBackup() {
    if (!db) return;
    setIsBackingUp(true);
    try {
      const result = await backupDatabase.mutateAsync({ name: decodedName, server: db.server_name });
      toast.success(`Backup created: ${result.filename}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create backup.");
    } finally {
      setIsBackingUp(false);
    }
  }

  async function handleDelete() {
    if (!db) return;
    if (!window.confirm(`Delete database "${decodedName}"? This cannot be undone.`)) return;
    try {
      await deleteDatabase.mutateAsync({ name: decodedName, server: db.server_name });
      toast.success(`Database "${decodedName}" deleted.`);
      void navigate("/databases");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete database.");
    }
  }

  function openRestoreModal(filename?: string) {
    setRestoreFilename(filename ?? "");
    setShowRestoreModal(true);
  }

  function closeRestoreModal() {
    setShowRestoreModal(false);
    setRestoreFilename("");
  }

  async function handleRestore(e: React.FormEvent) {
    e.preventDefault();
    if (!db || !restoreFilename) return;
    try {
      await restoreDatabase.mutateAsync({
        name: decodedName,
        filename: restoreFilename,
        serverName: db.server_name,
      });
      toast.success(`Database "${decodedName}" restored from "${restoreFilename}".`);
      closeRestoreModal();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to restore database.");
    }
  }

  function openScheduleModal() {
    setCronExpression(db?.backup_schedule ?? "0 2 * * *");
    setRetentionDays(7);
    setShowScheduleModal(true);
  }

  function closeScheduleModal() {
    setShowScheduleModal(false);
    setCronExpression("0 2 * * *");
    setRetentionDays(7);
  }

  async function handleSetSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!db) return;
    try {
      await scheduleBackup.mutateAsync({
        name: decodedName,
        cronExpression,
        retentionDays,
        server: db.server_name,
      });
      toast.success(`Backup schedule set for "${decodedName}".`);
      closeScheduleModal();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to set backup schedule.");
    }
  }

  async function handleUnschedule() {
    if (!db) return;
    try {
      await unscheduleBackup.mutateAsync({ name: decodedName, server: db.server_name });
      toast.success(`Backup schedule removed for "${decodedName}".`);
      closeScheduleModal();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to remove backup schedule.");
    }
  }

  // ─── Loading / Error states ──────────────────────────────────────────────────

  if (dbLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={28} className="animate-spin text-orange-400" aria-label="Loading database" />
      </div>
    );
  }

  if (dbError || !db) {
    return (
      <div>
        <Link
          to="/databases"
          className="mb-5 inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Back to Databases
        </Link>
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-5 text-red-400">
          <p className="font-medium">Database not found</p>
          <p className="mt-1 text-sm text-red-400/70">
            The database &quot;{decodedName}&quot; could not be loaded.
          </p>
        </div>
      </div>
    );
  }

  const typeLabel = DB_TYPE_LABELS[db.db_type] ?? db.db_type;

  const buildConnectionString = (): string => {
    const host = db.server_name;
    const port = db.port ?? "";
    const n = decodedName;
    switch (db.db_type) {
      case "postgres":
        return `postgresql://${n}:<password>@${host}:${port}/${n}`;
      case "mysql":
        return `mysql://${n}:<password>@${host}:${port}/${n}`;
      case "redis":
        return `redis://:<password>@${host}:${port}`;
      case "mongo":
        return `mongodb://${n}:<password>@${host}:${port}/${n}`;
      default:
        return `${db.db_type}://${n}:<password>@${host}:${port}/${n}`;
    }
  };

  type StatKey = "disk_size" | "active_connections" | "version" | "uptime";

  const getStatKeys = (): StatKey[] => {
    switch (db.db_type) {
      case "postgres":
      case "mysql":
        return ["disk_size", "active_connections", "version", "uptime"];
      case "redis":
        return ["version", "uptime"];
      case "mongo":
        return ["disk_size", "version"];
      default:
        return ["disk_size", "active_connections", "version", "uptime"];
    }
  };

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Back link */}
      <Link
        to="/databases"
        className="mb-5 inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        Back to Databases
      </Link>

      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-700">
            <Database size={22} className="text-orange-400" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">{decodedName}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center rounded-md bg-zinc-700 px-2.5 py-0.5 text-xs font-medium text-zinc-300">
                {typeLabel}
              </span>
              <StatusBadge status={db.status} />
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => void handleBackup()}
            disabled={isBackingUp}
            className="flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
            aria-label="Create backup"
          >
            {isBackingUp ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Download size={14} aria-hidden="true" />
            )}
            Backup
          </button>
          <button
            onClick={openScheduleModal}
            className={[
              "flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500",
              db.backup_schedule
                ? "border-orange-500/40 bg-orange-500/10 text-orange-300 hover:bg-orange-500/20"
                : "border-zinc-600 bg-zinc-700 text-zinc-200 hover:bg-zinc-600",
            ].join(" ")}
            aria-label="Schedule backups"
          >
            <Clock size={14} aria-hidden="true" />
            Schedule
          </button>
          <button
            onClick={() => void handleDelete()}
            disabled={deleteDatabase.isPending}
            className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500 disabled:opacity-50"
            aria-label="Delete database"
          >
            {deleteDatabase.isPending ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Trash2 size={14} aria-hidden="true" />
            )}
            Delete
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="rounded-xl border border-zinc-700 bg-zinc-800">
        {/* Tab list */}
        <div role="tablist" aria-label="Database details" className="flex border-b border-zinc-700">
          <TabButton
            id="overview"
            label="Overview"
            isActive={activeTab === "overview"}
            onClick={setActiveTab}
          />
          <TabButton
            id="backups"
            label="Backups"
            isActive={activeTab === "backups"}
            onClick={setActiveTab}
          />
        </div>

        {/* Tab panels */}
        <div className="p-5">
          {/* Overview */}
          <div
            id="tabpanel-overview"
            role="tabpanel"
            aria-label="Overview"
            hidden={activeTab !== "overview"}
          >
            {activeTab === "overview" && (
              <div className="space-y-6">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <InfoCard label="Type">
                    {typeLabel}
                  </InfoCard>
                  <InfoCard label="Server">
                    {db.server_name}
                  </InfoCard>
                  <InfoCard label="Port">
                    {db.port ? (
                      <span className="font-mono">{db.port}</span>
                    ) : (
                      <span className="text-zinc-500">—</span>
                    )}
                  </InfoCard>
                  <InfoCard label="Status">
                    <StatusBadge status={db.status} />
                  </InfoCard>
                  <InfoCard label="Created">
                    {db.created_at ? formatDate(db.created_at) : <span className="text-zinc-500">—</span>}
                  </InfoCard>
                  <InfoCard label="Backup Schedule">
                    {db.backup_schedule ? (
                      <span className="font-mono text-orange-300">{db.backup_schedule}</span>
                    ) : (
                      <span className="text-zinc-500">None</span>
                    )}
                  </InfoCard>
                </div>

                {/* Connection String */}
                <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
                    Connection String
                  </p>
                  <p className="break-all font-mono text-xs text-zinc-300">
                    {buildConnectionString()}
                  </p>
                  <p className="mt-1.5 text-xs text-zinc-500">
                    Replace <span className="font-mono text-zinc-400">&lt;password&gt;</span> with the password shown when the database was created.
                  </p>
                </div>

                {/* Stats section */}
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-zinc-200">Live Stats</h3>
                    <button
                      onClick={() => void refetchStats()}
                      disabled={statsFetching}
                      className="flex items-center gap-1.5 rounded-md border border-zinc-600 bg-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
                    >
                      {statsFetching ? (
                        <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                      ) : (
                        <BarChart2 size={12} aria-hidden="true" />
                      )}
                      {statsFetching ? "Fetching..." : "Fetch Stats"}
                    </button>
                  </div>

                  {!stats && !statsFetching && (
                    <p className="py-6 text-center text-sm text-zinc-500">
                      Click &quot;Fetch Stats&quot; to query live database metrics from the server.
                    </p>
                  )}

                  {statsFetching && (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 size={20} className="animate-spin text-zinc-500" aria-label="Fetching stats" />
                    </div>
                  )}

                  {stats && !statsFetching && (
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      {getStatKeys().map((key) => {
                        const value = stats[key];
                        if (value == null) return null;
                        const labels: Record<string, string> = {
                          disk_size: "Disk Size",
                          active_connections: "Active Connections",
                          version: "Version",
                          uptime: "Uptime",
                        };
                        return (
                          <div key={key} className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
                            <p className="mb-1 text-xs font-medium uppercase tracking-wider text-zinc-500">
                              {labels[key] ?? key}
                            </p>
                            <p className="font-mono text-sm text-zinc-200">{String(value)}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Backups */}
          <div
            id="tabpanel-backups"
            role="tabpanel"
            aria-label="Backups"
            hidden={activeTab !== "backups"}
          >
            {activeTab === "backups" && (
              <div className="space-y-4">
                {/* Backups header row */}
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-zinc-200">Backups</h2>
                  <button
                    onClick={() => void handleBackup()}
                    disabled={isBackingUp}
                    className="flex items-center gap-2 rounded-lg bg-orange-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
                  >
                    {isBackingUp ? (
                      <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                    ) : (
                      <Download size={12} aria-hidden="true" />
                    )}
                    Create Backup
                  </button>
                </div>

                {/* Loading */}
                {backupsLoading && (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 size={20} className="animate-spin text-zinc-500" aria-label="Loading backups" />
                  </div>
                )}

                {/* Empty */}
                {!backupsLoading && backups.length === 0 && (
                  <EmptyState
                    icon={<Download size={24} />}
                    title="No backups yet"
                    description="Create a backup to preserve the current state of this database."
                    action={{
                      label: "Create Backup",
                      onClick: () => void handleBackup(),
                    }}
                  />
                )}

                {/* Backup table */}
                {!backupsLoading && backups.length > 0 && (
                  <div className="overflow-hidden rounded-lg border border-zinc-700">
                    <table className="w-full text-sm" role="table">
                      <thead>
                        <tr className="border-b border-zinc-700 bg-zinc-800/60">
                          {["Filename", "Size", "Date", "Actions"].map((h) => (
                            <th
                              key={h}
                              scope="col"
                              className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400"
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-700/40">
                        {backups.map((backup) => (
                          <tr
                            key={backup.filename}
                            className="bg-zinc-800/30 transition-colors hover:bg-zinc-800/70"
                          >
                            <td className="px-4 py-3 font-mono text-xs text-zinc-200">
                              {backup.filename}
                            </td>
                            <td className="px-4 py-3 text-xs text-zinc-400">
                              {backup.size}
                            </td>
                            <td className="px-4 py-3 text-xs text-zinc-400">
                              {formatDate(backup.modified)}
                            </td>
                            <td className="px-4 py-3">
                              <button
                                onClick={() => openRestoreModal(backup.filename)}
                                className="flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-400 transition-colors hover:bg-amber-500/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
                                aria-label={`Restore from ${backup.filename}`}
                              >
                                <Upload size={11} aria-hidden="true" />
                                Restore
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Restore Modal */}
      {showRestoreModal && (
        <Modal title="Restore Database" onClose={closeRestoreModal}>
          <form onSubmit={(e) => void handleRestore(e)} className="space-y-4" noValidate>
            <p className="text-sm text-zinc-400">
              Restore{" "}
              <span className="font-medium text-zinc-200">{decodedName}</span> from a
              backup file on the server.
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
                onClick={closeRestoreModal}
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
      {showScheduleModal && (
        <Modal title="Schedule Backups" onClose={closeScheduleModal}>
          <form onSubmit={(e) => void handleSetSchedule(e)} className="space-y-4" noValidate>
            <p className="text-sm text-zinc-400">
              Configure automated backups for{" "}
              <span className="font-medium text-zinc-200">{decodedName}</span>.
            </p>

            {/* Current schedule indicator */}
            {db.backup_schedule && (
              <div className="flex items-center justify-between rounded-lg border border-orange-500/30 bg-orange-500/10 px-3 py-2.5">
                <div className="flex items-center gap-2 text-sm text-orange-300">
                  <Clock size={14} aria-hidden="true" />
                  <span>
                    Current schedule:{" "}
                    <span className="font-mono font-medium">{db.backup_schedule}</span>
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
    </div>
  );
}
