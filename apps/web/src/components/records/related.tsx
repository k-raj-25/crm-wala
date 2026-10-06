"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Calendar, CheckCircle2, Download, FileText, Mail, Paperclip, Phone, Pin, Plus, Trash2, UploadCloud } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, Button, Card, ColorChip, ConfirmDialog, EmptyState, Input, SkeletonRows, Textarea, cn, formatDate, formatMoney, timeAgo, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { CALL_OUTCOMES, label } from "@/lib/constants";
import { useAccess } from "@/lib/queries";
import type { Call, Contact, Deal, EmailMsg, Meeting, Note, Task } from "@/lib/types";
import { useUI } from "../shell/ui-context";

export type Scope = { entity: "lead" | "contact" | "company" | "deal"; id: string; label?: string };
const fk = (s: Scope) => ({ [`${s.entity}_id`]: s.id });

function useList<T>(key: string, path: string, s: Scope, extra: Record<string, unknown> = {}) {
  return useQuery({ queryKey: [key, s.entity, s.id, extra], queryFn: () => api.page<T>(path, { ...fk(s), per_page: 50, ...extra }) });
}
const Loading = () => <SkeletonRows rows={4} />;

export function NotesTab({ scope }: { scope: Scope }) {
  const q = useList<Note>("notes", "/api/v1/notes", scope, { sort: "-created_at" }); const { can } = useAccess(); const qc = useQueryClient(); const toast = useToast();
  const [body, setBody] = React.useState(""); const [del, setDel] = React.useState<string | null>(null);
  const add = useMutation({ mutationFn: () => api.post("/api/v1/notes", { body, ...fk(scope) }), onSuccess: () => { setBody(""); qc.invalidateQueries({ queryKey: ["notes"] }); qc.invalidateQueries({ queryKey: ["timeline"] }); toast.success("Note added"); }, onError: (e) => toast.error("Couldn't add note", (e as Error).message) });
  const pin = useMutation({ mutationFn: (n: Note) => api.patch(`/api/v1/notes/${n.id}`, { pinned: !n.pinned }), onSuccess: () => qc.invalidateQueries({ queryKey: ["notes"] }) });
  const notes = [...(q.data?.data ?? [])].sort((a, b) => Number(b.pinned) - Number(a.pinned));
  return (
    <div className="space-y-4">
      {can("notes.create") && <Card className="p-3"><Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} placeholder="Write a note… (visible to your team)" className="border-0 shadow-none focus:ring-0" onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && body.trim()) add.mutate(); }} /><div className="flex items-center justify-between px-1 pt-1"><span className="text-xs text-fg-subtle">⌘↵ to save</span><Button size="sm" onClick={() => add.mutate()} disabled={!body.trim()} loading={add.isPending}>Add note</Button></div></Card>}
      {q.isLoading ? <Loading /> : !notes.length ? <EmptyState compact icon={<FileText />} title="No notes yet" description="Capture context, decisions and next steps." /> : (
        <ul className="space-y-3">{notes.map((n) => (
          <li key={n.id} className={cn("group rounded-xl border bg-surface p-4", n.pinned ? "border-warning/40 bg-warning-soft/30" : "border-border")}>
            <div className="mb-2 flex items-center justify-between gap-3"><span className="flex items-center gap-2 text-[13px]"><Avatar name={n.author?.name} size={22} /><span className="font-medium">{n.author?.name ?? "Unknown"}</span><span className="text-fg-subtle">· {timeAgo(n.created_at)}</span>{n.pinned && <Pin className="size-3.5 text-warning" />}</span>
              <span className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">{can("notes.update") && <Button variant="ghost" size="icon-xs" aria-label={n.pinned ? "Unpin" : "Pin"} onClick={() => pin.mutate(n)}><Pin /></Button>}{can("notes.delete") && <Button variant="ghost" size="icon-xs" aria-label="Delete note" onClick={() => setDel(n.id)}><Trash2 /></Button>}</span></div>
            <p className="whitespace-pre-line text-sm leading-relaxed">{n.body}</p>
          </li>))}</ul>)}
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title="Delete this note?" description="This can't be undone." confirmLabel="Delete" onConfirm={async () => { await api.delete(`/api/v1/notes/${del}`); qc.invalidateQueries({ queryKey: ["notes"] }); toast.success("Note deleted"); }} />
    </div>
  );
}

