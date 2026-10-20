"use client";
import { ArrowLeft, Ban, CloudOff, Compass, CreditCard, Clock, Home, Lock, PlugZap, RefreshCw, SearchX, ServerCrash } from "lucide-react";
import { motion } from "framer-motion";
import * as React from "react";
import { cn } from "../lib/cn";
import { Button, buttonVariants } from "./button";
import { LogoMark } from "./logo";

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

/* Full-page screen for route errors (error.tsx / global-error.tsx) and 404s: a frosted card centred over the glow.
   Plain <a> links (not next/link) so it still works when the app's router is what broke. */
export function PageError({ kind = "error", title, description, onRetry, homeHref = "/", homeLabel = "Go to home", digest, details }: {
  kind?: "error" | "not-found"; title?: string; description?: string; onRetry?: () => void; homeHref?: string; homeLabel?: string; digest?: string; details?: string;
}) {
  const notFound = kind === "not-found";
  const [canGoBack, setCanGoBack] = React.useState(false);
  React.useEffect(() => { setCanGoBack(window.history.length > 1); }, []);
  const retry = onRetry ?? (() => window.location.reload());
  return (
    <main role={notFound ? undefined : "alert"} className="flex min-h-dvh items-center justify-center px-4 py-10 text-fg">
      <div className="glass w-full max-w-md rounded-3xl border border-border bg-surface p-7 text-center shadow-lg sm:p-9">
        <a href={homeHref} className="mx-auto mb-7 inline-flex items-center gap-2 text-sm font-semibold tracking-tight text-fg">
          <LogoMark size={24} /> CRM Wala
        </a>
        <div className="relative mx-auto mb-5 size-16">
          <div className={cn("absolute inset-0 -m-2 rounded-full opacity-80 blur-xl", notFound ? "bg-primary-soft" : "bg-danger-soft")} aria-hidden />
          <div className={cn("relative flex size-16 items-center justify-center rounded-2xl border border-border [&_svg]:size-7", notFound ? "bg-primary-soft text-primary" : "bg-danger-soft text-danger")}>
            {notFound ? <Compass /> : <ServerCrash />}
          </div>
        </div>
        {notFound && <p className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-fg-subtle">Error 404</p>}
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{title ?? (notFound ? "We can't find that page" : "This page couldn't load")}</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-fg-muted text-pretty">
          {description ?? (notFound
            ? "The link may be old, or the page may have moved. Head home and pick up from there."
            : "Something went wrong on our side. Reload to try again. Your work is saved, and nothing has been lost.")}
        </p>
        {details && <pre className="mt-4 max-h-32 overflow-auto rounded-xl border border-border bg-bg-subtle px-3 py-2 text-left font-mono text-xs whitespace-pre-wrap break-words text-fg-muted">{details}</pre>}
        <div className="mt-7 flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-center">
          {notFound ? (
            canGoBack && <Button variant="secondary" size="lg" onClick={() => window.history.back()}><ArrowLeft /> Go back</Button>
          ) : (
            canGoBack
              ? <Button variant="secondary" size="lg" onClick={() => window.history.back()}><ArrowLeft /> Go back</Button>
              : <a href={homeHref} className={buttonVariants({ variant: "secondary", size: "lg" })}><Home /> {homeLabel}</a>
          )}
          {notFound
            ? <a href={homeHref} className={buttonVariants({ size: "lg" })}><Home /> {homeLabel}</a>
            : <Button size="lg" onClick={retry}><RefreshCw /> Reload page</Button>}
        </div>
        {digest && <p className="mt-6 text-xs text-fg-subtle">Reference: <span className="font-mono">{digest}</span></p>}
      </div>
    </main>
  );
}
