"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Field, Input, NativeSelect, SkeletonRows, Switch, Table, TBody, TD, TH, THead, TR, formatDate, useToast } from "@crm/ui";
import { PageHeader, inr } from "@/components/bits";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";

type Coupon = { id: string; code: string; description: string | null; percent_off: number | null; amount_off: number | null; duration: string; duration_months: number | null; max_redemptions: number | null; times_redeemed: number; valid_until: string | null; plan_keys: string[]; is_active: boolean };

export default function Page() {
  const q = useQuery({ queryKey: ["coupons"], queryFn: () => api.get<Coupon[]>(`${A}/coupons`) });
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => api.get<{ plans: { key: string; name: string; is_trial: boolean }[] }>(`${A}/plans`) });
  const can = useCan(); const toast = useToast(); const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const toggle = useMutation({ mutationFn: (c: Coupon) => api.patch(`${A}/coupons/${c.id}`, { is_active: !c.is_active }), onSuccess: () => qc.invalidateQueries({ queryKey: ["coupons"] }), onError: (e) => toast.error((e as Error).message) });
  return (
    <>
      <PageHeader title="Coupons" description="Discount codes customers can apply at checkout." actions={can("finance") && <Button onClick={() => setOpen(true)}><Plus /> New coupon</Button>} />
      <Card className="overflow-x-auto">
        {q.isError ? <ErrorState compact kind="unavailable" onRetry={() => q.refetch()} /> : q.isLoading ? <div className="p-4"><SkeletonRows rows={5} /></div> : !q.data?.length ? <EmptyState compact title="No coupons yet" description="Create a code to offer a discount." action={can("finance") && <Button onClick={() => setOpen(true)}><Plus /> New coupon</Button>} /> : (
          <Table><THead><TR><TH>Code</TH><TH>Discount</TH><TH>Duration</TH><TH>Redeemed</TH><TH>Valid until</TH><TH>Plans</TH><TH>Active</TH></TR></THead>
            <TBody>{q.data.map((c) => (
              <TR key={c.id}><TD><span className="font-mono font-medium">{c.code}</span>{c.description && <p className="text-xs text-fg-subtle">{c.description}</p>}</TD>
                <TD className="tabular font-medium">{c.percent_off ? `${c.percent_off}% off` : inr((c.amount_off ?? 0) / 100) + " off"}</TD>
                <TD className="capitalize">{c.duration === "repeating" ? `${c.duration_months} months` : c.duration}</TD>
                <TD className="tabular">{c.times_redeemed}{c.max_redemptions ? ` / ${c.max_redemptions}` : ""}</TD>
                <TD>{c.valid_until ? formatDate(c.valid_until) : "No expiry"}</TD>
                <TD>{c.plan_keys.length ? c.plan_keys.map((k) => <Badge key={k} className="mr-1" tone="outline">{k}</Badge>) : <span className="text-fg-subtle">All paid</span>}</TD>
                <TD><Switch checked={c.is_active} disabled={!can("finance")} onCheckedChange={() => toggle.mutate(c)} aria-label={`${c.code} active`} /></TD></TR>))}</TBody></Table>)}
      </Card>
      <CouponDialog open={open} onClose={() => setOpen(false)} plans={(plans.data?.plans ?? []).filter((p) => !p.is_trial)} />
    </>
  );
}

function CouponDialog({ open, onClose, plans }: { open: boolean; onClose: () => void; plans: { key: string; name: string }[] }) {
  const toast = useToast(); const qc = useQueryClient();
  const [f, setF] = useState({ code: "", description: "", kind: "percent", value: "20", duration: "once", months: "3", max: "", until: "", plans: [] as string[] });
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post(`${A}/coupons`, {
      code: f.code, description: f.description || null, percent_off: f.kind === "percent" ? +f.value : null, amount_off: f.kind === "amount" ? Math.round(+f.value * 100) : null,
      duration: f.duration, duration_months: f.duration === "repeating" ? +f.months : null, max_redemptions: f.max ? +f.max : null, valid_until: f.until ? new Date(f.until + "T23:59:59").toISOString() : null, plan_keys: f.plans,
    }),
    onSuccess: () => { toast.success("Coupon created"); qc.invalidateQueries({ queryKey: ["coupons"] }); onClose(); },
    onError: (e) => setErr((e as Error).message),
  });
  const set = (k: keyof typeof f, v: string) => setF((s) => ({ ...s, [k]: v }));
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="New coupon" size="md">
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2"><Field label="Code"><Input value={f.code} onChange={(e) => set("code", e.target.value.toUpperCase())} placeholder="LAUNCH20" /></Field><Field label="Description"><Input value={f.description} onChange={(e) => set("description", e.target.value)} /></Field></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Discount type"><NativeSelect value={f.kind} onChange={(e) => set("kind", e.target.value)}><option value="percent">Percentage</option><option value="amount">Fixed amount (₹)</option></NativeSelect></Field>
            <Field label={f.kind === "percent" ? "Percent off (1–100)" : "Amount off (₹)"}><Input type="number" min={1} value={f.value} onChange={(e) => set("value", e.target.value)} /></Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Applies for"><NativeSelect value={f.duration} onChange={(e) => set("duration", e.target.value)}><option value="once">First payment only</option><option value="repeating">A number of months</option><option value="forever">Forever</option></NativeSelect></Field>
            {f.duration === "repeating" && <Field label="Months"><Input type="number" min={1} max={36} value={f.months} onChange={(e) => set("months", e.target.value)} /></Field>}
          </div>
          <div className="grid gap-4 sm:grid-cols-2"><Field label="Max redemptions" hint="Empty = unlimited"><Input type="number" min={1} value={f.max} onChange={(e) => set("max", e.target.value)} /></Field><Field label="Valid until" hint="Empty = no expiry"><Input type="date" value={f.until} onChange={(e) => set("until", e.target.value)} /></Field></div>
          <Field label="Restrict to plans" hint="None selected = all paid plans"><div className="flex flex-wrap gap-2">{plans.map((p) => { const on = f.plans.includes(p.key); return <button key={p.key} type="button" aria-pressed={on} onClick={() => setF((s) => ({ ...s, plans: on ? s.plans.filter((k) => k !== p.key) : [...s.plans, p.key] }))} className={on ? "rounded-full bg-primary px-3 py-1 text-sm text-primary-fg" : "rounded-full border border-border px-3 py-1 text-sm text-fg-muted hover:bg-surface-hover"}>{p.name}</button>; })}</div></Field>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} disabled={f.code.length < 3 || !+f.value} onClick={() => { setErr(null); m.mutate(); }}>Create coupon</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
