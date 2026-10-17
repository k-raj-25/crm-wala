"use client";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Check, ExternalLink, Pencil, Sparkles, Undo2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Badge, Button, Input, NativeSelect, Textarea, cn, useToast } from "@crm/ui";
import { type AiChange, type AiProposal, fillText, reportOutcome, runProposal, runUndo } from "@/lib/ai";

/** Options arrive as {value, label} or as [value, label] pairs (how the server writes them). */
const opts = (c: AiChange) => (c.options ?? []).map((o) => (Array.isArray(o) ? { value: String(o[0]), label: String(o[1]) } : o));
const show = (v: unknown) => v === null || v === undefined || v === "" ? "—" : Array.isArray(v) ? v.join(", ") || "—" : String(v);
const toLocal = (iso: unknown) => { if (!iso) return ""; const d = new Date(String(iso)); if (isNaN(+d)) return ""; const p = (n: number) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };
const fmtWhen = (iso: unknown) => { const d = new Date(String(iso)); return isNaN(+d) ? show(iso) : d.toLocaleString("en-IN", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }); };

function Editor({ c, value, onChange }: { c: AiChange; value: unknown; onChange: (v: unknown) => void }) {
  const id = `ai-${c.key}`;
  switch (c.input) {
    case "select": return <NativeSelect id={id} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>{opts(c).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</NativeSelect>;
    case "textarea": return <Textarea id={id} rows={3} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
    case "number": case "money": return <Input id={id} type="number" inputMode="decimal" value={value === null || value === undefined ? "" : String(value)} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />;
    case "datetime": return <Input id={id} type="datetime-local" value={toLocal(value)} onChange={(e) => onChange(e.target.value ? new Date(e.target.value).toISOString() : null)} />;
    case "date": return <Input id={id} type="date" value={String(value ?? "").slice(0, 10)} onChange={(e) => onChange(e.target.value || null)} />;
    case "tags": return <Input id={id} value={Array.isArray(value) ? value.join(", ") : String(value ?? "")} onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />;
    default: return <Input id={id} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
  }
}

/** "Do it for me" card: shows exactly what will change, lets people edit it, and runs it only when they press Approve. */
export function ProposalCard({ p, onDone, compact }: { p: AiProposal; onDone?: (state: "approved" | "cancelled") => void; compact?: boolean }) {
  const qc = useQueryClient(); const toast = useToast(); const router = useRouter();
  const initial = p.status === "approved" ? "done" : p.status ?? "open";
  const earlier = React.useRef(!!p.status).current; // settled before this page load, so there's nothing left to undo
  const [state, setState] = React.useState<"open" | "editing" | "running" | "done" | "cancelled" | "undone">(initial);
  const [vals, setVals] = React.useState<Record<string, unknown>>(() => Object.fromEntries(p.changes.map((c) => [c.key, c.to])));
  const [err, setErr] = React.useState<string | null>(null); const [result, setResult] = React.useState<string | null>(p.result_url ?? null);
  const editable = p.changes.some((c) => c.input !== "readonly");
  const changed = (c: AiChange) => JSON.stringify(vals[c.key]) !== JSON.stringify(c.to);
  const display = (c: AiChange) => changed(c) ? (c.input === "datetime" ? fmtWhen(vals[c.key]) : c.input === "select" ? opts(c).find((o) => o.value === vals[c.key])?.label ?? show(vals[c.key]) : show(vals[c.key])) : show(c.display_to);
  const refresh = () => qc.invalidateQueries();

  const approve = async () => {
    setState("running"); setErr(null);
    try {
      const results = await runProposal(p, vals);
      const filled = p.open_result ? fillText(p.open_result, results) : null; const open = filled && !filled.includes("undefined") ? filled : null;
      setState("done"); onDone?.("approved"); reportOutcome(p, "approved", undefined, open); refresh(); if (open) setResult(open);
      if (p.undo?.length) toast.toast({ tone: "success", title: "Done", description: p.title, duration: 30_000, action: { label: "Undo", onClick: async () => { try { await runUndo(p, results); setState("undone"); reportOutcome(p, "undone"); refresh(); toast.success("Undone"); } catch (e) { toast.error("Couldn't undo", (e as Error).message); } } } });
      else toast.success("Done", p.title);
    } catch (e) { const m = (e as Error).message; setErr(m); setState("open"); reportOutcome(p, "failed", m); refresh(); }
  };
  const cancel = () => { setState("cancelled"); onDone?.("cancelled"); reportOutcome(p, "cancelled"); };

  if (p.kind === "navigate") return <Link href={p.url ?? "/app"} className="flex items-center gap-3 rounded-xl border border-primary/30 bg-primary-soft/40 px-4 py-3 hover:bg-primary-soft"><Sparkles className="size-4 shrink-0 text-primary" /><span className="min-w-0 flex-1"><span className="block text-sm font-semibold">{p.title}</span>{p.description && <span className="block text-xs text-fg-muted">{p.description}</span>}</span><span className="text-xs font-medium text-primary">Take me there →</span></Link>;
  if (state === "cancelled") return <p className="flex items-center gap-1.5 rounded-xl border border-dashed border-border px-3 py-2 text-xs text-fg-subtle"><X className="size-3.5" /> Cancelled: {p.title}</p>;
  return (
    <div className={cn("overflow-hidden rounded-xl border bg-surface shadow-xs", state === "done" ? "border-success/40" : state === "undone" ? "border-border opacity-70" : "border-primary/30")}>
      <div className={cn("flex items-start gap-2.5 px-4 py-3", state === "done" ? "bg-success-soft/50" : "bg-primary-soft/40")}>
        <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full", state === "done" ? "bg-success text-white" : "bg-primary text-primary-fg")}>{state === "done" ? <Check className="size-3.5" /> : <Sparkles className="size-3.5" />}</span>
        <div className="min-w-0 flex-1"><p className="text-sm font-semibold">{p.title}</p>{p.description && <p className="mt-0.5 text-xs text-fg-muted">{p.description}</p>}
          {p.record && <Link href={p.record.url ?? "#"} className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">{p.record.name}<ExternalLink className="size-3" /></Link>}</div>
        {state === "done" && <Badge tone="success">Done</Badge>}{state === "undone" && <Badge>Undone</Badge>}
      </div>
      {p.changes.length > 0 && <dl className="divide-y divide-border px-4">{p.changes.map((c) => (
        <div key={c.key} className="grid gap-1 py-2.5 text-[13px] sm:grid-cols-[130px_1fr] sm:items-center">
          <dt className="text-fg-muted"><label htmlFor={`ai-${c.key}`}>{c.label}</label></dt>
          <dd className="min-w-0">{state === "editing" && c.input !== "readonly" ? <Editor c={c} value={vals[c.key]} onChange={(v) => setVals((s) => ({ ...s, [c.key]: v }))} /> : (
            <span className="flex flex-wrap items-center gap-1.5">{c.from !== null && c.from !== undefined && c.from !== "" && c.input !== "readonly" && <><span className="text-fg-subtle line-through">{show(c.display_from)}</span><ArrowRight className="size-3 text-fg-subtle" /></>}<span className={cn("font-medium", c.input === "textarea" && "whitespace-pre-wrap font-normal")}>{display(c)}</span></span>)}</dd>
        </div>))}</dl>}
      {!!p.items?.length && <ul className={cn("mx-4 my-2 overflow-y-auto rounded-lg border border-border text-[13px]", compact ? "max-h-32" : "max-h-48")}>{p.items.map((it) => <li key={it.id} className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5 last:border-0">{it.url ? <Link href={it.url} className="truncate hover:text-primary">{it.name}</Link> : <span className="truncate">{it.name}</span>}{it.hint && <span className="shrink-0 text-xs text-fg-subtle">{it.hint}</span>}</li>)}</ul>}
      {!!p.duplicates?.length && state !== "done" && <div className="mx-4 my-2 rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">Already in your CRM: {p.duplicates.map((d, i) => <React.Fragment key={d.id}>{i > 0 && ", "}<Link href={d.url} className="font-medium underline">{d.name}</Link></React.Fragment>)}</div>}
      {p.warning && state !== "done" && <p className="mx-4 my-2 flex items-start gap-1.5 text-xs text-warning"><AlertTriangle className="mt-px size-3.5 shrink-0" />{p.warning}</p>}
      {err && <p role="alert" className="mx-4 my-2 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{err}</p>}
      <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-2.5">
        {state === "open" || state === "editing" || state === "running" ? <>
          <Button size="sm" onClick={approve} loading={state === "running"}><Check /> {state === "editing" ? "Save & approve" : "Approve"}</Button>
          {editable && state !== "editing" && <Button size="sm" variant="secondary" onClick={() => setState("editing")}><Pencil /> Edit</Button>}
          <Button size="sm" variant="ghost" onClick={cancel}>Cancel</Button>
        </> : state === "done" ? <>
          {result && <Button size="sm" variant="secondary" onClick={() => router.push(result)}>Open <ArrowRight /></Button>}
          {p.url && !result && <Button size="sm" variant="secondary" asChild><Link href={p.url}>Open <ArrowRight /></Link></Button>}
          <span className="text-xs text-fg-subtle">{earlier ? "Approved earlier." : p.undo?.length ? <span className="inline-flex items-center gap-1"><Undo2 className="size-3" /> You can undo from the message at the bottom for 30 seconds.</span> : "Saved."}</span>
        </> : <span className="text-xs text-fg-subtle">This change was undone.</span>}
      </div>
    </div>
  );
}

export function ProposalList({ items, compact }: { items?: AiProposal[] | null; compact?: boolean }) {
  if (!items?.length) return null;
  return <div className="space-y-2.5">{items.map((p) => <ProposalCard key={p.id} p={p} compact={compact} />)}</div>;
}
