import { useState } from "react";
import { Zap, ArrowRight, Loader2 } from "lucide-react";
import { setApiKey } from "@/api/client";

interface Props {
  onLogin: () => void;
}

export default function Login({ onLogin }: Props) {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!key.trim()) return;

    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/dashboard", {
        headers: { "X-API-Key": key.trim() },
      });
      if (res.ok) {
        setApiKey(key.trim());
        onLogin();
      } else if (res.status === 401 || res.status === 403) {
        setError("Invalid API key");
      } else {
        setError(`Unexpected error: ${res.status}`);
      }
    } catch {
      setError("Cannot reach the API server");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center bg-zinc-950 px-4 overflow-hidden">
      {/* Background atmospheric gradient */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-1/2 left-1/2 h-[800px] w-[800px] -translate-x-1/2 rounded-full bg-orange-500/[0.04] blur-3xl" />
        <div className="absolute -bottom-1/4 -left-1/4 h-[600px] w-[600px] rounded-full bg-orange-600/[0.03] blur-3xl" />
      </div>

      {/* Subtle grid pattern */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }}
      />

      <div className="relative w-full max-w-sm">
        {/* Logo */}
        <div className="mb-10 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 shadow-lg shadow-orange-500/20 mb-5">
            <Zap size={24} className="text-white" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-50">
            infrakT
          </h1>
          <p className="text-zinc-500 mt-2 text-sm">
            Sign in to your platform dashboard
          </p>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 backdrop-blur-sm p-6 shadow-2xl shadow-black/40">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="api-key"
                className="block text-xs font-medium uppercase tracking-wider text-zinc-500 mb-2"
              >
                API Key
              </label>
              <input
                id="api-key"
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="Paste your API key"
                autoFocus
                className="w-full rounded-xl border border-zinc-700 bg-zinc-800/80 px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors focus:border-orange-500/60 focus:outline-none focus:ring-1 focus:ring-orange-500/40"
              />
              <p className="text-xs text-zinc-600 mt-2">
                Found at{" "}
                <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-zinc-400">
                  ~/.infrakt/api_key.txt
                </code>
              </p>
            </div>

            {error && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2.5">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !key.trim()}
              className="group flex w-full items-center justify-center gap-2 rounded-xl bg-orange-600 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-orange-500 hover:shadow-lg hover:shadow-orange-500/20 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-none"
            >
              {loading ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Verifying...
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-zinc-700">
          Self-hosted PaaS &middot; SSH-based &middot; Zero agents
        </p>
      </div>
    </div>
  );
}
