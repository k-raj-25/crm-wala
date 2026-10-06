"use client";
import { Background, BackgroundVariant, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowDown, ArrowLeft, ArrowUp, CheckCircle2, FlaskConical, History, Plus, Save, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { Badge, Button, Card, ErrorState, Field as FormField, Input, NativeSelect, Skeleton, Switch, Textarea, cn, formatDate, timeAgo, useTheme, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { MemberSelect } from "../forms/fields";
import { PageContainer } from "../shell/page";
import { ACTION_COLORS, ACTION_ICONS, TRIGGER_ICON, TEMPLATES, fromGraph, toGraph, uid, type Field, type Graph, type Meta, type Step } from "./meta";

type Auto = { id: string; name: string; description: string | null; trigger_type: string; trigger_config: Record<string, unknown>; graph: Graph; is_active: boolean; run_count: number };
type Run = { id: string; status: string; created_at: string; steps: { node_id: string; type: string; status: string; detail: string }[]; error: string | null; trigger_payload: Record<string, unknown> };

function FlowNode({ data, selected }: NodeProps<Node<{ icon: React.ElementType; color: string; kicker: string; title: string; summary?: string; status?: string; first?: boolean }>>) {
  const I = data.icon;
  return (
    <div className={cn("w-[280px] rounded-xl border bg-surface p-3.5 shadow-sm transition-all", selected ? "border-primary ring-2 ring-primary/25" : "border-border hover:border-border-strong")}>
      {!data.first && <Handle type="target" position={Position.Top} className="!size-2 !border-0 !bg-border-strong" />}
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg" style={{ background: `color-mix(in srgb, ${data.color} 15%, transparent)`, color: data.color }}><I className="size-[18px]" /></span>
        <div className="min-w-0 flex-1"><p className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">{data.kicker}</p><p className="truncate text-sm font-semibold">{data.title}</p>{data.summary && <p className="mt-0.5 line-clamp-2 text-xs text-fg-muted">{data.summary}</p>}</div>
        {data.status === "done" && <CheckCircle2 className="size-4 shrink-0 text-success" />}{data.status === "failed" && <XCircle className="size-4 shrink-0 text-danger" />}
      </div>
      <Handle type="source" position={Position.Bottom} className="!size-2 !border-0 !bg-border-strong" />
    </div>
  );
}
const nodeTypes = { flow: FlowNode };

function ConfigField({ f, value, onChange }: { f: Field; value: unknown; onChange: (v: unknown) => void }) {
  const v = value ?? f.default ?? "";
  if (f.type === "textarea") return <Textarea rows={5} value={v as string} onChange={(e) => onChange(e.target.value)} />;
  if (f.type === "number") return <Input type="number" min={0} value={v as number} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />;
  if (f.type === "select") return <NativeSelect value={v as string} onChange={(e) => onChange(e.target.value)}>{f.options!.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}</NativeSelect>;
  if (f.type === "user") return <MemberSelect value={(v as string) || null} onChange={(x) => onChange(x)} noneLabel="Choose person" />;
  return <Input value={v as string} onChange={(e) => onChange(e.target.value)} />;
}

function Builder({ initial, meta, isNew }: { initial: Auto | null; meta: Meta; isNew: boolean }) {
  const router = useRouter(); const qc = useQueryClient(); const toast = useToast(); const { resolved } = useTheme(); const { can } = useAccess();
  const seed = initial ? fromGraph(initial.graph) : { trigger: "lead.created", triggerConfig: {}, steps: [] as Step[] };
  const [name, setName] = React.useState(initial?.name ?? "Untitled automation"); const [trigger, setTrigger] = React.useState(seed.trigger); const [tConfig, setTConfig] = React.useState(seed.triggerConfig); const [steps, setSteps] = React.useState<Step[]>(seed.steps);
  const [active, setActive] = React.useState(initial?.is_active ?? false); const [sel, setSel] = React.useState<string>("trigger"); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  const [test, setTest] = React.useState<{ steps: { node_id: string; type: string; status: string; detail: string }[] } | null>(null); const [tab, setTab] = React.useState<"edit" | "runs">("edit");
  const id = initial?.id; const dirty = React.useRef(false); const mark = () => { dirty.current = true; };
  const canEdit = can(isNew ? "automations.create" : "automations.update");
  const runs = useQuery({ queryKey: ["automation-runs", id], enabled: !!id && tab === "runs", queryFn: () => api.get<Run[]>(`/api/v1/automations/${id}/runs`) });
  const trig = meta.triggers.find((t) => t.key === trigger)!; const aMeta = (k: string) => meta.actions.find((a) => a.key === k)!;
  const results = new Map((test?.steps ?? []).map((s) => [s.node_id, s]));

  const summary = (s: Step) => { const c = s.config; switch (s.action_type) { case "send_email": return `${(c.to as string) === "owner" ? "To owner" : "To the record"}: ${(c.subject as string) ?? ""}`; case "create_task": return `${(c.title as string) ?? ""} · due in ${c.due_in_days ?? 1}d`; case "delay": return `Wait ${c.amount ?? 1} ${c.unit ?? "days"}`; case "assign_user": return c.strategy === "user" ? "Specific person" : "Round robin"; case "add_tag": return `Tag “${(c.tag as string) ?? ""}”`; case "change_status": return `→ ${(c.value as string) ?? ""}`; case "send_notification": return (c.title as string) ?? ""; case "webhook": return (c.url as string) ?? ""; default: return (c.title as string) ?? ""; } };
  const nodes: Node[] = [{ id: "trigger", type: "flow", position: { x: 0, y: 0 }, draggable: false, selected: sel === "trigger", data: { icon: TRIGGER_ICON, color: "var(--series-1)", kicker: "When", title: trig.label, summary: trigger === "deal.stage_changed" && tConfig.stage ? `Moved to ${tConfig.stage}` : undefined, first: true } },
    ...steps.map((s, i) => ({ id: s.id, type: "flow", position: { x: 0, y: (i + 1) * 150 }, draggable: false, selected: sel === s.id, data: { icon: ACTION_ICONS[s.action_type], color: ACTION_COLORS[s.action_type], kicker: "Then", title: aMeta(s.action_type).label, summary: summary(s), status: results.get(s.id)?.status } }))];
  const edges = nodes.slice(1).map((n, i) => ({ id: `e${i}`, source: nodes[i].id, target: n.id, markerEnd: { type: MarkerType.ArrowClosed }, animated: active, style: { strokeWidth: 1.6 } }));

  const add = (type: string) => { const a = aMeta(type); const config = Object.fromEntries(a.fields.filter((f) => f.default !== undefined).map((f) => [f.key, f.default])); const s = { id: uid(), action_type: type, config }; setSteps((p) => { const idx = sel === "trigger" ? p.length : p.findIndex((x) => x.id === sel); const n = [...p]; n.splice(sel === "trigger" || idx < 0 ? p.length : idx + 1, 0, s); return n; }); setSel(s.id); mark(); setTest(null); };
  const move = (i: number, d: number) => { setSteps((p) => { const n = [...p]; [n[i], n[i + d]] = [n[i + d], n[i]]; return n; }); mark(); };
  const remove = (sid: string) => { setSteps((p) => p.filter((s) => s.id !== sid)); setSel("trigger"); mark(); };
  const payload = () => ({ name, trigger_type: trigger, trigger_config: tConfig, graph: toGraph(trigger, tConfig, steps), is_active: active });
  const save = async (activate?: boolean) => {
    setBusy(true); setErr(null);
    try {
      const body = { ...payload(), ...(activate !== undefined ? { is_active: activate } : {}) };
      const a = id ? await api.patch<Auto>(`/api/v1/automations/${id}`, body) : await api.post<Auto>("/api/v1/automations", body);
      qc.invalidateQueries({ queryKey: ["automations"] }); dirty.current = false; setActive(a.is_active); toast.success(id ? "Automation saved" : "Automation created");
      if (!id) router.replace(`/app/automations/${a.id}`);
    } catch (e) { setErr((e as Error).message); toast.error("Couldn't save", (e as Error).message); } finally { setBusy(false); }
  };
  const runTest = async () => { if (!id) { await save(); return; } if (dirty.current) await save(); try { setTest(await api.post(`/api/v1/automations/${id}/test`, { name: "Sample Lead" })); } catch (e) { toast.error("Test failed", (e as Error).message); } };
  const selStep = steps.find((s) => s.id === sel); const selIdx = steps.findIndex((s) => s.id === sel);

  return (
    <div className="flex h-[calc(100dvh-56px)] flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-3 sm:px-6">
        <Button variant="ghost" size="icon-sm" asChild aria-label="Back"><Link href="/app/automations"><ArrowLeft /></Link></Button>
        <Input value={name} onChange={(e) => { setName(e.target.value); mark(); }} className="h-9 max-w-xs border-transparent bg-transparent text-base font-semibold shadow-none hover:border-border" aria-label="Automation name" disabled={!canEdit} />
        <div className="ml-auto flex items-center gap-2">
          <div className="hidden rounded-md bg-bg-subtle p-0.5 sm:flex">{(["edit", "runs"] as const).map((t) => <button key={t} disabled={t === "runs" && !id} onClick={() => setTab(t)} className={cn("flex items-center gap-1.5 rounded-[7px] px-3 py-1 text-[13px] font-medium disabled:opacity-40", tab === t ? "bg-surface shadow-xs" : "text-fg-muted")}>{t === "runs" && <History className="size-3.5" />}{t === "edit" ? "Builder" : "Run history"}</button>)}</div>
          <label className="flex items-center gap-2 text-sm text-fg-muted"><Switch checked={active} onCheckedChange={(v) => { setActive(v); if (id) save(v); else mark(); }} disabled={!canEdit || (steps.length === 0)} aria-label="Active" />{active ? "Active" : "Paused"}</label>
          <Button variant="secondary" onClick={runTest} disabled={!canEdit || steps.length === 0}><FlaskConical /> Test</Button>
          <Button onClick={() => save()} loading={busy} disabled={!canEdit}><Save /> Save</Button>
        </div>
      </div>
      {err && <p role="alert" className="bg-danger-soft px-6 py-2 text-sm text-danger">{err}</p>}
      {tab === "runs" ? (
        <div className="flex-1 overflow-y-auto p-6"><div className="mx-auto max-w-3xl space-y-3">{runs.isLoading ? <Skeleton className="h-24" /> : !runs.data?.length ? <p className="py-16 text-center text-sm text-fg-muted">No runs yet. Runs appear when the trigger fires.</p> : runs.data.map((r) => (
          <Card key={r.id} className="p-4"><div className="flex items-center justify-between"><Badge tone={r.status === "completed" ? "success" : r.status === "failed" ? "danger" : r.status === "waiting" ? "warning" : "info"} dot>{r.status}</Badge><span className="text-xs text-fg-subtle">{formatDate(r.created_at, "datetime")} · {timeAgo(r.created_at)}</span></div>
            <ol className="mt-3 space-y-1.5">{r.steps.map((s, i) => <li key={i} className="flex items-center gap-2 text-[13px]">{s.status === "failed" ? <XCircle className="size-4 text-danger" /> : s.status === "waiting" ? <History className="size-4 text-warning" /> : <CheckCircle2 className="size-4 text-success" />}<span className="font-medium">{s.type.replace(/_/g, " ")}</span><span className="text-fg-muted">— {s.detail}</span></li>)}</ol>{r.error && <p className="mt-2 text-xs text-danger">{r.error}</p>}</Card>))}</div></div>
      ) : (
        <div className="grid min-h-0 flex-1 lg:grid-cols-[1fr_360px]">
          <div className="relative min-h-[420px] bg-bg-subtle/40">
            <ReactFlowProvider>
              <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_, n) => setSel(n.id)} onPaneClick={() => setSel("trigger")} fitView fitViewOptions={{ padding: 0.3, maxZoom: 1 }} minZoom={0.4} nodesConnectable={false} nodesDraggable={false} colorMode={resolved} proOptions={{ hideAttribution: true }}>
                <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} /><Controls showInteractive={false} />
              </ReactFlow>
            </ReactFlowProvider>
            {steps.length === 0 && <div className="pointer-events-none absolute inset-x-0 bottom-8 flex justify-center"><motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-full bg-surface px-4 py-2 text-sm text-fg-muted shadow-md">Add your first step from the panel →</motion.p></div>}
          </div>
          <aside className="min-h-0 overflow-y-auto border-l border-border bg-surface p-5" aria-label="Step settings">
            {sel === "trigger" ? (
              <div className="space-y-5">
                <div><h2 className="text-base font-semibold">Trigger</h2><p className="text-[13px] text-fg-muted">What starts this automation?</p></div>
                <FormField label="When"><NativeSelect value={trigger} onChange={(e) => { setTrigger(e.target.value); setTConfig({}); mark(); setTest(null); }} disabled={!!id}>{meta.triggers.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</NativeSelect></FormField>
                {id && <p className="-mt-3 text-xs text-fg-subtle">The trigger can't be changed after creation — duplicate the automation instead.</p>}
                {trig.config.map((c) => <FormField key={c.key} label={c.label} hint="Leave empty for any stage"><Input value={(tConfig[c.key] as string) ?? ""} onChange={(e) => { setTConfig({ ...tConfig, [c.key]: e.target.value }); mark(); }} placeholder="e.g. Won" /></FormField>)}
                <div className="border-t border-border pt-5"><h3 className="mb-3 text-sm font-semibold">Add a step</h3>
                  <div className="grid grid-cols-2 gap-2">{meta.actions.map((a) => { const I = ACTION_ICONS[a.key]; return <button key={a.key} onClick={() => add(a.key)} disabled={!canEdit || steps.length >= 18} className="flex items-center gap-2.5 rounded-lg border border-border p-2.5 text-left text-[13px] font-medium transition-colors hover:border-primary/40 hover:bg-primary-soft/40 disabled:opacity-50"><span className="flex size-7 shrink-0 items-center justify-center rounded-md" style={{ background: `color-mix(in srgb, ${ACTION_COLORS[a.key]} 15%, transparent)`, color: ACTION_COLORS[a.key] }}><I className="size-4" /></span>{a.label}</button>; })}</div></div>
              </div>
            ) : selStep ? (
              <div className="space-y-5">
                <div className="flex items-start justify-between gap-2"><div><h2 className="text-base font-semibold">{aMeta(selStep.action_type).label}</h2><p className="text-[13px] text-fg-muted">Step {selIdx + 1} of {steps.length}</p></div>
                  <div className="flex gap-1"><Button variant="ghost" size="icon-sm" disabled={selIdx === 0} onClick={() => move(selIdx, -1)} aria-label="Move up"><ArrowUp /></Button><Button variant="ghost" size="icon-sm" disabled={selIdx === steps.length - 1} onClick={() => move(selIdx, 1)} aria-label="Move down"><ArrowDown /></Button><Button variant="ghost" size="icon-sm" onClick={() => remove(selStep.id)} aria-label="Delete step" className="text-danger"><Trash2 /></Button></div></div>
                {aMeta(selStep.action_type).fields.map((f) => <FormField key={f.key} label={f.label} hint={f.key === "body" || f.key === "title" || f.key === "subject" ? "Merge fields: {{first_name}} {{name}} {{stage}}" : undefined}><ConfigField f={f} value={selStep.config[f.key]} onChange={(v) => { setSteps((p) => p.map((s) => (s.id === selStep.id ? { ...s, config: { ...s.config, [f.key]: v } } : s))); mark(); setTest(null); }} /></FormField>)}
                {results.get(selStep.id) && <p className={cn("rounded-lg p-3 text-[13px]", results.get(selStep.id)!.status === "failed" ? "bg-danger-soft text-danger" : "bg-success-soft text-success")}>Test: {results.get(selStep.id)!.detail}</p>}
              </div>
            ) : null}
            {test && <div className="mt-6 border-t border-border pt-4"><p className="mb-2 text-sm font-semibold">Test run (no side effects)</p><ol className="space-y-1.5 text-[13px]">{test.steps.map((s) => <li key={s.node_id} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /><span><span className="font-medium">{s.type.replace(/_/g, " ")}</span> <span className="text-fg-muted">{s.detail}</span></span></li>)}</ol></div>}
          </aside>
        </div>
      )}
    </div>
  );
}

export function AutomationEditor() {
  const { id } = useParams<{ id: string }>(); const isNew = id === "new";
  const meta = useQuery({ queryKey: ["automation-meta"], queryFn: () => api.get<Meta>("/api/v1/automations/meta") });
  const a = useQuery({ queryKey: ["automation", id], enabled: !isNew, queryFn: () => api.get<Auto>(`/api/v1/automations/${id}`) });
  if (meta.isError || a.isError) return <PageContainer><ErrorState kind={(meta.error as { status?: number })?.status === 402 ? "permission" : "unavailable"} title={(meta.error as { status?: number })?.status === 402 ? "Automations aren't in your plan" : undefined} description={(meta.error as { status?: number })?.status === 402 ? "Upgrade to Starter or above to build automations." : undefined} action={<Button asChild variant="secondary"><Link href="/app/automations">Back</Link></Button>} /></PageContainer>;
  if (!meta.data || (!isNew && !a.data)) return <PageContainer><Skeleton className="h-10 w-64" /><Skeleton className="mt-6 h-96" /></PageContainer>;
  return <Builder key={id + (a.data?.id ?? "")} initial={isNew ? null : a.data!} meta={meta.data} isNew={isNew} />;
}
export { Plus, TEMPLATES };