export function TaskRow({ t, onToggle }: { t: Task; onToggle: (t: Task) => void }) {
  const done = t.status === "completed"; const overdue = !done && t.due_at && new Date(t.due_at) < new Date();
  return (
    <li className="group flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-surface-hover">
      <button onClick={() => onToggle(t)} aria-label={done ? "Mark as to do" : "Mark complete"} aria-pressed={done} className={cn("flex size-5 shrink-0 items-center justify-center rounded-full border-2 transition-all", done ? "border-success bg-success text-white" : "border-border-strong hover:border-primary")}>{done && <CheckCircle2 className="size-5 -m-0.5 fill-success text-white" />}</button>
      <div className="min-w-0 flex-1"><p className={cn("truncate text-sm", done && "text-fg-subtle line-through")}>{t.title}</p><p className="flex items-center gap-2 text-xs text-fg-subtle">{t.due_at && <span className={cn(overdue && "font-medium text-danger")}>{formatDate(t.due_at, "datetime")}</span>}{t.kind === "follow_up" && <Badge tone="info">Follow-up</Badge>}</p></div>
      {t.priority !== "medium" && <Badge tone={t.priority === "urgent" ? "danger" : t.priority === "high" ? "warning" : "neutral"}>{label(t.priority)}</Badge>}
      {t.assignee && <Avatar name={t.assignee.name} size={22} />}
    </li>
  );
}

export function useToggleTask() {
  const qc = useQueryClient(); const toast = useToast();
  return useMutation({ mutationFn: (t: Task) => api.patch(`/api/v1/tasks/${t.id}`, { status: t.status === "completed" ? "todo" : "completed" }),
    onSuccess: (_r, t) => { qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["timeline"] }); qc.invalidateQueries({ queryKey: ["tasks-summary-badge"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); if (t.status !== "completed") toast.success("Task completed"); },
    onError: (e) => toast.error("Couldn't update task", (e as Error).message) });
}

export function TasksTab({ scope }: { scope: Scope }) {
  const q = useList<Task>("tasks", "/api/v1/tasks", scope, { sort: "due_at" }); const toggle = useToggleTask(); const ui = useUI(); const { can } = useAccess();
  const tasks = q.data?.data ?? []; const open = tasks.filter((t) => t.status !== "completed"); const done = tasks.filter((t) => t.status === "completed");
  return (
    <div className="space-y-4">
      {can("tasks.create") && <Button variant="secondary" size="sm" onClick={() => ui.openCreate("task", fk(scope))}><Plus /> Add task</Button>}
      {q.isLoading ? <Loading /> : !tasks.length ? <EmptyState compact icon={<CheckCircle2 />} title="No tasks" description="Create a task so the next step never slips." /> : (
        <><ul>{open.map((t) => <TaskRow key={t.id} t={t} onToggle={(x) => toggle.mutate(x)} />)}</ul>{done.length > 0 && <details><summary className="cursor-pointer px-2 text-xs font-medium text-fg-subtle">Completed ({done.length})</summary><ul className="mt-2">{done.map((t) => <TaskRow key={t.id} t={t} onToggle={(x) => toggle.mutate(x)} />)}</ul></details>}</>)}
    </div>
  );
}

