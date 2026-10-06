"use client";
import { motion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import * as React from "react";
import { Badge, Button, Card, Skeleton, cn } from "@crm/ui";

export function PageHeader({ title, description, actions }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0"><h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>{description && <p className="mt-1 text-sm text-fg-muted">{description}</p>}</div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, loading, tone }: { label: string; value: React.ReactNode; hint?: React.ReactNode; loading?: boolean; tone?: "danger" | "success" | "warning" }) {
  return (
    <Card className="p-4">
      <p className="text-[13px] text-fg-muted">{label}</p>
      {loading ? <Skeleton className="mt-2 h-8 w-24" /> : <p className={cn("tabular mt-1 text-2xl font-semibold tracking-tight", tone === "danger" && "text-danger", tone === "success" && "text-success", tone === "warning" && "text-warning")}>{value}</p>}
      {hint && <p className="mt-1 text-xs text-fg-subtle">{hint}</p>}
    </Card>
  );
}

export function Delta({ value }: { value: number }) {
  const up = value >= 0;
  return <span className={cn("inline-flex items-center gap-0.5 text-xs font-medium", up ? "text-success" : "text-danger")}>{up ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}{Math.abs(value)}%</span>;
}

export const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral" | "primary"> = {
  active: "success", trial: "info", trialing: "info", past_due: "warning", trial_expired: "warning", expired: "warning", suspended: "danger", canceled: "neutral", cancelled: "neutral",
  succeeded: "success", failed: "danger", refunded: "neutral", paid: "success", open: "info", void: "neutral", pending: "warning", processed: "success", ended: "neutral", connected: "success", error: "danger", reconnect: "warning",
};
export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-fg-subtle">—</span>;
  return <Badge tone={STATUS_TONE[status] ?? "neutral"} dot>{status.replace(/_/g, " ")}</Badge>;
}

export function Pager({ meta, onPage }: { meta?: { page: number; pages: number; total: number }; onPage: (p: number) => void }) {
  if (!meta || meta.total === 0) return null;
  return (
    <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm text-fg-muted">
      <span className="tabular">{meta.total.toLocaleString()} total · page {meta.page} of {meta.pages}</span>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={meta.page <= 1} onClick={() => onPage(meta.page - 1)}>Previous</Button>
        <Button size="sm" variant="secondary" disabled={meta.page >= meta.pages} onClick={() => onPage(meta.page + 1)}>Next</Button>
      </div>
    </div>
  );
}

export function Reveal({ children, delay = 0, className }: { children: React.ReactNode; delay?: number; className?: string }) {
  return <motion.div className={className} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay }}>{children}</motion.div>;
}

export const inr = (v: number | null | undefined, compact = false) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0, notation: compact ? "compact" : "standard" }).format(v ?? 0);
export const minor = (v: number | null | undefined) => inr((v ?? 0) / 100);
export const shortDay = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
