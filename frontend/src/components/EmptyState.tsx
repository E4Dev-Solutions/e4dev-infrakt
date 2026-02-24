import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

/** Centered empty state with icon, title, description, and optional CTA. */
export default function EmptyState({
  icon,
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-800 text-slate-500">
        {icon}
      </div>
      <h3 className="mb-1 text-base font-semibold text-slate-200">{title}</h3>
      {description && (
        <p className="mb-5 max-w-xs text-sm text-slate-400">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