export function EmailsTab({ scope, defaults }: { scope: Scope; defaults: Record<string, unknown> }) {
  const q = useList<EmailMsg>("emails", "/api/v1/emails", scope, { sort: "-created_at" }); const ui = useUI(); const { can } = useAccess(); const [open, setOpen] = React.useState<string | null>(null);
  return (
    <div className="space-y-4">
      {can("emails.create") && <Button variant="secondary" size="sm" onClick={() => ui.openCompose({ ...defaults, [`${scope.entity}_id`]: scope.id })}><Mail /> New email</Button>}
      {q.isLoading ? <Loading /> : !q.data?.data.length ? <EmptyState compact icon={<Mail />} title="No emails yet" description="Emails you send from here — or log — appear on this record." /> : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">{q.data.data.map((e) => (
          <li key={e.id}><button className="flex w-full items-start gap-3 px-4 py-3.5 text-left hover:bg-surface-hover" onClick={() => setOpen(open === e.id ? null : e.id)}>
            <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full", e.direction === "inbound" ? "bg-success-soft text-success" : "bg-info-soft text-info")}><Mail className="size-4" /></span>
            <span className="min-w-0 flex-1"><span className="flex items-center justify-between gap-3"><span className="truncate text-sm font-medium">{e.subject}</span><span className="shrink-0 text-xs text-fg-subtle">{timeAgo(e.sent_at ?? e.created_at)}</span></span>
              <span className="mt-0.5 flex items-center gap-2 text-xs text-fg-muted">{e.direction === "inbound" ? `From ${e.from_address}` : `To ${e.to_addresses.join(", ")}`}{e.status === "scheduled" && <Badge tone="warning">Scheduled {formatDate(e.scheduled_at, "datetime")}</Badge>}{e.status === "failed" && <Badge tone="danger">Failed</Badge>}{e.opens > 0 && <Badge tone="success">Opened {e.opens}×</Badge>}</span>
              {open === e.id && <span className="mt-3 block whitespace-pre-line rounded-lg bg-bg-subtle p-3 text-[13px] text-fg-muted">{e.body}</span>}</span></button></li>))}</ul>)}
    </div>
  );
}

export function CallsTab({ scope }: { scope: Scope }) {
  const q = useList<Call>("calls", "/api/v1/calls", scope, { sort: "-created_at" }); const ui = useUI(); const { can } = useAccess();
  const out = (o: string | null) => CALL_OUTCOMES.find(([k]) => k === o)?.[1];
  return (
    <div className="space-y-4">
      {can("meetings.create") && <Button variant="secondary" size="sm" onClick={() => ui.openCreate("call", fk(scope))}><Phone /> Log or schedule a call</Button>}
      {q.isLoading ? <Loading /> : !q.data?.data.length ? <EmptyState compact icon={<Phone />} title="No calls logged" description="Log calls with an outcome so follow-ups are never missed." /> : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">{q.data.data.map((c) => (
          <li key={c.id} className="flex gap-3 px-4 py-3.5"><span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-success-soft text-success"><Phone className="size-4" /></span>
            <div className="min-w-0 flex-1"><p className="flex flex-wrap items-center gap-2 text-sm font-medium">{label(c.direction)} call{c.status === "scheduled" ? <Badge tone="warning">Scheduled {formatDate(c.scheduled_at, "datetime")}</Badge> : c.outcome && <ColorChip color={c.outcome === "not_interested" ? "#ef4444" : c.outcome === "no_answer" ? "#94a3b8" : "#10b981"}>{out(c.outcome)}</ColorChip>}</p>
              {c.notes && <p className="mt-1 text-[13px] text-fg-muted">{c.notes}</p>}<p className="mt-1 text-xs text-fg-subtle">{c.owner?.name} · {formatDate(c.occurred_at ?? c.scheduled_at, "datetime")}{c.duration_seconds ? ` · ${Math.round(c.duration_seconds / 60)} min` : ""}</p></div></li>))}</ul>)}
    </div>
  );
}

