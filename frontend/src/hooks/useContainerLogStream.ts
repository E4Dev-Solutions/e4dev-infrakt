import { useState, useEffect, useCallback, useRef } from "react";
import { getApiKey } from "@/api/client";

export interface ContainerLogStreamState {
  lines: string[];
  isStreaming: boolean;
  error: string | null;
  clear: () => void;
}

/**
 * Streams live container logs via SSE from
 * `GET /api/apps/{name}/logs/stream?lines=N`.
 *
 * Uses `fetch` (not `EventSource`) to support the `X-API-Key` header.
 * The stream runs indefinitely until `enabled` becomes false or the
 * component unmounts.
 */
export function useContainerLogStream(
  appName: string | null,
  lines: number,
  enabled: boolean,
): ContainerLogStreamState {
  const [logLines, setLogLines] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const clear = useCallback(() => setLogLines([]), []);

  useEffect(() => {
    if (!appName || !enabled) {
      setIsStreaming(false);
      return;
    }

    setLogLines([]);
    setIsStreaming(true);
    setError(null);

    const controller = new AbortController();
    controllerRef.current = controller;

    async function connect() {
      const apiKey = getApiKey();
      const url = `/api/apps/${encodeURIComponent(appName!)}/logs/stream?lines=${lines}`;

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
              };
              if (payload.line !== undefined) {
                setLogLines((prev) => [...prev, payload.line!]);
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
  }, [appName, lines, enabled]);

  return { lines: logLines, isStreaming, error, clear };
}
