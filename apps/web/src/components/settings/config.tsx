"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Badge, Button, ColorChip, ConfirmDialog, Dialog, DialogContent, DialogFooter, EmptyState, Field, Input, NativeSelect, Select, Skeleton, Switch, Tabs, TabsList, TabsTrigger, Textarea, cn, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess, useCustomFields, useMe, usePipelines, keys } from "@/lib/queries";
import type { CustomFieldDef, Me, Pipeline, Stage, Tag } from "@/lib/types";
import { Divided, SettingsSection } from "./ui";

const PALETTE = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#f97316", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#94a3b8"];
function ColorDot({ value, onChange, disabled }: { value: string; onChange: (c: string) => void; disabled?: boolean }) {
  return <label className="relative inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-border" title="Pick color"><span className="size-4 rounded-full" style={{ background: value }} /><input type="color" disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" aria-label="Color" /></label>;
}

export function PipelineSettings() {
  const { can } = useAccess(); const qc = useQueryClient(); const toast = useToast(); const { data, isLoading } = usePipelines(); const manage = can("pipelines.update");
  const [newName, setNewName] = React.useState(""); const [delStage, setDelStage] = React.useState<{ p: Pipeline; s: Stage } | null>(null); const [moveTo, setMoveTo] = React.useState(""); const [delPipe, setDelPipe] = React.useState<Pipeline | null>(null); const [err, setErr] = React.useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: keys.pipelines });
  const run = async (fn: () => Promise<unknown>, ok?: string) => { try { await fn(); refresh(); qc.invalidateQueries({ queryKey: ["board"] }); if (ok) toast.success(ok); } catch (e) { toast.error("Couldn't save", (e as Error).message); } };
  if (isLoading) return <Skeleton className="h-96" />;
  return (
    <div className="space-y-6">
      {data!.map((p) => (
        <SettingsSection key={p.id} title={<span className="flex items-center gap-2">{p.name}{p.is_default && <Badge tone="primary">Default</Badge>}</span> as unknown as string} description={`${p.stages.length} stages — customise names, win probability and order.`}
          actions={manage && <div className="flex gap-2">{!p.is_default && <Button size="sm" variant="secondary" onClick={() => run(() => api.patch(`/api/v1/pipelines/${p.id}`, { is_default: true }), "Default pipeline updated")}><Star /> Make default</Button>}{!p.is_default && <Button size="sm" variant="ghost" className="text-danger" onClick={() => setDelPipe(p)}>Delete</Button>}</div>}>
          <ul className="space-y-2">
            {p.stages.map((s, i) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface p-2.5 sm:flex-nowrap">
                <div className="flex flex-col"><button disabled={!manage || i === 0} aria-label="Move up" onClick={() => run(() => api.put(`/api/v1/pipelines/${p.id}/stages/order`, { ids: p.stages.map((x) => x.id).map((id, k, a) => (k === i - 1 ? a[i] : k === i ? a[i - 1] : id)) }))} className="rounded p-0.5 text-fg-subtle hover:text-fg disabled:opacity-30"><ArrowUp className="size-3.5" /></button><button disabled={!manage || i === p.stages.length - 1} aria-label="Move down" onClick={() => run(() => api.put(`/api/v1/pipelines/${p.id}/stages/order`, { ids: p.stages.map((x) => x.id).map((id, k, a) => (k === i + 1 ? a[i] : k === i ? a[i + 1] : id)) }))} className="rounded p-0.5 text-fg-subtle hover:text-fg disabled:opacity-30"><ArrowDown className="size-3.5" /></button></div>
                <ColorDot value={s.color ?? "#94a3b8"} disabled={!manage} onChange={(c) => run(() => api.patch(`/api/v1/pipelines/${p.id}/stages/${s.id}`, { color: c }))} />
                <Input defaultValue={s.name} disabled={!manage} className="h-8 min-w-[140px] flex-1" aria-label="Stage name" onBlur={(e) => e.target.value.trim() && e.target.value !== s.name && run(() => api.patch(`/api/v1/pipelines/${p.id}/stages/${s.id}`, { name: e.target.value.trim() }), "Stage renamed")} />
                <div className="flex items-center gap-1.5"><Input type="number" min={0} max={100} defaultValue={s.probability} disabled={!manage || s.kind !== "open"} className="h-8 w-16" aria-label="Probability" onBlur={(e) => Number(e.target.value) !== s.probability && run(() => api.patch(`/api/v1/pipelines/${p.id}/stages/${s.id}`, { probability: Math.max(0, Math.min(100, Number(e.target.value))) }))} /><span className="text-xs text-fg-subtle">%</span></div>
                <div className="w-28"><Select size="sm" value={s.kind} disabled={!manage} onValueChange={(v) => run(() => api.patch(`/api/v1/pipelines/${p.id}/stages/${s.id}`, { kind: v }))} options={[{ value: "open", label: "Open" }, { value: "won", label: "Won" }, { value: "lost", label: "Lost" }]} /></div>
                {manage && <Button variant="ghost" size="icon-sm" aria-label={`Delete ${s.name}`} onClick={() => { setDelStage({ p, s }); setMoveTo(""); setErr(null); }}><Trash2 /></Button>}
              </li>))}
          </ul>
          {manage && <Button className="mt-3" variant="secondary" size="sm" onClick={() => run(() => api.post(`/api/v1/pipelines/${p.id}/stages`, { name: "New stage", probability: 50, kind: "open", color: "#6366f1" }), "Stage added")}><Plus /> Add stage</Button>}
        </SettingsSection>))}
      {can("pipelines.create") && <SettingsSection title="Create another pipeline" description="Separate processes (e.g. Partnerships vs Sales) each get their own board."><form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); if (!newName.trim()) return; try { await api.post("/api/v1/pipelines", { name: newName.trim() }); setNewName(""); refresh(); toast.success("Pipeline created"); } catch (er) { toast.error("Couldn't create pipeline", (er as Error).message); } }}><Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Pipeline name" aria-label="Pipeline name" className="max-w-xs" /><Button type="submit" disabled={!newName.trim()}>Create pipeline</Button></form></SettingsSection>}
      <Dialog open={!!delStage} onOpenChange={(o) => !o && setDelStage(null)}><DialogContent size="sm" title={`Delete “${delStage?.s.name}”?`} description="If deals are in this stage, choose where they should go.">
        {delStage && <Field label="Move deals to" error={err ?? undefined}><NativeSelect value={moveTo} onChange={(e) => setMoveTo(e.target.value)}><option value="">No deals (or choose a stage)…</option>{delStage.p.stages.filter((x) => x.id !== delStage.s.id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</NativeSelect></Field>}
        <DialogFooter><Button variant="secondary" onClick={() => setDelStage(null)}>Cancel</Button><Button variant="danger" onClick={async () => { try { await api.delete(`/api/v1/pipelines/${delStage!.p.id}/stages/${delStage!.s.id}${moveTo ? `?move_to=${moveTo}` : ""}`); refresh(); setDelStage(null); toast.success("Stage deleted"); } catch (e) { setErr((e as Error).message); } }}>Delete stage</Button></DialogFooter></DialogContent></Dialog>
      <ConfirmDialog open={!!delPipe} onOpenChange={(o) => !o && setDelPipe(null)} title={`Delete “${delPipe?.name}”?`} description="Only pipelines without open deals can be deleted." confirmLabel="Delete pipeline" onConfirm={async () => { await api.delete(`/api/v1/pipelines/${delPipe!.id}`); refresh(); toast.success("Pipeline deleted"); }} />
    </div>
  );
}

