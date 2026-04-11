'use client';

import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';

type ToastType = 'success' | 'error' | 'info' | 'warning';

interface ToastOptions {
  type?: ToastType;
  /** How long the toast stays visible, in ms. Default 3000. For undo toasts, default 5000. */
  durationMs?: number;
  /** When provided, shows an "撤销" button. Clicking calls this and hides the toast. */
  onUndo?: () => void | Promise<void>;
  /** Label for the undo button. Default "撤销". */
  undoLabel?: string;
}

interface Toast {
  id: number;
  message: string;
  type: ToastType;
  onUndo?: () => void | Promise<void>;
  undoLabel: string;
  undoing?: boolean;
}

interface ToastContextType {
  /**
   * Shows a toast. Backward compatible with (message, type) and new (message, options) signature.
   * Examples:
   *   showToast('ok')
   *   showToast('saved', 'success')
   *   showToast('已记录俯卧撑 30 个', { type: 'success', onUndo: () => revert() })
   */
  showToast: (message: string, typeOrOpts?: ToastType | ToastOptions) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

const TOAST_COLORS: Record<ToastType, string> = {
  success: 'bg-green-500',
  error: 'bg-red-500',
  info: 'bg-blue-500',
  warning: 'bg-amber-500',
};

const TOAST_ICONS: Record<ToastType, string> = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
  warning: '⚠',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t) {
      clearTimeout(t);
      timers.current.delete(id);
    }
    setToasts(prev => prev.filter(x => x.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, typeOrOpts?: ToastType | ToastOptions) => {
      const opts: ToastOptions =
        typeof typeOrOpts === 'string' ? { type: typeOrOpts } : typeOrOpts || {};
      const type = opts.type || 'info';
      const onUndo = opts.onUndo;
      const undoLabel = opts.undoLabel || '撤销';
      const durationMs = opts.durationMs ?? (onUndo ? 5000 : 3000);

      const id = Date.now() + Math.random();
      setToasts(prev => [...prev, { id, message, type, onUndo, undoLabel }]);

      const timer = setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
        timers.current.delete(id);
      }, durationMs);
      timers.current.set(id, timer);
    },
    []
  );

  const handleUndoClick = useCallback(
    async (toast: Toast) => {
      if (!toast.onUndo || toast.undoing) return;
      // mark undoing so repeated clicks are ignored
      setToasts(prev => prev.map(t => (t.id === toast.id ? { ...t, undoing: true } : t)));
      try {
        await toast.onUndo();
      } catch (e) {
        console.error('undo failed', e);
        // leave the toast up so user can see it didn't work
        setToasts(prev => prev.map(t => (t.id === toast.id ? { ...t, undoing: false } : t)));
        return;
      }
      dismiss(toast.id);
    },
    [dismiss]
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* Toast container */}
      <div className="fixed top-20 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map(toast => (
          <div
            key={toast.id}
            className={`${TOAST_COLORS[toast.type]} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 min-w-[220px] max-w-[420px] pointer-events-auto animate-slide-in`}
          >
            <span className="text-lg font-bold flex-shrink-0">{TOAST_ICONS[toast.type]}</span>
            <span className="text-sm leading-tight flex-1">{toast.message}</span>
            {toast.onUndo && (
              <button
                onClick={() => handleUndoClick(toast)}
                disabled={toast.undoing}
                className="ml-auto shrink-0 px-3 py-1 rounded-md text-xs font-bold bg-white/20 hover:bg-white/30 transition-colors disabled:opacity-50"
              >
                {toast.undoing ? '撤销中…' : toast.undoLabel}
              </button>
            )}
            <button
              onClick={() => dismiss(toast.id)}
              className="shrink-0 text-white/70 hover:text-white text-lg leading-none"
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <style jsx global>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(100%); }
          to { opacity: 1; transform: translateX(0); }
        }
        .animate-slide-in {
          animation: slideIn 0.3s ease-out;
        }
      `}</style>
    </ToastContext.Provider>
  );
}
