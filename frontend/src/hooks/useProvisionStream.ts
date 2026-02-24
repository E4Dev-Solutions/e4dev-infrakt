import { useState, useEffect } from "react";
import { getApiKey } from "@/api/client";

export interface ProvisionStreamState {
  lines: string[];
  isStreaming: boolean;
  status: string | null; // "active" | "inactive" | null (still running)
  error: string | null;
}

/**
 * Streams provisioning progress via SSE from
 * `GET /api/servers/{name}/provision/stream?key={provisionKey}`.
 *
 * Uses `fetch` (not `EventSource`) to support the `X-API-Key` header.
 */
export function useProvisionStream(
  serverName: string | null,
  provisionKey: number | null,
): ProvisionStreamState {
  const [lines, setLines] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!serverName || provisionKey === null) return;

    setLines([]);
    setIsStreaming(true);
    setStatus(null);
    setError(null);

    const controller = new AbortController();

    async function connect() {
      const apiKey = getApiKey();
      const url = `/api/servers/${encodeURIComponent(serverName!)}/provision/stream?key=${provisionKey}`;

      try {
        const response = await fetch(url, {
          headers: { ...(apiKey ? { "X-API-Key": apiKey } : {}) },
          signal: controller.signal,
        });

        if (!response.ok) {
          setError(`Stream failed: ${response.status}`);
          setIsStreaming(false);
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          setError("No response body");
          setIsStreaming(false);
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() ?? "";

          for (const event of events) {
            const dataLine = event
              .split("\n")
              .find((l) => l.startsWith("data: "));
            if (!dataLine) continue;

            try {
              const payload = JSON.parse(dataLine.slice(6)) as {
                line?: string;
                done?: boolean;
                status?: string;
              };
              if (payload.done) {
                setStatus(payload.status ?? null);
                setIsStreaming(false);
              } else if (payload.line) {
                setLines((prev) => [...prev, payload.line!]);
              }
            } catch {
              // Ignore malformed SSE events
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((err as Error).message);
        }
      } finally {
        setIsStreaming(false);
      }
    }

    void connect();

    return () => {
      controller.abort();
    };
  }, [serverName, provisionKey]);

  return { lines, isStreaming, status, error };
}
