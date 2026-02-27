import { useRef, useEffect } from "react";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";

interface Props {
  lines: string[];
  isStreaming: boolean;
  status: string | null;
  error: string | null;
  onClose?: () => void;
}

export default function DeploymentLogStream({
  lines,
  isStreaming,
  status,
  error,
  onClose,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines.length]);

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isStreaming ? (
            <>
              <Loader2
                size={14}
                className="animate-spin text-sky-400"
                aria-hidden="true"
              />
              <span className="text-sm font-medium text-sky-400">
                Deploying&hellip;
              </span>
            </>
          ) : status === "success" ? (
            <>
              <CheckCircle2
                size={14}
                className="text-emerald-400"
                aria-hidden="true"
              />
              <span className="text-sm font-medium text-emerald-400">
                Deployment succeeded
              </span>
            </>
          ) : status === "failed" ? (
            <>
              <XCircle
                size={14}
                className="text-red-400"
                aria-hidden="true"
              />
              <span className="text-sm font-medium text-red-400">
                Deployment failed
              </span>
            </>
          ) : null}
        </div>
        {onClose && !isStreaming && (
          <button
            onClick={onClose}
            className="rounded-md border border-zinc-600 bg-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
          >
            Close
          </button>
        )}
      </div>

      {/* Log terminal */}
      <div
        className="h-[400px] overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-950 p-4 font-mono text-xs leading-relaxed text-zinc-300"
        aria-label="Deployment logs"
        role="log"
        aria-live="polite"
      >
        {lines.length === 0 && isStreaming && (
          <span className="text-zinc-500">Waiting for logs&hellip;</span>
        )}
        {lines.map((line, i) => (
          <div
            key={i}
            className={
              line.includes("[ERROR]") ? "text-red-400" : undefined
            }
          >
            {line}
          </div>
        ))}
        {error && (
          <div className="mt-2 text-red-400">Stream error: {error}</div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
