import { useState, useCallback } from "react";
import type { ToastMessage, ToastType } from "@/components/Toast";

let nextId = 1;

/** Simple toast state manager — no external library required. */
export function useToast() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((type: ToastType, message: string) => {
    const id = nextId++;
    setToasts((prev) => [...prev, { id, type, message }]);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const success = useCallback(
    (message: string) => addToast("success", message),
    [addToast]
  );

  const error = useCallback(
    (message: string) => addToast("error", message),
    [addToast]
  );

  return { toasts, dismiss, success, error };
}
