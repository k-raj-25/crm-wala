"use client";
import { AlertTriangle, Info, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import * as React from "react";
import { cn } from "../lib/cn";

type Tone = "success" | "error" | "info" | "warning";
type Toast = { id: number; tone: Tone; title: string; description?: string; action?: { label: string; onClick: () => void } };
type Ctx = { toast: (t: Omit<Toast, "id"> & { duration?: number }) => void; success: (title: string, description?: string) => void; error: (title: string, description?: string) => void };
const ToastCtx = React.createContext<Ctx | null>(null);

export const useToast = () => {
  const c = React.useContext(ToastCtx);
  if (!c) throw new Error("useToast must be used inside <ToastProvider>");
  return c;
};

function SuccessCheck() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" className="fill-success" />
      <path d="M7.5 12.5l3 3 6-6.5" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="24" style={{ animation: "check-draw 380ms 80ms ease-out both" }} />
    </svg>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<Toast[]>([]);
  const id = React.useRef(0);
  const dismiss = (i: number) => setItems((p) => p.filter((t) => t.id !== i));
  const toast = React.useCallback((t: Omit<Toast, "id"> & { duration?: number }) => {
    const n = ++id.current;
    setItems((p) => [...p.slice(-3), { ...t, id: n }]);
    setTimeout(() => dismiss(n), t.duration ?? (t.tone === "error" ? 6500 : 3800));
  }, []);
  const ctx = React.useMemo<Ctx>(() => ({ toast, success: (title, description) => toast({ tone: "success", title, description }), error: (title, description) => toast({ tone: "error", title, description }) }), [toast]);
  return (
    <ToastCtx.Provider value={ctx}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[200] flex flex-col items-center gap-2 px-4 md:bottom-6 md:items-end md:px-6" role="region" aria-label="Notifications" aria-live="polite">
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <motion.div key={t.id} layout initial={{ opacity: 0, y: 16, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.12 } }} transition={{ type: "spring", stiffness: 500, damping: 36 }}
              className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border border-border bg-surface p-3.5 shadow-lg">
              <span className={cn("mt-0.5 shrink-0", t.tone === "error" && "text-danger", t.tone === "info" && "text-info", t.tone === "warning" && "text-warning")}>
                {t.tone === "success" ? <SuccessCheck /> : t.tone === "info" ? <Info className="size-5" /> : <AlertTriangle className="size-5" />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{t.title}</p>
                {t.description && <p className="mt-0.5 text-[13px] text-fg-muted">{t.description}</p>}
                {t.action && <button className="mt-1.5 text-[13px] font-medium text-primary hover:underline" onClick={() => { t.action!.onClick(); dismiss(t.id); }}>{t.action.label}</button>}
              </div>
              <button aria-label="Dismiss" onClick={() => dismiss(t.id)} className="-mr-1 rounded p-1 text-fg-subtle hover:bg-surface-hover hover:text-fg"><X className="size-4" /></button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}
