"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Checkbox, Dialog, DialogContent, DialogFooter, ErrorState, Field, Input, Skeleton, Switch, Textarea, useToast } from "@crm/ui";
import { PageHeader, inr } from "@/components/bits";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";

type Plan = { key: string; name: string; tagline: string | null; currency: string; price_monthly: number | null; price_annual: number | null; limits: Record<string, number | null>; features: string[]; highlights: string[]; is_public: boolean; is_active: boolean; is_trial: boolean; is_custom: boolean; sort_order: number; workspaces: number };
type Resp = { plans: Plan[]; limit_keys: Record<string, string>; features: string[] };
const FEATURE_LABEL = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()).replace(/^Ai /, "AI ").replace("Whatsapp", "WhatsApp");

export default function Page() {
  const q = useQuery({ queryKey: ["plans"], queryFn: () => api.get<Resp>(`${A}/plans`) });
  const can = useCan();
  const [edit, setEdit] = useState<Plan | "new" | null>(null);
  return (
    <>
      <PageHeader title="Plans & limits" description="Pricing, limits and features are data — changes apply immediately, no deploy needed." actions={can("finance") && <Button onClick={() => setEdit("new")}><Plus /> New plan</Button>} />
      {q.isError ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} /> : !q.data ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3"><Skeleton className="h-72" /><Skeleton className="h-72" /><Skeleton className="h-72" /></div> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.data.plans.map((p) => (
            <Card key={p.key} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{p.name}</h3><p className="text-sm text-fg-muted">{p.tagline}</p></div>
                {can("finance") && <Button size="icon-sm" variant="ghost" aria-label={`Edit ${p.name}`} onClick={() => setEdit(p)}><Pencil /></Button>}</div>
              <p className="mt-4 text-3xl font-semibold tracking-tight tabular">{p.is_custom || p.price_monthly === null ? "Custom" : p.price_monthly === 0 ? "Free" : inr(p.price_monthly / 100)}{!!p.price_monthly && <span className="text-sm font-normal text-fg-muted"> /mo</span>}</p>
              {!!p.price_annual && <p className="text-xs text-fg-subtle">{inr(p.price_annual / 100)} billed annually</p>}
              <div className="mt-3 flex flex-wrap gap-1.5">{p.is_trial && <Badge tone="info">trial</Badge>}{!p.is_active && <Badge tone="warning">inactive</Badge>}{!p.is_public && <Badge tone="outline">hidden</Badge>}<Badge tone="neutral">{p.workspaces} workspaces</Badge></div>
              <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">{Object.entries(q.data.limit_keys).map(([k, label]) => <div key={k} className="flex justify-between gap-2"><dt className="truncate text-fg-muted first-letter:uppercase">{label}</dt><dd className="tabular font-medium">{p.limits[k] === null || p.limits[k] === undefined ? "∞" : p.limits[k]!.toLocaleString()}</dd></div>)}</dl>
              <ul className="mt-4 flex-1 space-y-1 border-t border-border pt-4 text-[13px] text-fg-muted">{p.features.map((f) => <li key={f} className="flex items-center gap-2"><Check className="size-3.5 text-success" />{FEATURE_LABEL(f)}</li>)}</ul>
            </Card>))}
        </div>
      )}
      {q.data && <PlanDialog key={edit === "new" ? "new" : edit?.key ?? "none"} plan={edit} onClose={() => setEdit(null)} data={q.data} />}
    </>
  );
}

