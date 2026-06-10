import { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, AlertCircle, X, Info } from 'lucide-react';

let toastListener = null;
let toastId = 0;

// action (optional): { label, onClick } — renders an inline action button
// (e.g. "Undo"). When an action is present the default duration extends to 5s.
export function toast(message, type = 'info', duration, action = null) {
  if (toastListener) {
    const dur = duration ?? (action ? 5000 : 4000);
    toastListener({ id: ++toastId, message, type, duration: dur, action });
  }
}

toast.success = (msg, dur) => toast(msg, 'success', dur);
toast.error = (msg, dur) => toast(msg, 'error', dur || 6000);
toast.info = (msg, dur) => toast(msg, 'info', dur);

const ICONS = { success: CheckCircle2, error: AlertCircle, info: Info };

const COLORS = {
  success: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300',
  error: 'bg-red-500/15 border-red-500/30 text-red-300',
  info: 'bg-brand-500/15 border-brand-500/30 text-brand-300',
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((t) => {
    setToasts((prev) => [...prev, t]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== t.id));
    }, t.duration);
  }, []);

  useEffect(() => {
    toastListener = addToast;
    return () => { toastListener = null; };
  }, [addToast]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => {
        const Icon = ICONS[t.type] || Info;
        return (
          <div
            key={t.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm
              animate-[slideIn_0.3s_ease-out] ${COLORS[t.type] || COLORS.info}`}
          >
            <Icon className="w-5 h-5 shrink-0" />
            <p className="text-sm font-medium flex-1">{t.message}</p>
            {t.action && (
              <button
                onClick={() => {
                  t.action.onClick?.();
                  setToasts((prev) => prev.filter((x) => x.id !== t.id));
                }}
                className="shrink-0 text-xs font-semibold uppercase tracking-wide px-2 py-1 rounded-md hover:bg-white/10 transition-colors"
              >
                {t.action.label}
              </button>
            )}
            <button
              onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
              className="shrink-0 opacity-60 hover:opacity-100"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
