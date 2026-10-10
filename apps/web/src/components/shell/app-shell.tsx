"use client";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Ban, CreditCard, Download, LifeBuoy, MailWarning, Menu, MoreHorizontal, Search, ShieldAlert, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { Button, Dialog, DialogContent, ErrorState, Kbd, Logo, Skeleton, cn, humanDuration, useChord, useHotkey, useLocalStorage, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { MOBILE_PRIMARY, NAV } from "@/lib/nav";
import { useAccess, useMe } from "@/lib/queries";
import { ComposeEmail } from "../forms/compose-email";
import { CommandPalette } from "./command-palette";
import { QuickCreateDrawer, QuickCreateMenu } from "./quick-create";
import { Sidebar, UserMenu, WorkspaceSwitcher, useNavItems } from "./sidebar";
import { UIProvider, useUI } from "./ui-context";
import { NotificationsPopover } from "./notifications";

function TrialBanner() {
  const { data: me } = useMe();
  const sub = me?.subscription;
  const [dismissed, setDismissed] = useLocalStorage<Record<string, boolean>>("banner-dismissed", {});
  if (!sub) return null;
  const a = sub.access;
  let msg: React.ReactNode = null, tone = "bg-primary-soft text-primary", key = "", cta = "Choose a plan";
  if (sub.status === "trialing" && a.state === "full" && a.seconds_left != null) {
    const day = new Date().toDateString();
    if (a.trial_stage === "day1") { key = `t1-${me!.workspace!.id}`; msg = <><strong>Welcome!</strong> Your 3-day trial has started — everything is unlocked.</>; cta = "See plans"; }
    else if (a.trial_stage === "day2") { key = `t2-${day}`; msg = <><strong>Your trial ends tomorrow.</strong> {humanDuration(a.seconds_left)} left.</>; tone = "bg-warning-soft text-warning"; }
    else if (a.trial_stage === "final") { key = `t3-${day}`; msg = <><strong>Your trial ends {a.seconds_left < 86400 / 2 ? "soon" : "today"}.</strong> {humanDuration(a.seconds_left)} left — upgrade now to keep access to your CRM.</>; tone = "bg-warning-soft text-warning"; }
  } else if (a.state === "grace") { key = `g-${new Date().toDateString()}`; msg = <><strong>Payment failed.</strong> You keep full access for {humanDuration(a.seconds_left ?? 0)} while we retry — please update your payment method.</>; tone = "bg-danger-soft text-danger"; cta = "Update billing"; }
  else if (sub.status === "canceled" && sub.current_period_end) { key = `c-${sub.current_period_end}`; msg = <>Your subscription ends on <strong>{new Date(sub.current_period_end).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</strong>.</>; cta = "Resume"; }
  else if (sub.cancel_at_period_end && sub.current_period_end) { key = `cp-${sub.current_period_end}`; msg = <>Your plan is set to cancel on <strong>{new Date(sub.current_period_end).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</strong>.</>; cta = "Resume"; }
  if (!msg || dismissed[key]) return null;
  return (
    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} className={cn("overflow-hidden text-[13px]", tone)} role="status">
      <div className="mx-auto flex max-w-[1600px] items-center justify-center gap-3 px-4 py-2"><Sparkles className="hidden size-4 shrink-0 sm:block" /><span className="text-center">{msg}</span><Link href="/app/billing" className="shrink-0 rounded-md bg-current/10 px-2.5 py-1 font-semibold hover:bg-current/20"><span className="text-inherit">{cta} →</span></Link><button aria-label="Dismiss" onClick={() => setDismissed({ ...dismissed, [key]: true })} className="shrink-0 rounded p-1 opacity-70 hover:opacity-100"><X className="size-3.5" /></button></div>
    </motion.div>
  );
}

function ImpersonationBanner() {
  const { data: me } = useMe();
  if (!me?.impersonating) return null;
  return <div role="alert" className="flex items-center justify-center gap-3 bg-danger px-4 py-2 text-[13px] font-medium text-white"><ShieldAlert className="size-4" />You're viewing {me.user.name}'s workspace as support. Every action is logged.<button className="rounded bg-white/20 px-2.5 py-1 hover:bg-white/30" onClick={async () => { await api.post("/api/v1/auth/logout"); window.location.href = "/login"; }}>Exit</button></div>;
}

function VerifyBanner() {
  const { data: me } = useMe(); const toast = useToast();
  if (!me || me.user.email_verified) return null;
  return <div className="bg-info-soft px-4 py-2 text-center text-[13px] text-info"><MailWarning className="mr-2 inline size-4" />Please verify your email address. <button className="font-semibold underline" onClick={async () => { await api.post("/api/v1/auth/resend-verification"); toast.success("Verification email sent"); }}>Resend link</button></div>;
}

function RestrictedScreen() {
  const { data: me } = useMe(); const toast = useToast();
  const sub = me?.subscription; const reason = sub?.access.reason; const suspended = sub?.access.state === "suspended";
  const isOwnerLike = (me?.permissions ?? []).includes("*") || (me?.permissions ?? []).includes("billing.manage");
  const exp = async () => { const r = await api.raw("GET", "/api/v1/export/workspace"); if (!r.ok) { toast.error("Export failed"); return; } const b = await r.blob(); const u = URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = `${me?.workspace?.slug}-export.zip`; a.click(); URL.revokeObjectURL(u); };
  const copy = suspended ? { title: "This workspace is suspended", body: "Access has been paused by the platform team. Contact support to restore it.", icon: <ShieldAlert /> }
    : reason === "payment_failed" ? { title: "Payment failed", body: "We couldn't collect your latest payment and the grace period has ended. Update your payment method to restore access.", icon: <CreditCard /> }
    : reason === "subscription_ended" ? { title: "Your subscription has ended", body: "Choose a plan to pick up right where you left off.", icon: <Ban /> }
    : { title: "Your trial has ended", body: "Choose a plan to continue.", icon: <Ban /> };
  return (
    <div className="mx-auto flex min-h-[70dvh] max-w-xl flex-col items-center justify-center px-6 text-center">
      <div className="mb-6 flex size-16 items-center justify-center rounded-2xl bg-primary-soft text-primary [&_svg]:size-7">{copy.icon}</div>
      <h1 className="text-3xl font-semibold tracking-tight">{copy.title}</h1>
      <p className="mt-3 text-lg text-fg-muted">{copy.body}</p>
      <p className="mt-2 text-sm text-fg-subtle">Your data is safe — nothing has been deleted. You can still sign in, view billing and export everything.</p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        {!suspended && (isOwnerLike ? <Button size="lg" asChild><Link href="/app/billing">{reason === "payment_failed" ? "Update payment" : "Choose a plan to continue"}</Link></Button> : <p className="text-sm text-fg-muted">Ask a workspace owner to choose a plan.</p>)}
        <Button size="lg" variant="secondary" onClick={exp}><Download /> Export my data</Button>
        {suspended && <Button size="lg" variant="secondary" asChild><a href="mailto:support@crmwala.com"><LifeBuoy /> Contact support</a></Button>}
      </div>
    </div>
  );
}

const SHORTCUTS = [["⌘ K", "Command palette / search"], ["C", "Quick create menu"], ["G then B/L/C/P/K/T…", "Go to Projects, Leads, Clients, Pipeline, Site visits, Daily plan…"], ["[", "Collapse / expand sidebar"], ["?", "Show this help"], ["Esc", "Close dialogs"]];
function ShortcutsDialog() {
  const ui = useUI();
  return <Dialog open={ui.shortcuts} onOpenChange={ui.setShortcuts}><DialogContent size="sm" title="Keyboard shortcuts"><ul className="divide-y divide-border">{SHORTCUTS.map(([k, d]) => <li key={k} className="flex items-center justify-between gap-4 py-2.5 text-sm"><span className="text-fg-muted">{d}</span><span className="flex shrink-0 gap-1">{k.split(" ").map((p, i) => <Kbd key={i}>{p}</Kbd>)}</span></li>)}</ul></DialogContent></Dialog>;
}

function MobileNav() {
  const pathname = usePathname(); const items = useNavItems(); const [more, setMore] = React.useState(false);
  const primary = items.filter((i) => MOBILE_PRIMARY.includes(i.href)); const rest = items.filter((i) => !MOBILE_PRIMARY.includes(i.href));
  const act = (h: string) => (h === "/app" ? pathname === "/app" : pathname.startsWith(h));
  React.useEffect(() => setMore(false), [pathname]);
  return (
    <>
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden" aria-label="Primary">
        <ul className="grid grid-cols-5">
          {primary.map((i) => <li key={i.href}><Link href={i.href} aria-current={act(i.href) ? "page" : undefined} className={cn("flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium", act(i.href) ? "text-primary" : "text-fg-subtle")}><i.icon className="size-5" />{i.label}</Link></li>)}
          <li><button onClick={() => setMore(true)} className={cn("flex h-16 w-full flex-col items-center justify-center gap-1 text-[11px] font-medium", more ? "text-primary" : "text-fg-subtle")}><MoreHorizontal className="size-5" />More</button></li>
        </ul>
      </nav>
      <AnimatePresence>
        {more && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 bg-[var(--overlay)] md:hidden" onClick={() => setMore(false)} />
            <motion.div initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", stiffness: 420, damping: 38 }} className="fixed inset-x-0 bottom-0 z-50 max-h-[85dvh] overflow-y-auto rounded-t-2xl border-t border-border bg-surface p-4 pb-8 shadow-lg md:hidden" role="dialog" aria-label="More">
              <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-border-strong" />
              <div className="grid grid-cols-3 gap-2">{rest.map((i) => <Link key={i.href} href={i.href} className="flex flex-col items-center gap-2 rounded-xl border border-border p-3.5 text-xs font-medium hover:bg-surface-hover"><i.icon className="size-5 text-primary" />{i.label}</Link>)}</div>
              <div className="mt-4 space-y-1 border-t border-border pt-3"><WorkspaceSwitcher /><UserMenu /></div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

function Topbar() {
  const ui = useUI();
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-bg/80 px-4 backdrop-blur-xl sm:px-8">
      <div className="md:hidden"><Link href="/app"><Logo collapsed /></Link></div>
      <button onClick={() => ui.openCommand()} className="group flex h-9 max-w-md flex-1 items-center gap-2.5 rounded-lg border border-border bg-surface px-3 text-sm text-fg-subtle shadow-xs transition-colors hover:border-border-strong" aria-label="Search or run a command">
        <Search className="size-4" /><span className="flex-1 text-left">Search or jump to…</span><span className="hidden gap-1 sm:flex"><Kbd>⌘</Kbd><Kbd>K</Kbd></span>
      </button>
      <div className="ml-auto flex items-center gap-2"><div className="md:hidden"><NotificationsPopover collapsed /></div><QuickCreateMenu /></div>
    </header>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter(); const pathname = usePathname(); const ui = useUI();
  const [collapsed, setCollapsed] = useLocalStorage("sidebar-collapsed", false);
  const { data: me, isLoading, error } = useMe();
  const { restricted } = useAccess();
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: () => api.get<{ require_email_verification: boolean }>("/api/v1/auth/config"), staleTime: Infinity });
  const items = useNavItems();
  useHotkey("mod+k", (e) => { e.preventDefault(); ui.openCommand(); });
  useHotkey("[", () => setCollapsed((c) => !c));
  useHotkey("?", () => ui.openShortcuts());
  useHotkey("c", (e) => { e.preventDefault(); ui.openCommand("Create "); }, [items.length]);
  useChord("g", Object.fromEntries(NAV.filter((n) => n.chord).map((n) => [n.chord!, () => router.push(n.href)])));

  React.useEffect(() => {
    if (!me) return;
    if (!me.workspace) { router.replace("/onboarding"); return; }
    if (!me.user.email_verified && cfg.data?.require_email_verification) router.replace("/verify-email");
    else if (!me.workspace.onboarding_completed_at && me.role?.key === "owner" && !me.workspace.is_demo) router.replace("/onboarding");
  }, [me, cfg.data, router]);
  React.useEffect(() => { if (me?.user.preferences?.sidebar_collapsed !== undefined && localStorage.getItem("sidebar-collapsed") === null) setCollapsed(!!me.user.preferences.sidebar_collapsed); }, [me?.user.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    const code = (error as { code?: string }).code;
    if (code === "unauthenticated" || code === "session_revoked" || code === "token_expired" || code === "invalid_token") { if (typeof window !== "undefined") window.location.href = `/login?next=${encodeURIComponent(pathname)}`; return null; }
    return <div className="flex min-h-dvh items-center justify-center"><ErrorState kind={(error as { status?: number }).status === 0 ? "network" : "unavailable"} onRetry={() => window.location.reload()} /></div>;
  }
  if (isLoading || !me?.workspace) return <div className="flex min-h-dvh"><div className="hidden w-[248px] border-r border-border bg-surface p-4 md:block"><Skeleton className="h-8 w-32" /><div className="mt-8 space-y-3">{Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} className="h-8" />)}</div></div><div className="flex-1 p-8"><Skeleton className="h-9 w-64" /><Skeleton className="mt-6 h-40" /><Skeleton className="mt-4 h-72" /></div></div>;

  const allowedWhenRestricted = pathname.startsWith("/app/billing") || pathname.startsWith("/app/settings/profile") || pathname.startsWith("/app/settings/security");
  return (
    <div className="flex min-h-dvh">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <ImpersonationBanner /><VerifyBanner /><TrialBanner />
        <Topbar />
        <main className="flex-1 pb-24 md:pb-0" id="main">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={pathname.split("/").slice(0, 3).join("/")} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18, ease: "easeOut" }}>
              {restricted && !allowedWhenRestricted ? <RestrictedScreen /> : children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <MobileNav />
      <div className="fixed bottom-20 right-4 z-30 md:hidden"><QuickCreateMenu variant="fab" /></div>
      <CommandPalette /><QuickCreateDrawer /><ShortcutsDialog />
      <ComposeEmail open={!!ui.compose} onOpenChange={(o) => !o && ui.closeCompose()} defaults={ui.compose?.defaults} />
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return <UIProvider><Shell>{children}</Shell></UIProvider>;
}
export { Menu, AlertTriangle };
