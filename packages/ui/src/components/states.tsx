"use client";
import { Ban, CloudOff, CreditCard, Clock, Lock, PlugZap, RefreshCw, SearchX, ServerCrash } from "lucide-react";
import { motion } from "framer-motion";
import * as React from "react";
import { cn } from "../lib/cn";
import { Button } from "./button";

export function EmptyState({ icon, title, description, action, secondary, className, compact }: {
  icon?: React.ReactNode; title: string; description?: string; action?: React.ReactNode; secondary?: React.ReactNode; className?: string; compact?: boolean;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
      className={cn("flex flex-col items-center justify-center text-center", compact ? "px-4 py-10" : "px-6 py-20", className)}>
      <div className="relative mb-5">
        <div className="absolute inset-0 -m-3 rounded-full bg-primary-soft opacity-70 blur-xl" aria-hidden />
        <div className="relative flex size-14 items-center justify-center rounded-2xl border border-border bg-surface text-primary shadow-sm [&_svg]:size-6">{icon ?? <SearchX />}</div>
      </div>
      <h3 className="text-base font-semibold tracking-tight">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-fg-muted">{description}</p>}
      {(action || secondary) && <div className="mt-5 flex items-center gap-2">{action}{secondary}</div>}
    </motion.div>
  );
}

type ErrorKind = "network" | "permission" | "session_expired" | "payment_failed" | "trial_expired" | "integration" | "unavailable" | "generic";
const ERRORS: Record<ErrorKind, { icon: React.ReactNode; title: string; description: string; tone: string }> = {
  network: { icon: <CloudOff />, title: "You're offline", description: "We can't reach the server. Check your connection and try again — your changes aren't lost.", tone: "text-warning bg-warning-soft" },
  permission: { icon: <Lock />, title: "You don't have access", description: "Your role doesn't include this area. Ask a workspace admin if you need access.", tone: "text-fg-muted bg-bg-subtle" },
  session_expired: { icon: <Clock />, title: "Your session has expired", description: "For your security you've been signed out. Sign in again to pick up where you left off.", tone: "text-info bg-info-soft" },
  payment_failed: { icon: <CreditCard />, title: "Payment failed", description: "We couldn't charge your card. Update your payment method to keep your subscription active.", tone: "text-danger bg-danger-soft" },
  trial_expired: { icon: <Ban />, title: "Your trial has ended", description: "Choose a plan to continue. Your data is safe and nothing has been deleted.", tone: "text-primary bg-primary-soft" },
  integration: { icon: <PlugZap />, title: "Integration disconnected", description: "This connection needs to be re-authorised before it can sync again.", tone: "text-warning bg-warning-soft" },
  unavailable: { icon: <ServerCrash />, title: "Data unavailable", description: "We couldn't load this right now. This is on us — please try again in a moment.", tone: "text-danger bg-danger-soft" },
  generic: { icon: <ServerCrash />, title: "Something went wrong", description: "An unexpected error occurred. Try again, and contact support if it keeps happening.", tone: "text-danger bg-danger-soft" },
};

export function ErrorState({ kind = "generic", title, description, onRetry, action, className, compact, requestId }: {
  kind?: ErrorKind; title?: string; description?: string; onRetry?: () => void; action?: React.ReactNode; className?: string; compact?: boolean; requestId?: string;
}) {
  const e = ERRORS[kind];
  return (
    <div role="alert" className={cn("flex flex-col items-center justify-center text-center", compact ? "px-4 py-10" : "px-6 py-20", className)}>
      <div className={cn("mb-5 flex size-14 items-center justify-center rounded-2xl [&_svg]:size-6", e.tone)}>{e.icon}</div>
      <h3 className="text-base font-semibold tracking-tight">{title ?? e.title}</h3>
      <p className="mt-1.5 max-w-sm text-sm text-fg-muted">{description ?? e.description}</p>
      <div className="mt-5 flex items-center gap-2">
        {onRetry && <Button variant="secondary" onClick={onRetry}><RefreshCw /> Try again</Button>}
        {action}
      </div>
      {requestId && <p className="mt-4 text-xs text-fg-subtle">Reference: {requestId}</p>}
    </div>
  );
}
