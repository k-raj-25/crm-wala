"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, ArrowRight, Check, CreditCard, Download, FileText, Sparkles, Tag } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Badge, Button, Card, CardBody, CardHeader, ConfirmDialog, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Field, Input, Progress, Segmented, Skeleton, Table, TD, TH, THead, TR, Textarea, cn, formatDate, formatMoney, fromMinor, humanDuration, useToast } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess, keys } from "@/lib/queries";
import type { Plan, Subscription } from "@/lib/types";

type Overview = { subscription: Subscription; plan: Plan | null; next_billing_date: string | null; amount: number | null; currency: string; pending_plan_key: string | null; payment_method: { brand?: string; last4?: string } | null; provider: string; credit_balance: number; usage: { key: string; label: string; used: number; limit: number | null }[] };
type Quote = { plan_key: string; plan_name: string; interval: string; currency: string; subtotal: number; discount: number; coupon: string | null; proration_credit: number; account_credit: number; tax_name: string; tax_percent: number; tax: number; total: number };
type Invoice = { id: string; number: string; status: string; total: number; currency: string; created_at: string; period_start: string | null; period_end: string | null };
type Payment = { id: string; amount: number; currency: string; status: string; description: string | null; created_at: string; failure_reason: string | null; refunded_amount: number };
const RANK: Record<string, number> = { starter: 1, growth: 2, business: 3 };

function StatusBanner({ o }: { o: Overview }) {
  const s = o.subscription; const a = s.access; let tone = "bg-primary-soft text-primary", icon = <Sparkles className="size-5" />, title = "", body = "";
  if (a.state === "restricted" || a.state === "suspended") { tone = "bg-danger-soft text-danger"; icon = <AlertTriangle className="size-5" />; title = a.reason === "trial_expired" ? "Your trial has ended." : a.reason === "payment_failed" ? "Payment failed — access paused." : "Your subscription has ended."; body = a.reason === "trial_expired" ? "Choose a plan to continue. Nothing has been deleted." : "Update billing to restore access. Your data is safe."; }
  else if (a.state === "grace") { tone = "bg-danger-soft text-danger"; icon = <AlertTriangle className="size-5" />; title = "We couldn't process your payment."; body = `You keep full access for ${humanDuration(a.seconds_left ?? 0)} while we retry. Update your payment method to avoid interruption.`; }
  else if (s.status === "trialing") { tone = "bg-warning-soft text-warning"; title = a.seconds_left != null && a.seconds_left < 86400 ? `Your trial ends in ${humanDuration(a.seconds_left)}.` : `Your free trial ends in ${humanDuration(a.seconds_left ?? 0)}.`; body = "Upgrade now to keep access to your CRM."; }
  else if (s.cancel_at_period_end || s.status === "canceled") { tone = "bg-warning-soft text-warning"; title = `Your plan ends on ${formatDate(s.current_period_end, "long")}.`; body = "Resume any time before then to keep everything as it is."; }
  else return null;
  return <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} role="status" className={cn("mb-6 flex items-start gap-3 rounded-xl p-4", tone)}>{icon}<div><p className="font-semibold">{title}</p><p className="text-sm opacity-90">{body}</p></div></motion.div>;
}

