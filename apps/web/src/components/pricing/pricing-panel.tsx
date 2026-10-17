"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, History, Lightbulb, Minus, Plus, TrendingDown, TrendingUp, Undo2 } from "lucide-react";
import * as React from "react";
import { Badge, Button, Card, ConfirmDialog, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Skeleton, cn, formatMoney, formatMoneyCompact, timeAgo, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { plural } from "@/lib/pricing";
import type { Evidence, PriceChange, Suggestion } from "@/lib/pricing";

type SuggestionsRes = { window_days: number; cooldown_days: number; can_apply: boolean; suggestions: Suggestion[] };

/** Same rounding as the server: nearest ₹1,000, the way price lists are written. */
const repriced = (p: number, pct: number) => Math.round((p * (1 + pct / 100)) / 1000) * 1000;
const range = (lo: number, hi: number) => (lo === hi ? formatMoneyCompact(lo) : `${formatMoneyCompact(lo)} to ${formatMoneyCompact(hi)}`);
const signed = (n: number) => `${n > 0 ? "+" : ""}${n}%`;

function Chips({ e }: { e: Evidence }) {
  const items = [
    [e.holds, plural(e.holds, "hold")], [e.booked_recently, `${e.booked_recently} booked`], [e.visits, plural(e.visits, "site visit")],
    [e.compared, `compared ${e.compared}×`], [e.interested, plural(e.interested, "enquiry", "enquiries")], [e.matched, `${plural(e.matched, "matching buyer")}`],
  ].filter(([n]) => n) as [number, string][];
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge tone="outline">{e.left} of {e.flats} left</Badge>
      {items.map(([, l]) => <Badge key={l} tone="neutral">{l}</Badge>)}
    </div>
  );
}

