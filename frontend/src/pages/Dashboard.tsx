import {
  Server,
  Box,
  Database,
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Rocket,
  ArrowUpRight,
  Timer,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useDashboard } from "@/hooks/useApi";
import StatusBadge from "@/components/StatusBadge";
import type { RecentDeployment } from "@/api/client";
import type { ReactNode } from "react";

/* ── Stat Card ─────────────────────────────────────────── */

interface StatCardProps {
  label: string;
  value: number | string;
  icon: ReactNode;
  accent: string; // tailwind color token, e.g. "indigo"
  subLabel?: string;
  href?: string;
}

function StatCard({ label, value, icon, accent, subLabel, href }: StatCardProps) {
  const accentMap: Record<string, { border: string; bg: string; text: string; glow: string }> = {
    indigo: {
      border: "border-indigo-500/40",
      bg: "bg-indigo-500/10",
      text: "text-indigo-400",
      glow: "shadow-indigo-500/5",
    },
    emerald: {
      border: "border-emerald-500/40",
      bg: "bg-emerald-500/10",
      text: "text-emerald-400",
      glow: "shadow-emerald-500/5",
    },
    amber: {
      border: "border-amber-500/40",
      bg: "bg-amber-500/10",
      text: "text-amber-400",
      glow: "shadow-amber-500/5",
    },
    violet: {
      border: "border-violet-500/40",
      bg: "bg-violet-500/10",
      text: "text-violet-400",
      glow: "shadow-violet-500/5",
    },
  };

  const a = accentMap[accent] ?? accentMap.indigo;

  const card = (
    <div
      className={[
        "group relative overflow-hidden rounded-xl border bg-slate-800/80 p-5 transition-all duration-200",
        a.border,
        href ? "hover:bg-slate-800 hover:shadow-lg cursor-pointer" : "",
        a.glow,
      ].join(" ")}
    >
      {/* Subtle gradient overlay */}
      <div className={`absolute inset-0 opacity-[0.03] ${a.bg}`} />

      <div className="relative flex items-start justify-between">
        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
            {label}
          </p>
          <p className="text-3xl font-bold tabular-nums text-slate-100">{value}</p>
          {subLabel && (
            <p className="mt-1.5 text-xs text-slate-500">{subLabel}</p>
          )}
        </div>
        <div
          className={[
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
            a.bg,
            a.text,
          ].join(" ")}
        >
          {icon}
        </div>
      </div>

      {href && (
        <ArrowUpRight
          size={14}
          className="absolute right-3 top-3 text-slate-600 opacity-0 transition-opacity group-hover:opacity-100"
        />
      )}
    </div>
  );

  if (href) {
    return <Link to={href}>{card}</Link>;
  }
  return card;
}

/* ── Deployment Row ────────────────────────────────────── */

function DeploymentStatusIcon({ status }: { status: string }) {
  const s = status.toLowerCase();
  if (s === "success")
    return <CheckCircle2 size={15} className="text-emerald-400" />;
  if (s === "failed" || s === "error")
    return <XCircle size={15} className="text-red-400" />;
  return <Loader2 size={15} className="animate-spin text-indigo-400" />;
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

function formatDuration(start: string, end?: string): string {
  if (!end) return "...";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return "<1s";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem > 0 ? `${m}m ${rem}s` : `${m}m`;
}

function DeploymentRow({ dep }: { dep: RecentDeployment }) {
  return (
    <tr className="group transition-colors hover:bg-slate-700/20">
      <td className="py-3 pl-5 pr-3">
        <div className="flex items-center gap-2.5">
          <DeploymentStatusIcon status={dep.status} />
          <span className="font-medium text-slate-200">
            {dep.app_name || "—"}
          </span>
        </div>
      </td>
      <td className="px-3 py-3">
        <StatusBadge status={dep.status} />
      </td>
      <td className="px-3 py-3 font-mono text-xs text-slate-500">
        {dep.commit_hash ? dep.commit_hash.slice(0, 7) : "—"}
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-1.5 text-slate-500">
          <Timer size={12} className="shrink-0" />
          <span className="text-xs">
            {formatDuration(dep.started_at, dep.finished_at)}
          </span>
        </div>
      </td>
      <td className="py-3 pl-3 pr-5 text-right text-xs text-slate-500">
        {formatDate(dep.started_at)}
      </td>
    </tr>
  );
}

/* ── Dashboard Page ────────────────────────────────────── */

export default function Dashboard() {
  const { data, isLoading, isError, error } = useDashboard();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 size={24} className="animate-spin text-slate-500" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6">
        <p className="font-medium text-red-400">Failed to load dashboard</p>
        <p className="mt-1 text-sm text-red-400/60">
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
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Platform overview and recent activity
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Servers"
          value={stats.total_servers}
          icon={<Server size={20} />}
          accent="indigo"
          subLabel={`${stats.active_servers} active`}
          href="/servers"
        />
        <StatCard
          label="Active"
          value={stats.active_servers}
          icon={<Activity size={20} />}
          accent="emerald"
          subLabel={`of ${stats.total_servers} total`}
          href="/servers"
        />
        <StatCard
          label="Apps"
          value={stats.running_apps}
          icon={<Box size={20} />}
          accent="amber"
          subLabel={`${stats.running_apps} of ${stats.total_apps} running`}
          href="/apps"
        />
        <StatCard
          label="Databases"
          value={stats.total_databases}
          icon={<Database size={20} />}
          accent="violet"
          href="/databases"
        />
      </div>

      {/* Recent Deployments */}
      <div className="overflow-hidden rounded-xl border border-slate-700/60 bg-slate-800/50">
        <div className="flex items-center justify-between border-b border-slate-700/40 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-700/50">
              <Rocket size={14} className="text-slate-400" />
            </div>
            <h2 className="text-sm font-semibold text-slate-200">
              Recent Deployments
            </h2>
          </div>
          {stats.recent_deployments.length > 0 && (
            <span className="rounded-full bg-slate-700/40 px-2.5 py-0.5 text-[11px] font-medium text-slate-400">
              {stats.recent_deployments.length}
            </span>
          )}
        </div>

        {stats.recent_deployments.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-700/30">
              <Clock size={20} className="text-slate-600" />
            </div>
            <p className="text-sm font-medium text-slate-500">
              No deployments yet
            </p>
            <p className="mt-1 text-xs text-slate-600">
              Deploy an app to see activity here
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/30">
                  {["App", "Status", "Commit", "Duration", "Started"].map(
                    (h, i) => (
                      <th
                        key={h}
                        scope="col"
                        className={[
                          "py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600",
                          i === 0 ? "pl-5 pr-3 text-left" : "px-3 text-left",
                          i === 4 ? "pr-5 text-right" : "",
                        ].join(" ")}
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/20">
                {stats.recent_deployments.map((dep) => (
                  <DeploymentRow key={dep.id} dep={dep} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
