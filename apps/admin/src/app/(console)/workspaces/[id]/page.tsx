"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Ban, CalendarPlus, CircleDollarSign, LogIn, Play, Sliders, Tag, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import {
  Avatar, Badge, Button, Card, CardBody, CardHeader, ConfirmDialog, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Field, Input, NativeSelect, Progress, Skeleton,
  Table, TBody, TD, TH, THead, TR, Tabs, TabsContent, TabsList, TabsTrigger, Textarea, formatDate, timeAgo, useToast,
} from "@crm/ui";
import { PageHeader, Stat, StatusBadge, inr, minor } from "@/components/bits";
import { useStepUp } from "@/components/step-up";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";

type Detail = {
  id: string; name: string; slug: string; plan_key: string; status: string; status_label: string; subscription_status: string; billing_interval: string | null; trial_ends_at: string | null; current_period_end: string | null;
  grace_ends_at: string | null; cancel_at_period_end: boolean; credit_balance: number; limit_overrides: Record<string, number | null>; created_at: string; is_demo: boolean; industry: string | null; company_size: string | null; owner_id: string;
  access: { state: string; allowed: boolean; message?: string };
  counts: { contacts: number; leads: number; deals: number; users: number };
  usage: { key: string; label: string; used: number; limit: number | null }[];
  members: { user_id: string; name: string; email: string; role: string; status: string }[];
  subscriptions: { id: string; plan_key: string; interval: string; status: string; amount: number; current_period_end: string | null; cancel_at_period_end: boolean; provider: string; coupon_code: string | null }[];
  payments: { id: string; amount: number; refunded_amount: number; status: string; created_at: string; description: string | null; failure_reason: string | null }[];
  invoices: { id: string; number: string; total: number; status: string; created_at: string }[];
  integrations: { provider: string; status: string; mode: string }[];
};
type Dlg = "trial" | "plan" | "limits" | "credit" | "extend" | "suspend" | "delete" | "impersonate" | null;