export function MeetingsTab({ scope }: { scope: Scope }) {
  const q = useList<Meeting>("meetings", "/api/v1/meetings", scope, { sort: "-starts_at" }); const ui = useUI(); const { can, has } = useAccess(); const qc = useQueryClient(); const toast = useToast();
  const done = useMutation({ mutationFn: (m: Meeting) => api.patch(`/api/v1/meetings/${m.id}`, { status: "completed" }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["meetings"] }); qc.invalidateQueries({ queryKey: ["timeline"] }); } });
  const sum = useMutation({ mutationFn: (m: Meeting) => api.post<{ summary: string }>("/api/v1/ai/meeting-summary", { meeting_id: m.id }), onError: (e) => toast.error("Couldn't summarize", (e as Error).message) });
  const [summaries, setSummaries] = React.useState<Record<string, string>>({});
  return (
    <div className="space-y-4">
      {can("meetings.create") && <Button variant="secondary" size="sm" onClick={() => ui.openCreate("meeting", fk(scope))}><Calendar /> Schedule meeting</Button>}
      {q.isLoading ? <Loading /> : !q.data?.data.length ? <EmptyState compact icon={<Calendar />} title="No meetings" description="Schedule a meeting and it'll appear on your calendar." /> : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">{q.data.data.map((m) => (
          <li key={m.id} className="px-4 py-3.5"><div className="flex items-start gap-3"><span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary"><Calendar className="size-4" /></span>
            <div className="min-w-0 flex-1"><p className="flex flex-wrap items-center gap-2 text-sm font-medium">{m.title}<Badge tone={m.status === "completed" ? "success" : m.status === "canceled" ? "neutral" : "primary"}>{label(m.status)}</Badge></p><p className="mt-0.5 text-xs text-fg-muted">{formatDate(m.starts_at, "datetime")} – {formatDate(m.ends_at, "time")}{m.meeting_url && <> · <a className="text-primary hover:underline" href={m.meeting_url} target="_blank" rel="noreferrer">Join link</a></>}</p>
              {(summaries[m.id] ?? m.summary) && <p className="mt-2 whitespace-pre-line rounded-lg bg-bg-subtle p-3 text-[13px] text-fg-muted">{summaries[m.id] ?? m.summary}</p>}</div>
            <div className="flex shrink-0 gap-1">{m.status === "scheduled" && can("meetings.update") && <Button variant="ghost" size="xs" onClick={() => done.mutate(m)}>Mark done</Button>}{has("ai_assistant") && m.summary && <Button variant="ghost" size="xs" loading={sum.isPending} onClick={async () => { const r = await sum.mutateAsync(m); setSummaries((s) => ({ ...s, [m.id]: r.summary })); }}>AI summary</Button>}</div></div></li>))}</ul>)}
    </div>
  );
}

export function DealsTab({ scope }: { scope: Scope }) {
  const q = useList<Deal>("deals", "/api/v1/deals", scope, { sort: "-created_at" }); const ui = useUI(); const { can } = useAccess();
  const defaults = { ...fk(scope), ...(scope.entity === "contact" ? { _contact_label: scope.label } : { _company_label: scope.label }) };
  return (
    <div className="space-y-4">
      {can("deals.create") && <Button variant="secondary" size="sm" onClick={() => ui.openCreate("deal", defaults)}><Plus /> New deal</Button>}
      {q.isLoading ? <Loading /> : !q.data?.data.length ? <EmptyState compact title="No deals" description="Deals linked to this record show up here." /> : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">{q.data.data.map((d) => <li key={d.id}><Link href={`/app/deals/${d.id}`} className="flex items-center justify-between gap-3 px-4 py-3.5 hover:bg-surface-hover"><span className="min-w-0"><span className="block truncate text-sm font-medium">{d.name}</span><span className="text-xs text-fg-muted">{d.expected_close_date ? `Close ${formatDate(d.expected_close_date + "T00:00:00")}` : "No close date"}</span></span><span className="flex items-center gap-3"><ColorChip color={d.stage.color}>{d.stage.name}</ColorChip><span className="tabular text-sm font-semibold">{formatMoney(d.value, d.currency)}</span></span></Link></li>)}</ul>)}
    </div>
  );
}

export function ContactsTab({ companyId, companyName }: { companyId: string; companyName: string }) {
  const q = useQuery({ queryKey: ["contacts", "company", companyId], queryFn: () => api.page<Contact>("/api/v1/contacts", { company_id: companyId, per_page: 50 }) }); const ui = useUI(); const { can } = useAccess();
  return (
    <div className="space-y-4">
      {can("contacts.create") && <Button variant="secondary" size="sm" onClick={() => ui.openCreate("contact", { company_id: companyId, _company_label: companyName })}><Plus /> Add contact</Button>}
      {q.isLoading ? <Loading /> : !q.data?.data.length ? <EmptyState compact title="No contacts" description="Add the people you work with at this company." /> : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">{q.data.data.map((c) => <li key={c.id}><Link href={`/app/contacts/${c.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-hover"><Avatar name={c.name} size={34} /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{c.name}</span><span className="block truncate text-xs text-fg-muted">{c.job_title ?? c.email}</span></span><span className="text-xs text-fg-subtle">{c.last_activity_at ? timeAgo(c.last_activity_at) : ""}</span></Link></li>)}</ul>)}
    </div>
  );
}

