/**
 * Minimal singleton toast system — no context or provider required.
 *
 * Usage:
 *   import { toast } from "../toast";
 *   toast.success("Pick saved.");
 *   toast.error("Failed to save pick.");
 *
 * Render <Toaster /> once at the app root to display queued messages.
 */

import { useState, useEffect } from "react";

export type ToastType = "success" | "error";

export interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

type Listener = (toasts: ToastItem[]) => void;

let _toasts: ToastItem[] = [];
let _nextId = 0;
const _listeners = new Set<Listener>();

function _notify() {
  const snapshot = [..._toasts];
  _listeners.forEach((l) => l(snapshot));
}

function _add(message: string, type: ToastType, durationMs = 3_500) {
  const id = _nextId++;
  _toasts = [..._toasts, { id, message, type }];
  _notify();
  setTimeout(() => {
    _toasts = _toasts.filter((t) => t.id !== id);
    _notify();
  }, durationMs);
}

export const toast = {
  success: (message: string) => _add(message, "success"),
  error: (message: string) => _add(message, "error"),
};

/** Subscribe a React component to the current toast list. */
export function useToasts(): ToastItem[] {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  useEffect(() => {
    _listeners.add(setToasts);
    return () => {
      _listeners.delete(setToasts);
    };
  }, []);
  return toasts;
}