function PlanDialog({ plan, onClose, data }: { plan: Plan | "new" | null; onClose: () => void; data: Resp }) {
  const isNew = plan === "new";
  const p = plan && plan !== "new" ? plan : null;
  const toast = useToast(); const qc = useQueryClient();
  const [f, setF] = useState(() => ({
    key: p?.key ?? "", name: p?.name ?? "", tagline: p?.tagline ?? "", price_monthly: p?.price_monthly != null ? String(p.price_monthly / 100) : "", price_annual: p?.price_annual != null ? String(p.price_annual / 100) : "",
    limits: Object.fromEntries(Object.keys(data.limit_keys).map((k) => [k, p ? (p.limits[k] === null || p.limits[k] === undefined ? "" : String(p.limits[k])) : ""])) as Record<string, string>,
    features: new Set(p?.features ?? []), highlights: (p?.highlights ?? []).join("\n"), is_public: p?.is_public ?? true, is_active: p?.is_active ?? true, is_custom: p?.is_custom ?? false,
  }));
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const [err, setErr] = useState<Record<string, string> | string | null>(null);
  const m = useMutation({
    mutationFn: () => {
      const body = {
        key: f.key, name: f.name, tagline: f.tagline || null, currency: "INR",
        price_monthly: f.is_custom || f.price_monthly === "" ? null : Math.round(+f.price_monthly * 100), price_annual: f.is_custom || f.price_annual === "" ? null : Math.round(+f.price_annual * 100),
        limits: Object.fromEntries(Object.entries(f.limits).map(([k, v]) => [k, v.trim() === "" ? null : Math.max(0, Math.floor(+v))])),
        features: [...f.features], highlights: f.highlights.split("\n").map((s) => s.trim()).filter(Boolean), is_public: f.is_public, is_active: f.is_active, is_custom: f.is_custom,
      };
      return isNew ? api.post(`${A}/plans`, body) : api.patch(`${A}/plans/${p!.key}`, body);
    },
    onSuccess: () => { toast.success(isNew ? "Plan created" : "Plan saved"); qc.invalidateQueries({ queryKey: ["plans"] }); onClose(); },
    onError: (e) => setErr((e as { details?: Record<string, string> }).details ?? (e as Error).message),
  });
  const fieldErr = (k: string) => (typeof err === "object" && err ? err[k] : undefined);
  return (
    <Dialog open={!!plan} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={isNew ? "New plan" : `Edit ${p?.name ?? "plan"}`} description="Prices are in rupees. Leave a limit empty for unlimited." size="lg">
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" error={fieldErr("name")}><Input value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label="Key" hint="Lowercase, permanent" error={fieldErr("key")}><Input value={f.key} disabled={!isNew} onChange={(e) => set("key", e.target.value.toLowerCase())} placeholder="growth_plus" /></Field>
          </div>
          <Field label="Tagline"><Input value={f.tagline} onChange={(e) => set("tagline", e.target.value)} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Monthly price (₹)" error={fieldErr("price_monthly")}><Input type="number" min={0} disabled={f.is_custom} value={f.price_monthly} onChange={(e) => set("price_monthly", e.target.value)} /></Field>
            <Field label="Annual price (₹ per year)" error={fieldErr("price_annual")}><Input type="number" min={0} disabled={f.is_custom} value={f.price_annual} onChange={(e) => set("price_annual", e.target.value)} /></Field>
          </div>
          <div><p className="mb-2 text-sm font-medium">Limits</p><div className="grid gap-3 sm:grid-cols-2">{Object.entries(data.limit_keys).map(([k, label]) => <Field key={k} label={label}><Input type="number" min={0} placeholder="Unlimited" value={f.limits[k]} onChange={(e) => setF((s) => ({ ...s, limits: { ...s.limits, [k]: e.target.value } }))} /></Field>)}</div></div>
          <div><p className="mb-2 text-sm font-medium">Features {fieldErr("features") && <span className="text-danger">— {fieldErr("features")}</span>}</p>
            <div className="grid gap-2 sm:grid-cols-2">{data.features.map((k) => <label key={k} className="flex items-center gap-2 text-sm"><Checkbox checked={f.features.has(k)} onCheckedChange={(c) => setF((s) => { const n = new Set(s.features); if (c) n.add(k); else n.delete(k); return { ...s, features: n }; })} aria-label={k} />{FEATURE_LABEL(k)}</label>)}</div></div>
          <Field label="Highlights" hint="One per line — shown on the pricing page."><Textarea rows={4} value={f.highlights} onChange={(e) => set("highlights", e.target.value)} /></Field>
          <div className="grid gap-3 sm:grid-cols-3">
            {([["is_public", "Show on pricing page"], ["is_active", "Available to buy"], ["is_custom", "Custom pricing (contact sales)"]] as const).map(([k, l]) => <label key={k} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm">{l}<Switch checked={f[k]} onCheckedChange={(c) => set(k, c)} aria-label={l} /></label>)}
          </div>
          {typeof err === "string" && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} disabled={!f.name || !f.key} onClick={() => { setErr(null); m.mutate(); }}>{isNew ? "Create plan" : "Save changes"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