function SuggestionCard({ s, canApply, projectId }: { s: Suggestion; canApply: boolean; projectId: string }) {
  const qc = useQueryClient(); const toast = useToast();
  const [pct, setPct] = React.useState(s.pct);
  const [confirming, setConfirming] = React.useState(false);
  const up = s.rule === "raise_hot";
  const prices = s.units.map((u) => u.price);
  const lo = Math.min(...prices), hi = Math.max(...prices);
  const done = () => { ["pricing", "building", "project", "unit", "unit-history"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); };
  const apply = useMutation({
    mutationFn: () => api.post(`/api/v1/pricing/projects/${projectId}/apply`, { segment_key: s.segment_key, rule: s.rule, pct, headline: s.headline }),
    onSuccess: () => { done(); setConfirming(false); toast.success(`Prices updated ${signed(pct)}`, `${plural(s.units.length, "flat")}: ${s.segment_label}. We'll track how they sell.`); },
    onError: (e) => toast.error("Couldn't change the prices", (e as Error).message),
  });
  const dismiss = useMutation({
    mutationFn: () => api.post(`/api/v1/pricing/projects/${projectId}/dismiss`, { segment_key: s.segment_key, rule: s.rule, headline: s.headline }),
    onSuccess: () => { done(); toast.success("Price kept", "We won't suggest this again for 30 days."); },
    onError: (e) => toast.error("Couldn't save that", (e as Error).message),
  });
  const step = (d: number) => setPct((x) => { const v = Math.round((x + d) * 2) / 2; return v === 0 ? v + d : Math.max(-20, Math.min(20, v)); });
  return (
    <li className="p-4">
      <div className="flex gap-3">
        <span className={cn("mt-0.5 grid size-9 shrink-0 place-items-center rounded-full", up ? "bg-success-soft text-success" : "bg-warning-soft text-warning")}>{up ? <TrendingUp className="size-4" /> : <TrendingDown className="size-4" />}</span>
        <div className="min-w-0 flex-1 space-y-2.5">
          <p className="text-[15px] font-medium leading-snug">{s.headline}</p>
          <Chips e={s.evidence} />
          <p className="text-[13px] text-fg-muted">Flats {s.units.map((u) => u.number).join(", ")} · now {range(lo, hi)}<ArrowRight className="mx-1 inline size-3.5 align-[-2px]" /><b className="text-fg">{range(repriced(lo, pct), repriced(hi, pct))}</b></p>
          {canApply ? (
            <div className="flex flex-wrap items-center gap-2 pt-0.5">
              <div className="inline-flex h-9 items-center rounded-lg border border-border bg-surface" role="group" aria-label="Change by">
                <button type="button" className="grid h-full w-9 place-items-center text-fg-muted hover:text-fg" aria-label="Smaller change" onClick={() => step(-0.5)}><Minus className="size-4" /></button>
                <span className="w-14 text-center text-sm font-semibold tabular-nums" aria-live="polite">{signed(pct)}</span>
                <button type="button" className="grid h-full w-9 place-items-center text-fg-muted hover:text-fg" aria-label="Bigger change" onClick={() => step(0.5)}><Plus className="size-4" /></button>
              </div>
              <Button onClick={() => setConfirming(true)}><Check /> Apply</Button>
              <Button variant="ghost" loading={dismiss.isPending} onClick={() => dismiss.mutate()}>Keep price</Button>
            </div>
          ) : <p className="text-xs text-fg-subtle">Only the owner or an admin can change prices.</p>}
        </div>
      </div>
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent title={`Change ${plural(s.units.length, "price")} by ${signed(pct)}?`} description={`${s.segment_label}. Booked, sold and held flats keep their price. You can undo this later.`}>
          <div className="max-h-72 overflow-y-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-xs text-fg-muted"><tr><th scope="col" className="px-3 py-2 text-left font-medium">Flat</th><th scope="col" className="px-3 py-2 text-right font-medium">Now</th><th scope="col" className="px-3 py-2 text-right font-medium">New price</th></tr></thead>
              <tbody className="divide-y divide-border">{s.units.map((u) => <tr key={u.id}><td className="px-3 py-2 font-medium tabular-nums">{u.number}</td><td className="px-3 py-2 text-right tabular-nums text-fg-muted">{formatMoney(u.price)}</td><td className="px-3 py-2 text-right font-semibold tabular-nums">{formatMoney(repriced(u.price, pct))}</td></tr>)}</tbody>
            </table>
          </div>
          <DialogFooter><Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button><Button loading={apply.isPending} onClick={() => apply.mutate()}>Change prices</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  );
}

const VERDICT: Record<NonNullable<PriceChange["tracking"]>["verdict"], { label: string; tone: "success" | "danger" | "neutral" | "info" | "warning" }> = {
  too_early: { label: "Too early to tell", tone: "neutral" }, no_interest: { label: "Still no interest", tone: "warning" },
  faster: { label: "Selling faster", tone: "success" }, slower: { label: "Selling slower", tone: "danger" }, same: { label: "About the same", tone: "info" },
};
const pace = (p: { holds: number; booked: number }) => `${p.booked} booked, ${plural(p.holds, "hold")}`;