export default function Page() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const can = useCan();
  const qc = useQueryClient();
  const toast = useToast();
  const stepUp = useStepUp();
  const [dlg, setDlg] = useState<Dlg>(null);
  const [imp, setImp] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["workspace", id], queryFn: () => api.get<Detail>(`${A}/workspaces/${id}`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["workspace", id] }); qc.invalidateQueries({ queryKey: ["workspaces"] }); };
  const reactivate = useMutation({ mutationFn: () => api.post(`${A}/workspaces/${id}/reactivate`), onSuccess: () => { toast.success("Workspace reactivated"); refresh(); }, onError: (e) => toast.error((e as Error).message) });
  const w = q.data;

  if (q.isError) return <ErrorState kind="unavailable" title="Couldn't load this workspace" onRetry={() => q.refetch()} action={<Button variant="secondary" onClick={() => router.push("/workspaces")}>Back to workspaces</Button>} />;
  if (!w) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-40" /></div>;
  const suspended = w.status === "suspended";

  return (
    <>
      <Link href="/workspaces" className="mb-3 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg"><ArrowLeft className="size-4" /> Workspaces</Link>
      <PageHeader
        title={<span className="flex items-center gap-3">{w.name}<StatusBadge status={w.status_label} />{w.is_demo && <Badge tone="outline">demo</Badge>}</span>}
        description={<>{w.slug} · created {formatDate(w.created_at)} · access: <span className="font-medium">{w.access.state}</span></>}
        actions={<>
          {can("support", "finance") && <Button variant="secondary" size="sm" onClick={() => setDlg("trial")}><CalendarPlus /> Extend trial</Button>}
          {can("finance") && <Button variant="secondary" size="sm" onClick={() => setDlg("plan")}><Tag /> Change plan</Button>}
          {can("support") && (suspended ? <Button variant="secondary" size="sm" loading={reactivate.isPending} onClick={() => reactivate.mutate()}><Play /> Reactivate</Button> : <Button variant="danger-soft" size="sm" onClick={() => setDlg("suspend")}><Ban /> Suspend</Button>)}
        </>}
      />
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Plan" value={<span className="capitalize">{w.plan_key.replace(/_/g, " ")}</span>} hint={w.billing_interval ?? "no billing interval"} />
        <Stat label={w.subscription_status === "trialing" ? "Trial ends" : "Renews"} value={formatDate(w.subscription_status === "trialing" ? w.trial_ends_at : w.current_period_end) || "—"} hint={w.cancel_at_period_end ? "Cancels at period end" : w.grace_ends_at ? `Grace until ${formatDate(w.grace_ends_at)}` : undefined} />
        <Stat label="Account credit" value={minor(w.credit_balance)} />
        <Stat label="Records" value={(w.counts.contacts + w.counts.leads + w.counts.deals).toLocaleString()} hint={`${w.counts.contacts} contacts · ${w.counts.leads} leads · ${w.counts.deals} deals`} />
      </div>
      <Tabs defaultValue="overview">
        <TabsList><TabsTrigger value="overview">Usage & limits</TabsTrigger><TabsTrigger value="members" count={w.members.length}>Members</TabsTrigger><TabsTrigger value="billing">Billing</TabsTrigger><TabsTrigger value="integrations" count={w.integrations.length}>Integrations</TabsTrigger><TabsTrigger value="danger">Admin actions</TabsTrigger></TabsList>
        <TabsContent value="overview" className="mt-5">
          <Card><CardHeader title="Usage against limits" description="Overrides replace the plan limit for this workspace only." actions={can("finance") && <Button size="sm" variant="secondary" onClick={() => setDlg("limits")}><Sliders /> Edit limits</Button>} />
            <CardBody><ul className="grid gap-5 sm:grid-cols-2">{w.usage.map((u) => {
              const pct = u.limit ? Math.min(100, (u.used / u.limit) * 100) : 0;
              return <li key={u.key}><div className="mb-1.5 flex justify-between text-sm"><span>{u.label}{w.limit_overrides[u.key] !== undefined && <Badge className="ml-2" tone="warning">override</Badge>}</span><span className="tabular text-fg-muted">{u.used.toLocaleString()} / {u.limit === null ? "∞" : u.limit.toLocaleString()}</span></div><Progress value={pct} tone={pct >= 100 ? "danger" : pct >= 85 ? "warning" : "primary"} label={u.label} /></li>;
            })}</ul></CardBody></Card>
        </TabsContent>
        <TabsContent value="members" className="mt-5"><Card className="overflow-x-auto"><Table><THead><TR><TH>Member</TH><TH>Role</TH><TH>Status</TH><TH /></TR></THead><TBody>{w.members.map((m) => (
          <TR key={m.user_id}><TD><div className="flex items-center gap-3"><Avatar name={m.name} size={30} /><div><p className="font-medium">{m.name}{m.user_id === w.owner_id && <Badge className="ml-2" tone="primary">owner</Badge>}</p><p className="text-xs text-fg-muted">{m.email}</p></div></div></TD>
            <TD className="capitalize">{m.role}</TD><TD><StatusBadge status={m.status} /></TD>
            <TD className="text-right">{can("support") && m.status === "active" && <Button size="xs" variant="secondary" onClick={() => { setImp(m.user_id); setDlg("impersonate"); }}><LogIn /> Impersonate</Button>}</TD></TR>))}</TBody></Table></Card></TabsContent>
        <TabsContent value="billing" className="mt-5 space-y-5">
          <Card><CardHeader title="Subscriptions" actions={can("finance") && w.subscriptions.some((s) => s.status === "active" || s.status === "past_due") && <Button size="sm" variant="secondary" onClick={() => setDlg("extend")}>Extend period</Button>} />
            <div className="overflow-x-auto pt-3">{w.subscriptions.length ? <Table><THead><TR><TH>Plan</TH><TH>Interval</TH><TH>Status</TH><TH className="text-right">Amount</TH><TH>Period end</TH><TH>Provider</TH></TR></THead><TBody>{w.subscriptions.map((s) => <TR key={s.id}><TD className="capitalize">{s.plan_key.replace(/_/g, " ")}{s.coupon_code && <Badge className="ml-2" tone="outline">{s.coupon_code}</Badge>}</TD><TD className="capitalize">{s.interval}</TD><TD><StatusBadge status={s.cancel_at_period_end ? "canceled" : s.status} /></TD><TD className="tabular text-right">{minor(s.amount)}</TD><TD>{formatDate(s.current_period_end)}</TD><TD>{s.provider}</TD></TR>)}</TBody></Table> : <EmptyState compact title="No subscriptions" description="This workspace has never paid." />}</div></Card>
          <Card><CardHeader title="Payments" />
            <div className="overflow-x-auto pt-3">{w.payments.length ? <Table><THead><TR><TH>Date</TH><TH>Description</TH><TH>Status</TH><TH className="text-right">Amount</TH><TH className="text-right">Refunded</TH></TR></THead><TBody>{w.payments.map((p) => <TR key={p.id}><TD>{formatDate(p.created_at, "datetime")}</TD><TD>{p.description ?? "—"}{p.failure_reason && <p className="text-xs text-danger">{p.failure_reason}</p>}</TD><TD><StatusBadge status={p.status} /></TD><TD className="tabular text-right">{minor(p.amount)}</TD><TD className="tabular text-right">{p.refunded_amount ? minor(p.refunded_amount) : "—"}</TD></TR>)}</TBody></Table> : <EmptyState compact title="No payments" />}</div></Card>
          <Card><CardHeader title="Invoices" />
            <div className="overflow-x-auto pt-3">{w.invoices.length ? <Table><THead><TR><TH>Number</TH><TH>Date</TH><TH>Status</TH><TH className="text-right">Total</TH></TR></THead><TBody>{w.invoices.map((i) => <TR key={i.id}><TD className="font-mono text-xs">{i.number}</TD><TD>{formatDate(i.created_at)}</TD><TD><StatusBadge status={i.status} /></TD><TD className="tabular text-right">{minor(i.total)}</TD></TR>)}</TBody></Table> : <EmptyState compact title="No invoices" />}</div></Card>
        </TabsContent>
        <TabsContent value="integrations" className="mt-5"><Card>{w.integrations.length ? <ul className="divide-y divide-border">{w.integrations.map((i) => <li key={i.provider} className="flex items-center justify-between px-5 py-3 text-sm"><span className="font-medium capitalize">{i.provider.replace(/_/g, " ")}</span><span className="flex items-center gap-2"><Badge tone="outline">{i.mode}</Badge><StatusBadge status={i.status} /></span></li>)}</ul> : <EmptyState compact title="No integrations connected" />}</Card></TabsContent>
        <TabsContent value="danger" className="mt-5">
          <Card><CardBody className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-medium">Adjust account credit</p><p className="text-sm text-fg-muted">Credit is applied automatically to the next invoice.</p></div>{can("finance") && <Button variant="secondary" onClick={() => setDlg("credit")}><CircleDollarSign /> Adjust credit</Button>}</div>
            <hr className="border-border" />
            <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-medium text-danger">Delete workspace</p><p className="text-sm text-fg-muted">Soft-deletes the workspace and signs everyone out. Data is retained for recovery until purged by an operator.</p></div>{can() && <Button variant="danger-soft" onClick={() => setDlg("delete")}><Trash2 /> Delete workspace</Button>}</div>
          </CardBody></Card>
        </TabsContent>
      </Tabs>

      <DaysDialog open={dlg === "trial"} onOpenChange={(o) => !o && setDlg(null)} title="Extend trial" max={90} cta="Extend trial" path={`${A}/workspaces/${id}/extend-trial`} onDone={refresh} note="Adds days to the current trial end (or restarts an expired trial)." />
      <DaysDialog open={dlg === "extend"} onOpenChange={(o) => !o && setDlg(null)} title="Extend subscription period" max={365} cta="Extend period" path={`${A}/workspaces/${id}/extend-subscription`} onDone={refresh} note="Pushes the renewal date out without charging." />
      <PlanDialog open={dlg === "plan"} onOpenChange={(o) => !o && setDlg(null)} id={id} current={w.plan_key} onDone={refresh} />
      <LimitsDialog open={dlg === "limits"} onOpenChange={(o) => !o && setDlg(null)} id={id} usage={w.usage} overrides={w.limit_overrides} onDone={refresh} />
      <CreditDialog open={dlg === "credit"} onOpenChange={(o) => !o && setDlg(null)} id={id} onDone={refresh} />
      <ConfirmDialog open={dlg === "suspend"} onOpenChange={(o) => !o && setDlg(null)} title="Suspend workspace?" description="Members keep their accounts but lose access to this workspace immediately. Data is untouched." confirmLabel="Suspend workspace" requireReason
        onConfirm={async ({ reason }) => { await api.post(`${A}/workspaces/${id}/suspend`, { confirm: true, reason }); toast.success("Workspace suspended"); refresh(); }} />
      <ConfirmDialog open={dlg === "delete"} onOpenChange={(o) => !o && setDlg(null)} title="Delete workspace?" description={<>This signs out every member and hides “{w.name}”. Data is retained for recovery.</>} confirmLabel="Delete workspace" typeToConfirm={w.name} requireReason
        onConfirm={async ({ reason, typed }) => { await stepUp(() => api.delete(`${A}/workspaces/${id}`, { confirm: true, confirm_text: typed, reason })); toast.success("Workspace deleted"); router.replace("/workspaces"); }} />
      <ImpersonateDialog open={dlg === "impersonate"} onOpenChange={(o) => !o && setDlg(null)} wid={id} uid={imp} name={w.members.find((m) => m.user_id === imp)?.name ?? ""} />
    </>
  );
}

