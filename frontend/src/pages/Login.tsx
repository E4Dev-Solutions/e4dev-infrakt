import { useState } from "react";
import { KeyRound } from "lucide-react";
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

    // Validate the key by hitting the dashboard endpoint
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
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600/10 mb-4">
            <KeyRound className="w-8 h-8 text-blue-400" />
          </div>
          <h1 className="text-2xl font-bold text-white">infrakt</h1>
          <p className="text-gray-400 mt-1 text-sm">Enter your API key to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="api-key" className="block text-sm font-medium text-gray-300 mb-1">
              API Key
            </label>
            <input
              id="api-key"
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="Paste your API key"
              autoFocus
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Found at <code className="text-gray-400">~/.infrakt/api_key.txt</code>
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !key.trim()}
            className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Verifying..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
