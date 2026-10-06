"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Button, Card, CardHeader, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Field, Input, NativeSelect, Skeleton, SkeletonRows, Table, TBody, TD, TH, THead, TR, formatDate, useToast,
} from "@crm/ui";
import { PageHeader, Pager, Reveal, Stat, StatusBadge, inr, minor } from "@/components/bits";
import { useStepUp } from "@/components/step-up";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";
import type { Meta } from "@/lib/types";

type Overview = { revenue_total: number; revenue_this_month: number; mrr: number; arr: number; active_subscriptions: number; cancelled_subscriptions: number; failed_payments: number; past_due_workspaces: number; refunds_total: number; coupons: { active: number; redemptions: number }; plans: { key: string; name: string; active_subscriptions: number; mrr: number }[] };
type Pay = { id: string; workspace_id: string; workspace: string; amount: number; refunded_amount: number; currency: string; status: string; provider: string; description: string | null; failure_reason: string | null; created_at: string };

export default function Page() {
  const [status, setStatus] = useState(""); const [page, setPage] = useState(1);
  const [refund, setRefund] = useState<Pay | null>(null);
  const can = useCan();
  const ov = useQuery({ queryKey: ["billing-overview"], queryFn: () => api.get<Overview>(`${A}/billing/overview`) });
  const pays = useQuery({ queryKey: ["payments", status, page], queryFn: () => api.page<Pay>(`${A}/payments`, { status, page, per_page: 20 }), placeholderData: (p) => p });
  const o = ov.data;
  return (
    <>
      <PageHeader title="Billing & payments" description="Revenue, subscriptions and every charge across the platform." />
      {ov.isError ? <ErrorState compact kind="unavailable" onRetry={() => ov.refetch()} /> : (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          {[["MRR", o && inr(o.mrr)], ["ARR", o && inr(o.arr)], ["Revenue this month", o && inr(o.revenue_this_month)], ["Lifetime revenue", o && inr(o.revenue_total)], ["Active subscriptions", o?.active_subscriptions], ["Failed payments (30d)", o?.failed_payments], ["Past-due workspaces", o?.past_due_workspaces], ["Refunded", o && inr(o.refunds_total)]].map(([l, v], i) => (
            <Reveal key={l as string} delay={i * 0.03}><Stat label={l as string} value={v} loading={!o} tone={(l === "Failed payments (30d)" || l === "Past-due workspaces") && Number(v) > 0 ? "warning" : undefined} /></Reveal>))}
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card>
          <CardHeader title="Payments" actions={<NativeSelect className="h-8 w-36 text-[13px]" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Payment status"><option value="">All</option>{["succeeded", "failed", "refunded", "pending"].map((s) => <option key={s} value={s}>{s}</option>)}</NativeSelect>} />
          <div className="mt-3 overflow-x-auto">
            {pays.isError ? <ErrorState compact kind="unavailable" onRetry={() => pays.refetch()} /> : pays.isLoading ? <div className="p-4"><SkeletonRows rows={6} /></div> : !pays.data?.data.length ? <EmptyState compact title="No payments yet" description="Payments appear here when customers subscribe." /> : (
              <Table><THead><TR><TH>Date</TH><TH>Workspace</TH><TH>Status</TH><TH className="text-right">Amount</TH><TH className="text-right">Refunded</TH><TH /></TR></THead>
                <TBody>{pays.data.data.map((p) => (
                  <TR key={p.id}><TD className="whitespace-nowrap">{formatDate(p.created_at, "datetime")}</TD>
                    <TD><Link href={`/workspaces/${p.workspace_id}`} className="font-medium hover:text-primary">{p.workspace}</Link><p className="text-xs text-fg-subtle">{p.description ?? p.provider}</p></TD>
                    <TD><StatusBadge status={p.status} />{p.failure_reason && <p className="mt-0.5 max-w-[200px] truncate text-xs text-danger" title={p.failure_reason}>{p.failure_reason}</p>}</TD>
                    <TD className="tabular text-right">{minor(p.amount)}</TD><TD className="tabular text-right">{p.refunded_amount ? minor(p.refunded_amount) : "—"}</TD>
                    <TD className="text-right">{can("finance") && (p.status === "succeeded" || p.status === "refunded") && p.refunded_amount < p.amount && <Button size="xs" variant="secondary" onClick={() => setRefund(p)}><RotateCcw /> Refund</Button>}</TD></TR>))}</TBody></Table>)}
          </div>
          <Pager meta={pays.data?.meta as Meta | undefined} onPage={setPage} />
        </Card>
        <Card><CardHeader title="By plan" description="Active subscriptions and MRR" />
          <div className="p-5 pt-3">{!o ? <Skeleton className="h-40" /> : <ul className="divide-y divide-border">{o.plans.map((p) => <li key={p.key} className="flex items-center justify-between py-2.5 text-sm"><span>{p.name}<span className="ml-2 text-xs text-fg-subtle">{p.active_subscriptions} subs</span></span><span className="tabular font-medium">{p.mrr ? inr(p.mrr) : "—"}</span></li>)}</ul>}
            {o && <p className="mt-4 rounded-lg bg-bg-subtle p-3 text-xs text-fg-muted">{o.coupons.active} active coupons · {o.coupons.redemptions} redemptions · {o.cancelled_subscriptions} cancelled / cancelling</p>}</div></Card>
      </div>
      <RefundDialog pay={refund} onClose={() => setRefund(null)} />
    </>
  );
}

function RefundDialog({ pay, onClose }: { pay: Pay | null; onClose: () => void }) {
  const stepUp = useStepUp(); const toast = useToast(); const qc = useQueryClient();
  const [amount, setAmount] = useState(""); const [reason, setReason] = useState("");
  const left = pay ? (pay.amount - pay.refunded_amount) / 100 : 0;
  const m = useMutation({
    mutationFn: () => stepUp(() => api.post(`${A}/payments/${pay!.id}/refund`, { amount: amount ? Math.round(+amount * 100) : undefined, reason })),
    onSuccess: () => { toast.success("Refund issued"); qc.invalidateQueries({ queryKey: ["payments"] }); qc.invalidateQueries({ queryKey: ["billing-overview"] }); setAmount(""); setReason(""); onClose(); },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <Dialog open={!!pay} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Refund payment" description={pay ? `${pay.workspace} · up to ${inr(left)} can be refunded.` : undefined} size="sm">
        <div className="space-y-4">
          <Field label="Amount (₹)" hint="Leave empty to refund the full remaining amount."><Input type="number" min={1} max={left} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={String(left)} /></Field>
          <Field label="Reason" hint="Required — stored in the audit log."><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        </div>
        <DialogFooter><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="danger" loading={m.isPending} disabled={!reason.trim() || (!!amount && (+amount <= 0 || +amount > left))} onClick={() => m.mutate()}>Issue refund</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