type FileRow = { id: string; filename: string; size_bytes: number; mime_type: string; created_at: string; uploader: { name: string } | null };
export function FilesTab({ scope }: { scope: Scope }) {
  const q = useQuery({ queryKey: ["files", scope.entity, scope.id], queryFn: () => api.get<FileRow[]>("/api/v1/files", fk(scope)) }); const qc = useQueryClient(); const toast = useToast(); const { can } = useAccess();
  const [drag, setDrag] = React.useState(false); const [busy, setBusy] = React.useState(false); const input = React.useRef<HTMLInputElement>(null); const [del, setDel] = React.useState<FileRow | null>(null);
  const upload = async (files: FileList | File[]) => {
    setBusy(true);
    for (const f of Array.from(files)) { const fd = new FormData(); fd.append("file", f); for (const [k, v] of Object.entries(fk(scope))) fd.append(k, v as string); try { await api.upload("/api/v1/files", fd); } catch (e) { toast.error(`Couldn't upload ${f.name}`, (e as Error).message); } }
    setBusy(false); qc.invalidateQueries({ queryKey: ["files"] }); qc.invalidateQueries({ queryKey: ["timeline"] });
  };
  const open = async (f: FileRow) => { const r = await api.get<{ url: string }>(`/api/v1/files/${f.id}/url`); window.open(r.url, "_blank"); };
  const size = (b: number) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);
  return (
    <div className="space-y-4">
      {can("files.create") && <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files); }} className={cn("flex flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-colors", drag ? "border-primary bg-primary-soft/40" : "border-border")}>
        <UploadCloud className="size-6 text-fg-subtle" /><p className="text-sm text-fg-muted">Drag files here or <button className="font-medium text-primary hover:underline" onClick={() => input.current?.click()}>browse</button></p><p className="text-xs text-fg-subtle">PDF, images, Office docs, CSV — up to 25 MB</p>
        <input ref={input} type="file" multiple hidden onChange={(e) => e.target.files && upload(e.target.files)} />{busy && <p className="text-xs text-primary">Uploading…</p>}</div>}
      {q.isLoading ? <Loading /> : !q.data?.length ? <EmptyState compact icon={<Paperclip />} title="No files" description="Attach contracts, proposals and more." /> : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">{q.data.map((f) => <li key={f.id} className="flex items-center gap-3 px-4 py-3"><FileText className="size-5 shrink-0 text-fg-subtle" /><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{f.filename}</p><p className="text-xs text-fg-subtle">{size(f.size_bytes)} · {f.uploader?.name} · {timeAgo(f.created_at)}</p></div><Button variant="ghost" size="icon-sm" aria-label={`Download ${f.filename}`} onClick={() => open(f)}><Download /></Button>{can("files.delete") && <Button variant="ghost" size="icon-sm" aria-label="Delete file" onClick={() => setDel(f)}><Trash2 /></Button>}</li>)}</ul>)}
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete ${del?.filename}?`} description="The file will no longer be accessible." confirmLabel="Delete" onConfirm={async () => { await api.delete(`/api/v1/files/${del!.id}`); qc.invalidateQueries({ queryKey: ["files"] }); toast.success("File deleted"); }} />
    </div>
  );
}
export { Input };
