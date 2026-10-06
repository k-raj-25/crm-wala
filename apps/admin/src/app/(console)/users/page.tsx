"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, KeyRound, LogIn, Search, Trash2, UserCheck } from "lucide-react";
import { useState } from "react";
import {
  Avatar, Badge, Button, Card, ConfirmDialog, Dialog, DialogContent, DialogFooter, Drawer, EmptyState, ErrorState, Field, Input, NativeSelect, SkeletonRows,
  Table, TBody, TD, TH, THead, TR, Textarea, formatDate, timeAgo, useDebounce, useToast,
} from "@crm/ui";
import { Pager, PageHeader, StatusBadge } from "@/components/bits";
import { useStepUp } from "@/components/step-up";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";
import type { Meta } from "@/lib/types";

type Row = { id: string; name: string; email: string; status: string; created_at: string; last_login_at: string | null; email_verified: boolean; mfa_enabled: boolean; company: string | null; workspace_id: string | null; plan: string | null; subscription_status: string | null; trial_status: string | null; trial_ends_at: string | null };
type Detail = Row & { active_sessions: number; last_login_ip: string | null; workspaces: { id: string; name: string; role: string; plan: string; status: string; is_owner: boolean }[]; recent_activity: { time: string; action: string; summary: string }[] };

export default function Page() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [plan, setPlan] = useState("");
  const [sub, setSub] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const dq = useDebounce(q, 300);
  const params = { q: dq, status, plan, subscription_status: sub, page, per_page: 25 };
  const users = useQuery({ queryKey: ["users", params], queryFn: () => api.page<Row>(`${A}/users`, params), placeholderData: (p) => p });
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => api.get<{ plans: { key: string; name: string }[] }>(`${A}/plans`), staleTime: 300_000 });
  const reset = (fn: () => void) => { fn(); setPage(1); };

  return (
    <>
      <PageHeader title="Users" description="Everyone who has signed up, across all workspaces." />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-border p-3">
          <div className="min-w-[220px] flex-1"><Input icon={<Search />} placeholder="Search name, email or company…" value={q} onChange={(e) => reset(() => setQ(e.target.value))} aria-label="Search users" /></div>
          <NativeSelect className="w-36" value={status} onChange={(e) => reset(() => setStatus(e.target.value))} aria-label="Status"><option value="">All statuses</option><option value="active">Active</option><option value="suspended">Suspended</option></NativeSelect>
          <NativeSelect className="w-40" value={plan} onChange={(e) => reset(() => setPlan(e.target.value))} aria-label="Plan"><option value="">All plans</option>{plans.data?.plans.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</NativeSelect>
          <NativeSelect className="w-44" value={sub} onChange={(e) => reset(() => setSub(e.target.value))} aria-label="Subscription"><option value="">Any subscription</option>{["trialing", "active", "past_due", "expired", "canceled"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</NativeSelect>
        </div>
        {users.isError ? <ErrorState compact kind="unavailable" onRetry={() => users.refetch()} /> : users.isLoading ? <div className="p-4"><SkeletonRows rows={8} /></div> : !users.data?.data.length ? <EmptyState compact title="No users match" description="Try a different search or clear the filters." /> : (
          <div className="overflow-x-auto">
            <Table>
              <THead><TR><TH>User</TH><TH>Company</TH><TH>Plan</TH><TH>Trial / status</TH><TH>Signed up</TH><TH>Last login</TH></TR></THead>
              <TBody>{users.data.data.map((u) => (
                <TR key={u.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(u.id)}>
                  <TD><button className="flex items-center gap-3 text-left" onClick={(e) => { e.stopPropagation(); setOpen(u.id); }}><Avatar name={u.name} size={32} /><span><span className="block font-medium">{u.name}</span><span className="block text-xs text-fg-muted">{u.email}</span></span></button></TD>
                  <TD className="text-fg-muted">{u.company ?? "—"}</TD>
                  <TD className="capitalize">{u.plan?.replace(/_/g, " ") ?? "—"}</TD>
                  <TD>{u.status === "suspended" ? <StatusBadge status="suspended" /> : <StatusBadge status={u.trial_status ?? u.subscription_status} />}</TD>
                  <TD className="text-fg-muted">{formatDate(u.created_at)}</TD>
                  <TD className="text-fg-muted">{u.last_login_at ? timeAgo(u.last_login_at) : "Never"}</TD>
                </TR>))}</TBody>
            </Table>
          </div>
        )}
        <Pager meta={users.data?.meta as Meta | undefined} onPage={setPage} />
      </Card>
      <UserDrawer id={open} onClose={() => setOpen(null)} />
    </>
  );
}

function UserDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const can = useCan();
  const stepUp = useStepUp();
  const d = useQuery({ queryKey: ["user", id], queryFn: () => api.get<Detail>(`${A}/users/${id}`), enabled: !!id });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["user", id] }); qc.invalidateQueries({ queryKey: ["users"] }); };
  const [dlg, setDlg] = useState<"suspend" | "delete" | "impersonate" | null>(null);
  const u = d.data;

  const reactivate = useMutation({ mutationFn: () => api.post(`${A}/users/${id}/reactivate`), onSuccess: () => { toast.success("User reactivated"); refresh(); }, onError: (e) => toast.error((e as Error).message) });
  const reset = useMutation({ mutationFn: () => api.post(`${A}/users/${id}/request-password-reset`), onSuccess: () => toast.success("Password reset email sent"), onError: (e) => toast.error((e as Error).message) });

  return (
    <Drawer open={!!id} onOpenChange={(o) => !o && onClose()} title={u?.name ?? "User"} description={u?.email} width={520}>
      {d.isLoading || !u ? <SkeletonRows rows={6} /> : (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={u.status} />{u.email_verified ? <Badge tone="success">Email verified</Badge> : <Badge tone="warning">Unverified</Badge>}{u.mfa_enabled && <Badge tone="primary">2FA on</Badge>}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            {[["Signed up", formatDate(u.created_at, "datetime")], ["Last login", u.last_login_at ? formatDate(u.last_login_at, "datetime") : "Never"], ["Last IP", u.last_login_ip ?? "—"], ["Active sessions", String(u.active_sessions)]].map(([k, v]) => <div key={k}><dt className="text-xs text-fg-subtle">{k}</dt><dd className="font-medium">{v}</dd></div>)}
          </dl>
          <section><h3 className="mb-2 text-sm font-semibold">Workspaces</h3>
            <ul className="divide-y divide-border rounded-lg border border-border">{u.workspaces.map((w) => <li key={w.id} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm"><div><a href={`/workspaces/${w.id}`} className="font-medium text-primary hover:underline">{w.name}</a><p className="text-xs text-fg-muted capitalize">{w.role}{w.is_owner ? " · owner" : ""} · {w.plan.replace(/_/g, " ")}</p></div><StatusBadge status={w.status} /></li>)}{!u.workspaces.length && <li className="px-3 py-3 text-sm text-fg-muted">No workspaces</li>}</ul></section>
          <section><h3 className="mb-2 text-sm font-semibold">Recent activity</h3>
            <ul className="space-y-2 text-sm">{u.recent_activity.map((a, i) => <li key={i} className="flex gap-3"><span className="w-20 shrink-0 text-xs text-fg-subtle">{timeAgo(a.time)}</span><span className="text-fg-muted">{a.summary || a.action}</span></li>)}{!u.recent_activity.length && <li className="text-fg-muted">Nothing yet</li>}</ul></section>
          <section className="space-y-2 border-t border-border pt-5">
            <h3 className="text-sm font-semibold">Actions</h3>
            <div className="flex flex-wrap gap-2">
              {can("support") && <Button variant="secondary" size="sm" onClick={() => setDlg("impersonate")} disabled={u.status !== "active" || !u.workspaces.length}><LogIn /> Impersonate</Button>}
              {can("support") && <Button variant="secondary" size="sm" loading={reset.isPending} onClick={() => reset.mutate()}><KeyRound /> Send password reset</Button>}
              {can("support") && (u.status === "active" ? <Button variant="danger-soft" size="sm" onClick={() => setDlg("suspend")}><Ban /> Suspend</Button> : <Button variant="secondary" size="sm" loading={reactivate.isPending} onClick={() => reactivate.mutate()}><UserCheck /> Reactivate</Button>)}
              {can() && <Button variant="danger-soft" size="sm" onClick={() => setDlg("delete")}><Trash2 /> Delete account</Button>}
            </div>
          </section>
          <ConfirmDialog open={dlg === "suspend"} onOpenChange={(o) => !o && setDlg(null)} title="Suspend this user?" description={<>{u.email} will be signed out everywhere and blocked from signing in until reactivated.</>} confirmLabel="Suspend user" requireReason
            onConfirm={async ({ reason }) => { await api.post(`${A}/users/${id}/suspend`, { confirm: true, reason }); toast.success("User suspended"); refresh(); }} />
          <ConfirmDialog open={dlg === "delete"} onOpenChange={(o) => !o && setDlg(null)} title="Delete this account?" description={<>This removes {u.email} and the workspaces they own (only if no one else is a member). Workspace data is retained for recovery. This can't be undone from the UI.</>} confirmLabel="Delete account" typeToConfirm={u.email} requireReason
            onConfirm={async ({ reason, typed }) => { await stepUp(() => api.delete(`${A}/users/${id}`, { confirm: true, confirm_text: typed, reason })); toast.success("Account deleted"); onClose(); qc.invalidateQueries({ queryKey: ["users"] }); }} />
          <ImpersonateDialog open={dlg === "impersonate"} onOpenChange={(o) => !o && setDlg(null)} user={u} />
        </div>
      )}
    </Drawer>
  );
}

function ImpersonateDialog({ open, onOpenChange, user }: { open: boolean; onOpenChange: (o: boolean) => void; user: Detail }) {
  const stepUp = useStepUp();
  const toast = useToast();
  const [ws, setWs] = useState(user.workspaces[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await stepUp(() => api.post<{ url: string }>(`${A}/users/${user.id}/impersonate`, { confirm: true, reason, workspace_id: ws }));
      window.open(r.url, "_blank", "noopener");
      toast.success("Impersonation session opened", "The grant expires in 2 minutes and is audit-logged.");
      onOpenChange(false);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Impersonate user" description={`You'll open the product signed in as ${user.name}. A banner shows the session is impersonated; every action is attributed in the audit log.`} size="sm">
        <div className="space-y-4">
          <Field label="Workspace"><NativeSelect value={ws} onChange={(e) => setWs(e.target.value)}>{user.workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</NativeSelect></Field>
          <Field label="Reason" hint="Recorded in the audit log. Link a ticket if you have one."><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={go} loading={busy} disabled={reason.trim().length < 3 || !ws}>Open session</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