export function LeadStatusSettings() {
  const { data: me } = useMe(); const { can } = useAccess(); const qc = useQueryClient(); const toast = useToast(); const manage = can("settings.manage");
  const [rows, setRows] = React.useState<{ key: string; label: string; color: string }[]>([]); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  React.useEffect(() => { if (me?.workspace) setRows(me.workspace.lead_statuses); }, [me?.workspace?.id, me?.workspace?.lead_statuses]);
  const fixed = new Set(["new", "converted", "lost"]);
  const save = async () => { setBusy(true); setErr(null); try { await api.put("/api/v1/settings/lead-statuses", { statuses: rows }); qc.invalidateQueries({ queryKey: keys.me }); toast.success("Lead statuses saved"); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const move = (i: number, d: number) => setRows((r) => { const n = [...r]; [n[i], n[i + d]] = [n[i + d], n[i]]; return n; });
  return (
    <SettingsSection title="Lead statuses" description="The stages a lead moves through before it becomes a customer. “New”, “Converted” and “Lost” are required." actions={<Button onClick={save} loading={busy} disabled={!manage}>Save</Button>}>
      <ul className="space-y-2">{rows.map((r, i) => <li key={r.key} className="flex items-center gap-2 rounded-lg border border-border p-2.5"><div className="flex flex-col"><button aria-label="Up" disabled={i === 0 || !manage} onClick={() => move(i, -1)} className="text-fg-subtle hover:text-fg disabled:opacity-30"><ArrowUp className="size-3.5" /></button><button aria-label="Down" disabled={i === rows.length - 1 || !manage} onClick={() => move(i, 1)} className="text-fg-subtle hover:text-fg disabled:opacity-30"><ArrowDown className="size-3.5" /></button></div>
        <ColorDot value={r.color} disabled={!manage} onChange={(c) => setRows(rows.map((x, k) => (k === i ? { ...x, color: c } : x)))} /><Input value={r.label} disabled={!manage} className="h-8 flex-1" aria-label="Status label" onChange={(e) => setRows(rows.map((x, k) => (k === i ? { ...x, label: e.target.value } : x)))} /><code className="hidden text-xs text-fg-subtle sm:block">{r.key}</code><ColorChip color={r.color}>{r.label || "…"}</ColorChip>
        <Button variant="ghost" size="icon-sm" disabled={fixed.has(r.key) || !manage} aria-label="Remove status" onClick={() => setRows(rows.filter((_, k) => k !== i))}><Trash2 /></Button></li>)}</ul>
      {manage && <Button className="mt-3" variant="secondary" size="sm" onClick={() => { const n = rows.length + 1; setRows([...rows.slice(0, -2), { key: `status_${n}`, label: `Status ${n}`, color: PALETTE[n % PALETTE.length] }, ...rows.slice(-2)]); }}><Plus /> Add status</Button>}
      {err && <p role="alert" className="mt-3 text-sm text-danger">{err}</p>}
    </SettingsSection>
  );
}

const FT = [["text", "Text"], ["number", "Number"], ["currency", "Currency"], ["date", "Date"], ["dropdown", "Dropdown"], ["multi_select", "Multi-select"], ["checkbox", "Checkbox"], ["url", "URL"], ["email", "Email"], ["phone", "Phone"]];
export function CustomFieldSettings() {
  const { can, has } = useAccess(); const qc = useQueryClient(); const toast = useToast(); const { data, isLoading } = useCustomFields(); const manage = can("settings.manage") && has("custom_fields");
  const [ent, setEnt] = React.useState<"lead" | "contact" | "company" | "deal">("lead"); const [open, setOpen] = React.useState(false); const [f, setF] = React.useState({ label: "", field_type: "text", options: "", required: false }); const [err, setErr] = React.useState<string | null>(null); const [del, setDel] = React.useState<CustomFieldDef | null>(null);
  const list = (data ?? []).filter((d) => d.entity_type === ent);
  const add = async () => { setErr(null); try { await api.post("/api/v1/custom-fields", { entity_type: ent, label: f.label, field_type: f.field_type, options: f.options.split(",").map((s) => s.trim()).filter(Boolean), required: f.required }); qc.invalidateQueries({ queryKey: keys.customFields }); setOpen(false); setF({ label: "", field_type: "text", options: "", required: false }); toast.success("Custom field added"); } catch (e) { setErr((e as Error).message); } };
  return (
    <SettingsSection title="Custom fields" description="Capture the details unique to your business. Fields appear in forms and on record pages." actions={<Button onClick={() => { setOpen(true); setErr(null); }} disabled={!manage}><Plus /> Add field</Button>}>
      {!has("custom_fields") && <p className="mb-4 rounded-lg bg-warning-soft p-3 text-sm text-warning">Custom fields aren't in your plan. <Link href="/app/billing" className="font-medium underline">Upgrade</Link></p>}
      <Tabs value={ent} onValueChange={(v) => setEnt(v as typeof ent)}><TabsList>{(["lead", "contact", "company", "deal"] as const).map((e) => <TabsTrigger key={e} value={e} count={(data ?? []).filter((d) => d.entity_type === e).length}>{e[0].toUpperCase() + e.slice(1)}s</TabsTrigger>)}</TabsList></Tabs>
      <div className="mt-4">{isLoading ? <Skeleton className="h-32" /> : !list.length ? <EmptyState compact title={`No custom ${ent} fields`} description="Add a field like “Preferred language” or “Contract length”." /> : <ul className="divide-y divide-border">{list.map((d) => <li key={d.id} className="flex items-center justify-between gap-3 py-3"><div><p className="text-sm font-medium">{d.label} {d.required && <Badge tone="warning">Required</Badge>}</p><p className="text-xs text-fg-muted">{FT.find(([k]) => k === d.field_type)?.[1]}{d.options.length ? ` · ${d.options.join(", ")}` : ""}</p></div>{manage && <Button size="icon-sm" variant="ghost" aria-label={`Delete ${d.label}`} onClick={() => setDel(d)}><Trash2 /></Button>}</li>)}</ul>}</div>
      <Dialog open={open} onOpenChange={setOpen}><DialogContent size="sm" title={`New ${ent} field`}>
        <div className="space-y-4"><Field label="Label" error={err ?? undefined}><Input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} autoFocus /></Field><Field label="Type"><NativeSelect value={f.field_type} onChange={(e) => setF({ ...f, field_type: e.target.value })}>{FT.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect></Field>
          {["dropdown", "multi_select"].includes(f.field_type) && <Field label="Options" hint="Comma separated"><Input value={f.options} onChange={(e) => setF({ ...f, options: e.target.value })} placeholder="English, Hindi, Tamil" /></Field>}
          <label className="flex items-center gap-3 text-sm"><Switch checked={f.required} onCheckedChange={(c) => setF({ ...f, required: c })} aria-label="Required" />Required when creating records</label></div>
        <DialogFooter><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button onClick={add} disabled={!f.label.trim()}>Add field</Button></DialogFooter></DialogContent></Dialog>
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete “${del?.label}”?`} description="Values already saved on records stay in the database but are hidden." confirmLabel="Delete field" onConfirm={async () => { await api.delete(`/api/v1/custom-fields/${del!.id}`); qc.invalidateQueries({ queryKey: keys.customFields }); }} />
    </SettingsSection>
  );
}

export function TagSettings() {
  const { can } = useAccess(); const qc = useQueryClient(); const toast = useToast(); const manage = can("settings.manage");
  const q = useQuery({ queryKey: keys.tags, queryFn: () => api.get<Tag[]>("/api/v1/tags") }); const [name, setName] = React.useState(""); const [del, setDel] = React.useState<Tag | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: keys.tags });
  return (
    <SettingsSection title="Tags" description="Labels you can attach to leads, contacts, companies and deals. Renaming updates every record.">
      {q.isLoading ? <Skeleton className="h-24" /> : <ul className="flex flex-wrap gap-2">{q.data!.map((t) => <li key={t.id} className="group flex items-center gap-1 rounded-full border border-border bg-surface py-1 pl-1.5 pr-2"><ColorDot value={t.color ?? "#6366f1"} disabled={!manage} onChange={async (c) => { await api.patch(`/api/v1/tags/${t.id}`, { color: c }); refresh(); }} /><input defaultValue={t.name} disabled={!manage} aria-label="Tag name" className="w-24 bg-transparent text-sm outline-none" onBlur={async (e) => { const v = e.target.value.trim(); if (v && v !== t.name) { try { await api.patch(`/api/v1/tags/${t.id}`, { name: v }); refresh(); } catch (er) { toast.error("Couldn't rename", (er as Error).message); e.target.value = t.name; } } }} />{manage && <button aria-label={`Delete ${t.name}`} onClick={() => setDel(t)} className="rounded-full p-1 text-fg-subtle hover:bg-danger-soft hover:text-danger"><Trash2 className="size-3.5" /></button>}</li>)}{!q.data!.length && <li className="text-sm text-fg-muted">No tags yet — they're created as you use them.</li>}</ul>}
      {manage && <form className="mt-4 flex max-w-sm gap-2" onSubmit={async (e) => { e.preventDefault(); if (!name.trim()) return; try { await api.post("/api/v1/tags", { name: name.trim() }); setName(""); refresh(); } catch (er) { toast.error("Couldn't add tag", (er as Error).message); } }}><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="New tag" aria-label="New tag" /><Button type="submit" variant="secondary" disabled={!name.trim()}><Plus /> Add</Button></form>}
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete tag “${del?.name}”?`} description="It's removed from every record that uses it." confirmLabel="Delete tag" onConfirm={async () => { await api.delete(`/api/v1/tags/${del!.id}`); refresh(); }} />
    </SettingsSection>
  );
}

type Tpl = { id: string; name: string; subject: string; body: string };
export function EmailSettings() {
  const { can } = useAccess(); const qc = useQueryClient(); const toast = useToast();
  const q = useQuery({ queryKey: ["email-templates"], queryFn: () => api.get<Tpl[]>("/api/v1/emails/templates") }); const integ = useQuery({ queryKey: ["integrations"], queryFn: () => api.get<{ integrations: { provider: string; status: string; mode: string | null; account_label: string | null }[] }>("/api/v1/integrations") });
  const [edit, setEdit] = React.useState<Partial<Tpl> | null>(null); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  const mail = integ.data?.integrations.filter((i) => ["gmail", "outlook"].includes(i.provider) && i.status === "connected");
  const save = async () => { setBusy(true); setErr(null); try { const b = { name: edit!.name, subject: edit!.subject, body: edit!.body }; edit!.id ? await api.patch(`/api/v1/emails/templates/${edit!.id}`, b) : await api.post("/api/v1/emails/templates", b); qc.invalidateQueries({ queryKey: ["email-templates"] }); setEdit(null); toast.success("Template saved"); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  return (
    <div className="space-y-6">
      <SettingsSection title="Mailbox" description="Send and receive email from your own account so conversations land on the right records."><div className="flex flex-wrap items-center justify-between gap-3"><div className="text-sm">{mail?.length ? mail.map((m) => <p key={m.provider}><Badge tone="success" dot>Connected</Badge> <span className="ml-2 font-medium capitalize">{m.provider}</span> <span className="text-fg-muted">· {m.account_label}{m.mode === "sandbox" ? " (sandbox)" : ""}</span></p>) : <p className="text-fg-muted">No mailbox connected — emails send from CRM Wala with your address as reply-to.</p>}</div><Button variant="secondary" asChild><Link href="/app/integrations">Manage integrations</Link></Button></div></SettingsSection>
      <SettingsSection title="Email templates" description="Reusable emails with merge fields like {{first_name}}." actions={can("emails.create") && <Button onClick={() => { setEdit({ name: "", subject: "", body: "Hi {{first_name}},\n\n" }); setErr(null); }}><Plus /> New template</Button>}>
        {q.isLoading ? <Skeleton className="h-24" /> : !q.data?.length ? <EmptyState compact title="No templates yet" description="Save time with templates for intros, follow-ups and proposals." /> : <ul className="divide-y divide-border">{q.data.map((t) => <li key={t.id} className="flex items-center justify-between gap-3 py-3.5"><div className="min-w-0"><p className="text-sm font-medium">{t.name}</p><p className="truncate text-xs text-fg-muted">{t.subject}</p></div><div className="flex gap-1"><Button size="xs" variant="ghost" onClick={() => { setEdit(t); setErr(null); }}>Edit</Button><Button size="xs" variant="ghost" className="text-danger" onClick={async () => { await api.delete(`/api/v1/emails/templates/${t.id}`); qc.invalidateQueries({ queryKey: ["email-templates"] }); }}>Delete</Button></div></li>)}</ul>}
      </SettingsSection>
      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}><DialogContent size="lg" title={edit?.id ? "Edit template" : "New template"}>
        {edit && <div className="space-y-4"><Field label="Name"><Input value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field><Field label="Subject"><Input value={edit.subject ?? ""} onChange={(e) => setEdit({ ...edit, subject: e.target.value })} /></Field><Field label="Body" hint="Merge fields: {{first_name}} {{last_name}} {{company}} {{sender_name}}" error={err ?? undefined}><Textarea rows={10} value={edit.body ?? ""} onChange={(e) => setEdit({ ...edit, body: e.target.value })} /></Field></div>}
        <DialogFooter><Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button><Button onClick={save} loading={busy} disabled={!edit?.name?.trim() || !edit?.subject?.trim() || !edit?.body?.trim()}>Save template</Button></DialogFooter></DialogContent></Dialog>
    </div>
  );
}
export { Divided, cn };
