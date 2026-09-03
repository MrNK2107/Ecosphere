import { useState, useEffect, useCallback } from "react";

export type ToastType = "success" | "error" | "info";

interface Toast {
  id: string;
  type: ToastType;
  message: string;
}

let _addToast: ((type: ToastType, message: string) => void) | null = null;

export function showToast(type: ToastType, message: string) {
  _addToast?.(type, message);
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((type: ToastType, message: string) => {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    setToasts((prev) => [...prev, { id, type, message }]);
    // Auto-remove after 4s
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  useEffect(() => {
    _addToast = addToast;
    return () => { _addToast = null; };
  }, [addToast]);

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const colors: Record<ToastType, string> = {
    success: "bg-green-900/80 border-green-700 text-green-200",
    error: "bg-red-900/80 border-red-700 text-red-200",
    info: "bg-blue-900/80 border-blue-700 text-blue-200",
  };

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`px-3 py-2 rounded border text-xs max-w-xs ${colors[t.type]} flex items-start gap-2 cursor-pointer`}
          onClick={() => removeToast(t.id)}
        >
          <span className="flex-1">{t.message}</span>
          <span className="opacity-50">✕</span>
        </div>
      ))}
    </div>
  );
}
