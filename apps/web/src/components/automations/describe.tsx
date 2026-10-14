"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Button, Card, Textarea, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { ACTION_COLORS, ACTION_ICONS, CHANNEL_LABEL, TRIGGER_ICON, type Graph, type Meta } from "./meta";

type Draft = { name: string; description: string; trigger_type: string; trigger_config: Record<string, unknown>; graph: Graph; steps: { id: string; label: string; action_type: string; config: Record<string, unknown> }[] };

const EXAMPLES = [
  "When a lead comes in, assign it round robin and create a call task for today",
  "When a lead comes in, tag it hot, warm or cold with AI and draft a WhatsApp reply for the owner",
  "When a deal moves to Won, notify the admins and log an activity",
  "When a form is submitted, wait 2 days and remind the owner to follow up",
];

const show = (v: unknown) => (typeof v === "string" ? CHANNEL_LABEL[v] ?? v.replace(/_/g, " ") : String(v));

/** "Describe it": the assistant turns a sentence into a paused automation the person reviews before it's created. */
export function DescribeAutomation() {
  const router = useRouter(); const qc = useQueryClient(); const toast = useToast();
  const [text, setText] = React.useState(""); const [busy, setBusy] = React.useState(false); const [saving, setSaving] = React.useState(false); const [err, setErr] = React.useState<string | null>(null); const [draft, setDraft] = React.useState<Draft | null>(null);
  const meta = useQuery({ queryKey: ["automation-meta"], enabled: !!draft, queryFn: () => api.get<Meta>("/api/v1/automations/meta") });
  const fieldLabel = (type: string, key: string) => meta.data?.actions.find((a) => a.key === type)?.fields.find((f) => f.key === key)?.label ?? key.replace(/_/g, " ");
  const trigLabel = (k: string) => meta.data?.triggers.find((t) => t.key === k)?.label ?? k.replace(".", " ").replace(/_/g, " ");
  const run = async () => { setBusy(true); setErr(null); try { setDraft(await api.post<Draft>("/api/v1/ai/automation-draft", { text: text.trim() })); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const create = async () => {
    if (!draft) return; setSaving(true);
    try { const a = await api.post<{ id: string }>("/api/v1/automations", { name: draft.name, description: draft.description, trigger_type: draft.trigger_type, trigger_config: draft.trigger_config, graph: draft.graph, is_active: false }); qc.invalidateQueries({ queryKey: ["automations"] }); toast.success("Automation created (paused)", "Check the steps, then switch it on."); router.push(`/app/automations/${a.id}`); }
    catch (e) { toast.error("Couldn't create", (e as Error).message); setSaving(false); }
  };
  const T = TRIGGER_ICON;
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /><h2 className="text-sm font-semibold">Describe it</h2><span className="text-xs text-fg-subtle">The assistant builds the steps. You review before anything is created.</span></div>
      {!draft ? (
        <div className="mt-3 space-y-3">
          <Textarea rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Describe what should happen, e.g. When a 99acres lead comes in, assign it round robin, create a call task and remind the owner after 2 days" aria-label="Describe the automation" />
          <div className="flex flex-wrap gap-1.5">{EXAMPLES.map((x) => <button key={x} type="button" onClick={() => setText(x)} className="rounded-full border border-border bg-surface-2 px-3 py-1 text-xs text-fg-muted hover:border-primary/40 hover:text-fg">{x}</button>)}</div>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
          <div className="flex justify-end"><Button onClick={run} loading={busy} disabled={text.trim().length < 8}><Sparkles /> Draft it</Button></div>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <div><p className="font-semibold">{draft.name}</p>{draft.description && <p className="text-[13px] text-fg-muted">{draft.description}</p>}</div>
          <ol className="space-y-2">
            <li className="flex items-start gap-3 rounded-lg border border-border p-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><T className="size-4" /></span><div><p className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">When</p><p className="text-sm font-medium">{trigLabel(draft.trigger_type)}</p>
              {Object.entries(draft.trigger_config ?? {}).filter(([, v]) => v !== "" && v != null).map(([k, v]) => <p key={k} className="text-xs text-fg-muted">{k.replace(/_/g, " ")}: {show(v)}</p>)}</div></li>
            {draft.steps.map((s, i) => { const I = ACTION_ICONS[s.action_type] ?? TRIGGER_ICON; const c = ACTION_COLORS[s.action_type] ?? "var(--fg-muted)"; const cfg = Object.entries(s.config ?? {}).filter(([, v]) => v !== "" && v != null); return (
              <li key={s.id} className="flex items-start gap-3 rounded-lg border border-border p-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-lg" style={{ background: `color-mix(in srgb, ${c} 15%, transparent)`, color: c }}><I className="size-4" /></span>
                <div className="min-w-0"><p className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">Step {i + 1}</p><p className="text-sm font-medium">{s.label}</p>
                  {cfg.map(([k, v]) => <p key={k} className="line-clamp-2 whitespace-pre-line text-xs text-fg-muted">{fieldLabel(s.action_type, k)}: {show(v)}</p>)}</div></li>); })}
          </ol>
          <p className="text-xs text-fg-subtle">It's created paused. You can change any step in the builder, then switch it on.</p>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setDraft(null)} disabled={saving}><X /> Cancel</Button><Button onClick={create} loading={saving}>Create (paused)</Button></div>
        </div>
      )}
    </Card>
  );
}