function ChangeRow({ c, canApply }: { c: PriceChange; canApply: boolean }) {
  const qc = useQueryClient(); const toast = useToast(); const [ask, setAsk] = React.useState(false);
  const undo = useMutation({
    mutationFn: () => api.post<{ restored: string[]; skipped: string[] }>(`/api/v1/pricing/changes/${c.id}/undo`),
    onSuccess: (r) => {
      ["pricing", "building", "project", "unit", "unit-history"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success("Old prices are back", r.skipped.length ? `${r.skipped.join(", ")} kept ${r.skipped.length === 1 ? "its" : "their"} price, changed by hand since.` : undefined);
    },
    onError: (e) => toast.error("Couldn't undo", (e as Error).message),
  });
  const t = c.tracking;
  return (
    <li className="px-4 py-3.5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
            <span className={cn(c.status === "undone" && "text-fg-muted line-through decoration-fg-subtle")}>{c.segment_label}</span>
            {c.status === "dismissed" ? <Badge tone="outline">Price kept</Badge> : <Badge tone={c.pct > 0 ? "success" : "warning"}>{signed(c.pct)}</Badge>}
            {c.status === "undone" && <Badge tone="neutral">Undone</Badge>}
            {t && c.status === "applied" && <Badge tone={VERDICT[t.verdict].tone} dot>{VERDICT[t.verdict].label}</Badge>}
          </p>
          {t && t.verdict !== "too_early" && <p className="mt-1 text-[13px] text-fg-muted">{t.days} days before: {pace(t.before)}. {t.days} days after: <b className="font-medium text-fg">{pace(t.after)}</b>.</p>}
          {t?.verdict === "too_early" && <p className="mt-1 text-[13px] text-fg-muted">We'll compare sales before and after once it has run for a week.</p>}
          <p className="mt-1 text-xs text-fg-subtle">{c.status === "dismissed" ? "Kept" : "Applied"} by {c.decided_by_name ?? "someone"} {timeAgo(c.created_at)}{c.units.length > 0 && <> · flats {c.units.map((u) => u.number).join(", ")}</>}{c.undone_at && <> · undone by {c.undone_by_name ?? "someone"} {timeAgo(c.undone_at)}</>}</p>
        </div>
        {canApply && c.status === "applied" && <Button size="sm" variant="ghost" onClick={() => setAsk(true)}><Undo2 /> Undo</Button>}
      </div>
      <ConfirmDialog open={ask} onOpenChange={setAsk} title="Put the old prices back?" description={`${plural(c.units.length, "flat")} go back to the price before this ${signed(c.pct)} change. A flat whose price was changed by hand since keeps that price.`}
        confirmLabel="Undo change" tone="primary" onConfirm={() => undo.mutateAsync().then(() => undefined)} />
    </li>
  );
}

/** The project's Pricing tab: what to charge, and what happened after the last changes. */
export function PricingPanel({ projectId }: { projectId: string }) {
  const sugg = useQuery({ queryKey: ["pricing", "suggestions", projectId], queryFn: () => api.get<SuggestionsRes>(`/api/v1/pricing/projects/${projectId}/suggestions`) });
  const changes = useQuery({ queryKey: ["pricing", "changes", projectId], queryFn: () => api.get<PriceChange[]>(`/api/v1/pricing/projects/${projectId}/changes`) });
  const canApply = !!sugg.data?.can_apply;
  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="border-b border-border p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><Lightbulb className="size-4 text-primary" /> What to charge</h2>
          <p className="mt-1 text-[13px] text-fg-muted">Read from holds, bookings, site visits, comparisons and enquiries in the last {sugg.data?.window_days ?? 60} days. Prices only change when you apply a suggestion.</p>
        </div>
        {sugg.isLoading ? <div className="space-y-3 p-4"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
          : sugg.isError ? <ErrorState compact kind="unavailable" onRetry={() => sugg.refetch()} />
          : !sugg.data?.suggestions.length ? <EmptyState compact icon={<Check />} title="Prices look right" description="No group of flats is selling much faster or slower than the rest. We'll suggest a change when that moves." />
          : <ul className="divide-y divide-border">{sugg.data.suggestions.map((s) => <SuggestionCard key={s.id} s={s} canApply={canApply} projectId={projectId} />)}</ul>}
      </Card>
      <Card className="overflow-hidden">
        <div className="border-b border-border p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><History className="size-4 text-primary" /> Price changes and what happened</h2>
          <p className="mt-1 text-[13px] text-fg-muted">For each change, the same number of days before and after: how many of those flats were held and booked.</p>
        </div>
        {changes.isLoading ? <div className="p-4"><Skeleton className="h-16" /></div>
          : !changes.data?.length ? <p className="p-4 text-sm text-fg-muted">No price changes yet.</p>
          : <ul className="divide-y divide-border">{changes.data.map((c) => <ChangeRow key={c.id} c={c} canApply={canApply} />)}</ul>}
      </Card>
    </div>
  );
}