function useAction<T>(fn: (v: T) => Promise<unknown>, onDone: () => void, close: () => void, msg: string) {
  const toast = useToast();
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({ mutationFn: fn, onSuccess: () => { toast.success(msg); onDone(); close(); }, onError: (e) => setErr((e as Error).message) });
  return { m, err, setErr };
}

function DaysDialog({ open, onOpenChange, title, max, cta, path, onDone, note }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; max: number; cta: string; path: string; onDone: () => void; note: string }) {
  const [days, setDays] = useState("7"); const [reason, setReason] = useState("");
  const { m, err } = useAction(() => api.post(path, { days: +days, reason }), onDone, () => onOpenChange(false), "Saved");
  const n = +days;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent title={title} description={note} size="sm">
      <div className="space-y-4"><Field label="Days" error={n < 1 || n > max ? `Enter 1–${max}` : undefined}><Input type="number" min={1} max={max} value={days} onChange={(e) => setDays(e.target.value)} /></Field>
        <Field label="Reason (optional)"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>{err && <p role="alert" className="text-sm text-danger">{err}</p>}</div>
      <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={m.isPending} disabled={!(n >= 1 && n <= max)} onClick={() => m.mutate(undefined)}>{cta}</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function PlanDialog({ open, onOpenChange, id, current, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; id: string; current: string; onDone: () => void }) {
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => api.get<{ plans: { key: string; name: string }[] }>(`${A}/plans`), enabled: open });
  const [plan, setPlan] = useState(current); const [interval, setInterval_] = useState("monthly"); const [reason, setReason] = useState("");
  const { m, err } = useAction(() => api.post(`${A}/workspaces/${id}/change-plan`, { plan_key: plan, interval, reason }), onDone, () => onOpenChange(false), "Plan changed");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent title="Change plan" description="A complimentary assignment — the customer isn't charged. Customers purchase through checkout." size="sm">
      <div className="space-y-4">
        <Field label="Plan"><NativeSelect value={plan} onChange={(e) => setPlan(e.target.value)}>{plans.data?.plans.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</NativeSelect></Field>
        <Field label="Billing interval"><NativeSelect value={interval} onChange={(e) => setInterval_(e.target.value)}><option value="monthly">Monthly (30 days)</option><option value="annual">Annual (365 days)</option></NativeSelect></Field>
        <Field label="Reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>{err && <p role="alert" className="text-sm text-danger">{err}</p>}</div>
      <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={m.isPending} onClick={() => m.mutate(undefined)}>Apply plan</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function LimitsDialog({ open, onOpenChange, id, usage, overrides, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; id: string; usage: Detail["usage"]; overrides: Record<string, number | null>; onDone: () => void }) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const [init, setInit] = useState(false);
  if (open && !init) { setVals(Object.fromEntries(Object.entries(overrides).map(([k, v]) => [k, v === null ? "unlimited" : String(v)]))); setInit(true); }
  if (!open && init) setInit(false);
  const { m, err } = useAction(() => {
    const limits: Record<string, number | null> = {};
    for (const [k, v] of Object.entries(vals)) { const t = v.trim().toLowerCase(); if (!t) continue; limits[k] = t === "unlimited" || t === "∞" ? null : Math.max(0, Math.floor(+t)); }
    return api.put(`${A}/workspaces/${id}/limits`, { limits });
  }, onDone, () => onOpenChange(false), "Limits updated");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent title="Limit overrides" description="Leave blank to use the plan's limit. Type “unlimited” to remove the cap." size="md">
      <div className="space-y-3">{usage.map((u) => <Field key={u.key} label={u.label} hint={`Plan limit: ${u.limit === null ? "unlimited" : u.limit}`}><Input value={vals[u.key] ?? ""} onChange={(e) => setVals((s) => ({ ...s, [u.key]: e.target.value }))} placeholder="Use plan limit" /></Field>)}{err && <p role="alert" className="text-sm text-danger">{err}</p>}</div>
      <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={m.isPending} onClick={() => m.mutate(undefined)}>Save overrides</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function CreditDialog({ open, onOpenChange, id, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; id: string; onDone: () => void }) {
  const [amt, setAmt] = useState("500"); const [reason, setReason] = useState("");
  const { m, err } = useAction(() => api.post(`${A}/workspaces/${id}/credit`, { amount: Math.round(+amt * 100), reason }), onDone, () => onOpenChange(false), "Credit adjusted");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent title="Adjust account credit" description="Enter rupees. Use a negative number to remove credit." size="sm">
      <div className="space-y-4"><Field label="Amount (₹)"><Input type="number" value={amt} onChange={(e) => setAmt(e.target.value)} /></Field><Field label="Reason" hint="Required — stored in the audit log."><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>{err && <p role="alert" className="text-sm text-danger">{err}</p>}</div>
      <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={m.isPending} disabled={!reason.trim() || !+amt} onClick={() => m.mutate(undefined)}>Apply</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function ImpersonateDialog({ open, onOpenChange, wid, uid, name }: { open: boolean; onOpenChange: (o: boolean) => void; wid: string; uid: string | null; name: string }) {
  const stepUp = useStepUp(); const toast = useToast();
  const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true); setErr(null);
    try { const r = await stepUp(() => api.post<{ url: string }>(`${A}/users/${uid}/impersonate`, { confirm: true, reason, workspace_id: wid })); window.open(r.url, "_blank", "noopener"); toast.success("Impersonation session opened"); onOpenChange(false); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent title={`Impersonate ${name}`} description="Opens the product as this user. The session is bannered and fully audit-logged." size="sm">
      <Field label="Reason" hint="Required — stored in the audit log."><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>{err && <p role="alert" className="mt-2 text-sm text-danger">{err}</p>}
      <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={busy} disabled={reason.trim().length < 3} onClick={go}>Open session</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