export default function BillingPage() {
  const { can, me } = useAccess(); const router = useRouter(); const toast = useToast(); const qc = useQueryClient();
  const ov = useQuery({ queryKey: ["billing"], enabled: can("billing.manage"), queryFn: () => api.get<Overview>("/api/v1/billing/overview") });
  const plans = useQuery({ queryKey: ["billing-plans"], enabled: can("billing.manage"), queryFn: () => api.get<Plan[]>("/api/v1/billing/plans") });
  const invoices = useQuery({ queryKey: ["invoices"], enabled: can("billing.manage"), queryFn: () => api.get<Invoice[]>("/api/v1/billing/invoices") });
  const payments = useQuery({ queryKey: ["payments"], enabled: can("billing.manage"), queryFn: () => api.get<Payment[]>("/api/v1/billing/payments") });
  const [interval, setIntervalV] = React.useState<"monthly" | "annual">("monthly"); const [coupon, setCoupon] = React.useState(""); const [target, setTarget] = React.useState<Plan | null>(null); const [quote, setQuote] = React.useState<Quote | null>(null); const [qerr, setQerr] = React.useState<string | null>(null); const [busy, setBusy] = React.useState(false);
  const [cancel, setCancel] = React.useState(false); const [sales, setSales] = React.useState(false); const [msg, setMsg] = React.useState("");
  const refresh = () => { ["billing", "invoices", "payments"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); qc.invalidateQueries({ queryKey: keys.me }); };
  const resume = useMutation({ mutationFn: () => api.post("/api/v1/billing/resume"), onSuccess: () => { refresh(); toast.success("Subscription resumed"); }, onError: (e) => toast.error("Couldn't resume", (e as Error).message) });
  const select = async (p: Plan, code = coupon) => { setTarget(p); setQerr(null); setQuote(null); try { setQuote(await api.post<Quote>("/api/v1/billing/quote", { plan_key: p.key, interval, coupon_code: code || undefined })); } catch (e) { setQerr((e as Error).message); if (code) { try { setQuote(await api.post<Quote>("/api/v1/billing/quote", { plan_key: p.key, interval })); } catch {} } } };
  const go = async () => {
    if (!target) return; setBusy(true);
    try { const r = await api.post<{ url?: string; scheduled?: boolean; effective?: string }>("/api/v1/billing/checkout", { plan_key: target.key, interval, coupon_code: quote?.coupon ?? undefined }); if (r.scheduled) { toast.success("Downgrade scheduled", `Takes effect on ${formatDate(r.effective, "long")}.`); setTarget(null); refresh(); } else if (r.url) { const u = new URL(r.url, window.location.origin); if (u.origin === window.location.origin) router.push(u.pathname + u.search); else window.location.href = r.url; } }
    catch (e) { toast.error("Couldn't start checkout", (e as Error).message); } finally { setBusy(false); }
  };
  const dl = async (i: Invoice) => { const r = await api.raw("GET", `/api/v1/billing/invoices/${i.id}/pdf`); if (!r.ok) return toast.error("Couldn't download"); const u = URL.createObjectURL(await r.blob()); const a = document.createElement("a"); a.href = u; a.download = `${i.number}.pdf`; a.click(); URL.revokeObjectURL(u); };
  if (!can("billing.manage")) return <PageContainer><ErrorState kind="permission" description="Only workspace owners can manage billing. Ask your owner to update the plan." /></PageContainer>;
  if (ov.isError) return <PageContainer><ErrorState kind="unavailable" onRetry={() => ov.refetch()} /></PageContainer>;
  const o = ov.data; const cur = o?.subscription.plan_key; const curPlan = plans.data?.find((p) => p.key === cur);
  const price = (p: Plan) => (interval === "annual" ? p.price_annual : p.price_monthly);
  const kind = (p: Plan) => (p.is_custom ? "sales" : p.key === cur && o?.subscription.status === "active" && o.subscription.interval === interval ? "current" : o?.subscription.status !== "active" ? "choose" : (RANK[p.key] ?? 9) < (RANK[cur ?? ""] ?? 0) ? "downgrade" : "upgrade");
  return (
    <PageContainer>
      <PageHeader title="Billing & plan" description="Manage your subscription, usage and invoices." />
      {o && <StatusBanner o={o} />}
      <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
        <Card><CardHeader title="Current plan" />
          <CardBody>{!o ? <Skeleton className="h-32" /> : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-2xl font-semibold tracking-tight">{o.subscription.plan_name}</p><p className="text-sm text-fg-muted">{o.subscription.status === "trialing" ? "Free trial" : o.subscription.interval === "annual" ? "Billed yearly" : "Billed monthly"}</p></div><Badge tone={o.subscription.status === "active" ? "success" : o.subscription.status === "trialing" ? "warning" : "danger"} dot>{o.subscription.status === "past_due" ? "Payment issue" : o.subscription.status.replace(/^\w/, (c) => c.toUpperCase())}</Badge></div>
              <dl className="grid gap-4 sm:grid-cols-3">
                <div><dt className="text-xs text-fg-muted">{o.subscription.status === "trialing" ? "Trial ends" : o.subscription.cancel_at_period_end ? "Access until" : "Next billing date"}</dt><dd className="mt-1 text-sm font-medium">{formatDate(o.subscription.status === "trialing" ? o.subscription.trial_ends_at : o.subscription.current_period_end, "long") }</dd></div>
                <div><dt className="text-xs text-fg-muted">Amount</dt><dd className="mt-1 text-sm font-medium">{o.amount ? `${formatMoney(fromMinor(o.amount), o.currency)} / ${o.subscription.interval === "annual" ? "yr" : "mo"}` : "—"}</dd></div>
                <div><dt className="text-xs text-fg-muted">Payment method</dt><dd className="mt-1 flex items-center gap-1.5 text-sm font-medium">{o.payment_method?.last4 ? <><CreditCard className="size-4 text-fg-subtle" /><span className="capitalize">{o.payment_method.brand}</span> •••• {o.payment_method.last4}</> : "—"}</dd></div>
              </dl>
              {o.pending_plan_key && <p className="rounded-lg bg-info-soft p-3 text-sm text-info">Your plan changes to <strong className="capitalize">{o.pending_plan_key}</strong> on {formatDate(o.subscription.current_period_end, "long")}. <button className="font-semibold underline" onClick={async () => { await api.post("/api/v1/billing/cancel-downgrade"); refresh(); }}>Keep current plan</button></p>}
              {o.credit_balance > 0 && <p className="text-sm text-success">Account credit: <strong>{formatMoney(fromMinor(o.credit_balance), o.currency)}</strong> (applied to your next invoice)</p>}
              <div className="flex flex-wrap gap-2 border-t border-border pt-4"><Button onClick={() => document.getElementById("plans")?.scrollIntoView({ behavior: "smooth" })}>{o.subscription.status === "active" ? "Change plan" : "Choose a plan"} <ArrowRight /></Button>
                {(o.subscription.cancel_at_period_end || o.subscription.status === "canceled") && o.subscription.status !== "expired" && <Button variant="secondary" onClick={() => resume.mutate()} loading={resume.isPending}>Resume subscription</Button>}
                {o.subscription.status === "active" && !o.subscription.cancel_at_period_end && <Button variant="ghost" className="text-danger" onClick={() => setCancel(true)}>Cancel subscription</Button>}</div>
            </div>)}</CardBody></Card>
        <Card><CardHeader title="Usage" description="Against your plan's limits" />
          <CardBody className="space-y-4">{!o ? <Skeleton className="h-40" /> : o.usage.map((u) => { const pct = u.limit ? (u.used / u.limit) * 100 : 0; return <div key={u.key}><div className="mb-1.5 flex items-center justify-between text-[13px]"><span>{u.label.replace(/^\w/, (c) => c.toUpperCase())}</span><span className="tabular text-fg-muted">{u.used.toLocaleString("en-IN")} {u.limit ? `/ ${u.limit.toLocaleString("en-IN")}` : "· unlimited"}</span></div>{u.limit ? <Progress value={u.used} max={u.limit} tone={pct >= 100 ? "danger" : pct >= 80 ? "warning" : "primary"} label={u.label} /> : <div className="h-1.5 rounded-full bg-gradient-to-r from-primary/30 to-primary/10" />}</div>; })}</CardBody></Card>
      </div>

      <section id="plans" className="mt-10 scroll-mt-20">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold tracking-tight">Compare plans</h2><p className="text-sm text-fg-muted">Upgrades apply instantly with prorated credit. Downgrades start at the end of your billing period.</p></div>
          <div className="flex items-center gap-3"><Segmented value={interval} onChange={setIntervalV} options={[{ value: "monthly", label: "Monthly" }, { value: "annual", label: "Annual" }]} />{interval === "annual" && <Badge tone="success">2 months free</Badge>}</div></div>
        <div className="mb-5 flex max-w-sm items-center gap-2"><Input icon={<Tag />} value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} placeholder="Have a coupon code?" aria-label="Coupon code" /></div>
        {!plans.data ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-80" />)}</div> : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{plans.data.map((p) => { const k = kind(p); const pr = price(p); return (
            <Card key={p.key} className={cn("flex flex-col p-6", k === "current" && "border-primary ring-1 ring-primary/30", p.key === "growth" && k !== "current" && "shadow-md")}>
              <div className="flex items-center justify-between"><h3 className="text-lg font-semibold">{p.name}</h3>{k === "current" && <Badge tone="primary">Current</Badge>}{p.key === "growth" && k !== "current" && <Badge tone="primary">Popular</Badge>}</div><p className="mt-1 min-h-10 text-[13px] text-fg-muted">{p.tagline}</p>
              <p className="my-4 text-3xl font-semibold tracking-tight tabular">{p.is_custom || pr == null ? "Custom" : <>{formatMoney(fromMinor(pr), p.currency)}<span className="text-sm font-normal text-fg-muted"> /{interval === "annual" ? "yr" : "mo"}</span></>}</p>
              <Button variant={k === "upgrade" || k === "choose" ? "primary" : "secondary"} disabled={k === "current"} onClick={() => (p.is_custom ? setSales(true) : select(p))}>{{ current: "Current plan", sales: "Talk to sales", downgrade: "Downgrade", upgrade: "Upgrade", choose: "Choose plan" }[k]}</Button>
              <ul className="mt-5 space-y-2 text-[13px]">{p.highlights.map((h) => <li key={h} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-success" />{h}</li>)}</ul></Card>); })}</div>)}
      </section>

      <div className="mt-10 grid gap-5 xl:grid-cols-2">
        <Card><CardHeader title="Invoices" /><CardBody className="px-0 pb-2">{invoices.isLoading ? <div className="px-5"><Skeleton className="h-24" /></div> : !invoices.data?.length ? <EmptyState compact icon={<FileText />} title="No invoices yet" description="Invoices appear after your first payment." /> : <Table><THead><TR><TH className="pl-5">Invoice</TH><TH>Date</TH><TH className="text-right">Total</TH><TH /></TR></THead><tbody>{invoices.data.map((i) => <TR key={i.id}><TD className="pl-5 font-medium">{i.number}{i.status === "void" && <Badge tone="neutral" className="ml-2">Void</Badge>}</TD><TD className="text-fg-muted">{formatDate(i.created_at)}</TD><TD className="tabular text-right">{formatMoney(fromMinor(i.total), i.currency, { decimals: 2 })}</TD><TD className="pr-5 text-right"><Button variant="ghost" size="icon-sm" aria-label={`Download ${i.number}`} onClick={() => dl(i)}><Download /></Button></TD></TR>)}</tbody></Table>}</CardBody></Card>
        <Card><CardHeader title="Payment history" /><CardBody className="px-0 pb-2">{payments.isLoading ? <div className="px-5"><Skeleton className="h-24" /></div> : !payments.data?.length ? <EmptyState compact icon={<CreditCard />} title="No payments yet" /> : <Table><THead><TR><TH className="pl-5">Description</TH><TH>Status</TH><TH className="pr-5 text-right">Amount</TH></TR></THead><tbody>{payments.data.map((p) => <TR key={p.id}><TD className="pl-5"><span className="block font-medium">{p.description ?? "Payment"}</span><span className="text-xs text-fg-muted">{formatDate(p.created_at, "datetime")}{p.failure_reason && ` · ${p.failure_reason}`}</span></TD><TD><Badge tone={p.status === "succeeded" ? "success" : p.status === "failed" ? "danger" : "neutral"}>{p.status}</Badge></TD><TD className="tabular pr-5 text-right">{formatMoney(fromMinor(p.amount), p.currency, { decimals: 2 })}</TD></TR>)}</tbody></Table>}</CardBody></Card>
      </div>

      <Dialog open={!!target} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent size="sm" title={`${target?.name} plan`} description={interval === "annual" ? "Billed yearly" : "Billed monthly"}>
          {!quote ? <Skeleton className="h-40" /> : (
            <div className="space-y-4"><dl className="space-y-2.5 text-sm">
              <div className="flex justify-between"><dt className="text-fg-muted">{quote.plan_name} ({interval})</dt><dd className="tabular">{formatMoney(fromMinor(quote.subtotal), quote.currency, { decimals: 2 })}</dd></div>
              {quote.discount > 0 && <div className="flex justify-between text-success"><dt>Coupon {quote.coupon}</dt><dd className="tabular">−{formatMoney(fromMinor(quote.discount), quote.currency, { decimals: 2 })}</dd></div>}
              {quote.proration_credit > 0 && <div className="flex justify-between text-success"><dt>Credit for unused time</dt><dd className="tabular">−{formatMoney(fromMinor(quote.proration_credit), quote.currency, { decimals: 2 })}</dd></div>}
              {quote.account_credit > 0 && <div className="flex justify-between text-success"><dt>Account credit</dt><dd className="tabular">−{formatMoney(fromMinor(quote.account_credit), quote.currency, { decimals: 2 })}</dd></div>}
              <div className="flex justify-between"><dt className="text-fg-muted">{quote.tax_name} ({quote.tax_percent}%)</dt><dd className="tabular">{formatMoney(fromMinor(quote.tax), quote.currency, { decimals: 2 })}</dd></div>
              <div className="flex justify-between border-t border-border pt-3 text-base font-semibold"><dt>Due today</dt><dd className="tabular">{formatMoney(fromMinor(quote.total), quote.currency, { decimals: 2 })}</dd></div></dl>
              {qerr && <p role="alert" className="text-sm text-danger">{qerr}</p>}
              {kind(target!) === "downgrade" && <p className="rounded-lg bg-info-soft p-3 text-[13px] text-info">Downgrades take effect at the end of your current period — you keep today's features until then.</p>}
              <p className="text-xs text-fg-subtle">You'll pay on a secure hosted page. Card details never touch our servers.</p></div>)}
          <DialogFooter><Button variant="secondary" onClick={() => setTarget(null)}>Cancel</Button><Button onClick={go} loading={busy} disabled={!quote}>{kind(target ?? ({} as Plan)) === "downgrade" ? "Schedule downgrade" : "Continue to payment"}<ArrowRight /></Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog open={cancel} onOpenChange={setCancel} title="Cancel your subscription?" confirmLabel="Cancel at period end" description={<>You'll keep full access until <strong>{formatDate(o?.subscription.current_period_end, "long")}</strong>. After that your workspace becomes read-only recovery mode — your data is never deleted and you can resubscribe any time.</>} onConfirm={async () => { await api.post("/api/v1/billing/cancel", {}); refresh(); toast.success("Subscription will end at period close"); }} />
      <Dialog open={sales} onOpenChange={setSales}><DialogContent size="sm" title="Talk to sales" description="Tell us what you need and we'll reach out within one business day."><Field label="Message"><Textarea rows={4} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Team size, integrations, security requirements…" /></Field><DialogFooter><Button variant="secondary" onClick={() => setSales(false)}>Cancel</Button><Button disabled={!msg.trim()} onClick={async () => { await api.post("/api/v1/billing/contact-sales", { message: msg }); setSales(false); setMsg(""); toast.success("Thanks — we'll be in touch"); }}>Send</Button></DialogFooter></DialogContent></Dialog>
      {me && null}
    </PageContainer>
  );
}


