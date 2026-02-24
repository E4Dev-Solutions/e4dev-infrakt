import { Server, Box, Database, Activity, Clock, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { useDashboard } from "@/hooks/useApi";
import StatusBadge from "@/components/StatusBadge";
import type { ReactNode } from "react";

interface StatCardProps {
  label: string;
  value: number | string;
  icon: ReactNode;
  accentColor: string;
  subLabel?: string;
}

function StatCard({ label, value, icon, accentColor, subLabel }: StatCardProps) {
  return (
    <div
      className={[
        "relative overflow-hidden rounded-xl border border-slate-700 bg-slate-800 p-5",
        `border-l-[3px] ${accentColor}`,
      ].join(" ")}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wider text-slate-400">
            {label}
          </p>
          <p className="text-3xl font-bold text-slate-100">{value}</p>
          {subLabel && (
            <p className="mt-1 text-xs text-slate-500">{subLabel}</p>
          )}
        </div>
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-700/60 text-slate-400">
          {icon}
        </div>
      </div>
    </div>
  );
}

function DeploymentStatusIcon({ status }: { status: string }) {
  const s = status.toLowerCase();
  if (s === "success") return <CheckCircle size={14} className="text-emerald-400" aria-hidden="true" />;
  if (s === "failed" || s === "error") return <XCircle size={14} className="text-red-400" aria-hidden="true" />;
  return <Loader2 size={14} className="animate-spin text-indigo-400" aria-hidden="true" />;
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function Dashboard() {
  const { data, isLoading, isError, error } = useDashboard();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 size={28} className="animate-spin text-indigo-400" aria-label="Loading dashboard" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-6 text-red-400">
        <p className="font-medium">Failed to load dashboard</p>
        <p className="mt-1 text-sm text-red-400/70">
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
      </div>
    );
  }

  const stats = data ?? {
    total_servers: 0,
    active_servers: 0,
    total_apps: 0,
    running_apps: 0,
    total_databases: 0,
    recent_deployments: [],
  };

  return (
    <div>
      {/* Page heading */}
      <div className="mb-7">
        <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">
          Platform overview and recent activity
        </p>
      </div>

      {/* Stat cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Servers"
          value={stats.total_servers}
          icon={<Server size={20} />}
          accentColor="border-l-indigo-500"
          subLabel={`${stats.active_servers} active`}
        />
        <StatCard
          label="Active Servers"
          value={stats.active_servers}
          icon={<Activity size={20} />}
          accentColor="border-l-emerald-500"
          subLabel={`of ${stats.total_servers} total`}
        />
        <StatCard
          label="Running Apps"
          value={stats.running_apps}
          icon={<Box size={20} />}
          accentColor="border-l-amber-500"
          subLabel={`of ${stats.total_apps} total`}
        />
        <StatCard
          label="Databases"
          value={stats.total_databases}
          icon={<Database size={20} />}
          accentColor="border-l-violet-500"
        />
      </div>

      {/* Recent Deployments */}
      <div className="rounded-xl border border-slate-700 bg-slate-800">
        <div className="flex items-center gap-2 border-b border-slate-700 px-5 py-4">
          <Clock size={16} className="text-slate-400" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-slate-200">
            Recent Deployments
          </h2>
        </div>

        {stats.recent_deployments.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">
            No deployments yet. Deploy an app to see activity here.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" role="table">
              <thead>
                <tr className="border-b border-slate-700/50">
                  <th
                    scope="col"
                    className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
                  >
                    App
                  </th>
                  <th
                    scope="col"
                    className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
                  >
                    Status
                  </th>
                  <th
                    scope="col"
                    className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
                  >
                    Commit
                  </th>
                  <th
                    scope="col"
                    className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
                  >
                    Started
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/30">
                {stats.recent_deployments.map((dep) => (
                  <tr
                    key={dep.id}
                    className="transition-colors hover:bg-slate-700/30"
                  >
                    <td className="px-5 py-3 font-medium text-slate-200">
                      {dep.app_name}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <DeploymentStatusIcon status={dep.status} />
                        <StatusBadge status={dep.status} />
                      </div>
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-slate-400">
                      {dep.commit_hash
                        ? dep.commit_hash.slice(0, 8)
                        : "—"}
                    </td>
                    <td className="px-5 py-3 text-slate-400">
                      {formatDate(dep.started_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
