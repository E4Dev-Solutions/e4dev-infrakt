interface StatusBadgeProps {
  status: string;
  className?: string;
}

type BadgeVariant = "green" | "gray" | "blue" | "red" | "amber";

function getVariant(status: string): BadgeVariant {
  const normalized = status.toLowerCase().trim();
  if (normalized === "running" || normalized === "active" || normalized === "success") {
    return "green";
  }
  if (
    normalized === "stopped" ||
    normalized === "inactive" ||
    normalized === "idle"
  ) {
    return "gray";
  }
  if (
    normalized === "deploying" ||
    normalized === "provisioning" ||
    normalized === "in_progress" ||
    normalized === "pending"
  ) {
    return "blue";
  }
  if (normalized === "error" || normalized === "failed" || normalized === "unhealthy") {
    return "red";
  }
  if (normalized === "warning" || normalized === "restarting") {
    return "amber";
  }
  if (normalized === "healthy") {
    return "green";
  }
  if (normalized === "starting") {
    return "blue";
  }
  return "gray";
}

const variantClasses: Record<BadgeVariant, string> = {
  green: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  gray: "bg-slate-600/30 text-slate-400 ring-1 ring-slate-500/30",
  blue: "bg-indigo-500/15 text-indigo-400 ring-1 ring-indigo-500/30 badge-pulse",
  red: "bg-red-500/15 text-red-400 ring-1 ring-red-500/30",
  amber: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
};

function formatLabel(status: string): string {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Colored pill badge for resource status values. */
export default function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const variant = getVariant(status);
  return (
    <span
      className={[
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className,
      ].join(" ")}
      aria-label={`Status: ${formatLabel(status)}`}
    >
      {formatLabel(status)}
    </span>
  );
}
