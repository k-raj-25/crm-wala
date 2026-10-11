"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCheck, Download, FileText, MessageCircle, Send, Trash2, UploadCloud, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { ApiError, Badge, Button, ConfirmDialog, EmptyState, ErrorState, Field, Input, NativeSelect, Skeleton, Textarea, cn, formatDate, timeAgo, useToast } from "@crm/ui";
import { AsyncSelect } from "@/components/forms/fields";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";

export type WaTemplate = { name: string; language: string; category: string | null; body: string; body_params: number; header: string | null };
export type WaMessage = { id: string; direction: "inbound" | "outbound"; status: "sent" | "delivered" | "read" | "failed" | "received"; kind: string; body: string | null; template_name: string | null; error: string | null; created_at: string; data: { filename?: string; sandbox?: boolean } };
type Conversation = { phone: string | null; connected: boolean; mode: "live" | "sandbox" | null; window_open: boolean; messages: WaMessage[] };
export type UnitDoc = { id: string; filename: string; mime_type: string; size_bytes: number; doc_kind: string | null; scope: "unit" | "project"; created_at: string };

export const DOC_KINDS: [string, string][] = [["brochure", "Brochure"], ["floor_plan", "Floor plan"], ["price_list", "Price list"], ["other", "Other"]];
export const WA_GREEN = "#25d366";
const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
const templateKey = (t: WaTemplate) => `${t.name}|${t.language}`;
const fill = (body: string, params: string[]) => body.replace(/\{\{\s*(\d+)\s*\}\}/g, (m, n) => params[Number(n) - 1] || m);

export function useWaTemplates(enabled = true) {
  return useQuery({ queryKey: ["wa-templates"], enabled, staleTime: 5 * 60_000, retry: false, queryFn: () => api.get<WaTemplate[]>("/api/v1/whatsapp/templates") });
}

function Ticks({ m }: { m: WaMessage }) {
  if (m.direction === "inbound") return null;
  if (m.status === "failed") return <XCircle className="size-3.5 text-danger" aria-label="Failed" />;
  if (m.status === "sent") return <Check className="size-3.5" aria-label="Sent" />;
  return <CheckCheck className={cn("size-3.5", m.status === "read" && "text-info")} aria-label={m.status === "read" ? "Read" : "Delivered"} />;
}

/** Template picker with one input per {{n}} placeholder and a live preview. */
function TemplateComposer({ templates, defaults, onSend, busy }: { templates: WaTemplate[]; defaults: string[]; onSend: (t: WaTemplate, params: string[]) => void; busy: boolean }) {
  const usable = templates.filter((t) => !t.header || t.header === "TEXT");
  const [key, setKey] = React.useState("");
  const t = usable.find((x) => templateKey(x) === key);
  const [params, setParams] = React.useState<string[]>([]);
  React.useEffect(() => { if (t) setParams(Array.from({ length: t.body_params }, (_, i) => defaults[i] ?? "")); }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!usable.length) return <p className="text-sm text-fg-muted">No approved text templates yet. Create one in WhatsApp Manager and it shows up here once Meta approves it.</p>;
  return (
    <div className="space-y-3">
      <Field label="Template"><NativeSelect value={key} onChange={(e) => setKey(e.target.value)}><option value="">Choose an approved template…</option>{usable.map((x) => <option key={templateKey(x)} value={templateKey(x)}>{x.name.replace(/_/g, " ")} ({x.language})</option>)}</NativeSelect></Field>
      {t && <>
        {params.map((p, i) => <Field key={i} label={`Placeholder {{${i + 1}}}`}><Input value={p} onChange={(e) => setParams(params.map((x, j) => (j === i ? e.target.value : x)))} maxLength={200} /></Field>)}
        <p className="whitespace-pre-line rounded-lg bg-bg-subtle px-3 py-2 text-[13px] text-fg-muted">{fill(t.body, params)}</p>
        <div className="flex justify-end"><Button size="sm" loading={busy} disabled={params.some((p) => !p.trim())} onClick={() => onSend(t, params)}><Send /> Send template</Button></div>
      </>}
    </div>
  );
}

/** WhatsApp conversation with a lead or contact: history, 24-hour window state, templates and free text. */
export function WhatsAppTab({ entity, id, firstName }: { entity: "lead" | "contact"; id: string; firstName: string }) {
  const qc = useQueryClient(); const toast = useToast(); const { can } = useAccess();
  const conv = useQuery({ queryKey: ["wa-conversation", entity, id], refetchInterval: (q) => (q.state.status === "error" ? false : 20_000), retry: 1, queryFn: () => api.get<Conversation>("/api/v1/whatsapp/conversation", { [`${entity}_id`]: id }) });
  const c = conv.data;
  const templates = useWaTemplates(!!c?.connected);
  const [text, setText] = React.useState(""); const [busy, setBusy] = React.useState(false); const [mode, setMode] = React.useState<"text" | "template">("text");
  const end = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [c?.messages.length]);
  const send = async (body: Record<string, unknown>) => {
    setBusy(true);
    try { await api.post("/api/v1/whatsapp/send", { [`${entity}_id`]: id, ...body }); setText(""); qc.invalidateQueries({ queryKey: ["wa-conversation", entity, id] }); qc.invalidateQueries({ queryKey: ["timeline"] }); toast.success("Sent on WhatsApp"); }
    catch (e) { toast.error("Couldn't send", errText(e)); } finally { setBusy(false); }
  };
  if (conv.isLoading) return <Skeleton className="h-60 w-full" />;
  // A failed request is not the same as "not connected": say what went wrong (a 404 here means the API is older than this screen).
  if (conv.isError) return <ErrorState compact title="Couldn't load WhatsApp" description={(conv.error as ApiError)?.status === 404 ? "The server doesn't have WhatsApp messaging yet. Restart the API and run database migrations, then try again." : errText(conv.error)} onRetry={() => conv.refetch()} />;
  if (!c?.connected) return <EmptyState compact icon={<MessageCircle />} title="WhatsApp isn't connected" description="Connect your WhatsApp Business number to message clients from here." action={can("integrations.manage") ? <Button variant="secondary" size="sm" asChild><Link href="/app/integrations?connect=whatsapp">Connect WhatsApp</Link></Button> : undefined} />;
  if (!c.phone) return <EmptyState compact icon={<MessageCircle />} title="No mobile number" description="Add a mobile number to this record to message them on WhatsApp." />;
  const windowOpen = c.window_open; const tab = windowOpen ? mode : "template";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted"><span className="font-medium text-fg">+{c.phone}</span>{c.mode === "sandbox" && <Badge tone="warning">Sandbox</Badge>}<span className="ml-auto">{windowOpen ? "Replied in the last 24 hours: free messages allowed" : "Outside the 24-hour window: templates only"}</span></div>
      <div className="max-h-[420px] space-y-2 overflow-y-auto rounded-xl border border-border bg-bg-subtle p-3">
        {!c.messages.length ? <p className="py-6 text-center text-sm text-fg-muted">No WhatsApp messages yet.</p> : c.messages.map((m) => (
          <div key={m.id} className={cn("flex", m.direction === "outbound" ? "justify-end" : "justify-start")}>
            <div className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-xs", m.direction === "outbound" ? "rounded-br-sm bg-[#dcf8c6] text-[#111b21] dark:bg-[#005c4b] dark:text-[#e9edef]" : "rounded-bl-sm bg-surface")}>
              {m.data?.filename && <p className="mb-1 flex items-center gap-1.5 font-medium"><FileText className="size-4 shrink-0" />{m.data.filename}</p>}
              {m.template_name && <p className="mb-0.5 text-[11px] uppercase tracking-wide opacity-60">Template · {m.template_name.replace(/_/g, " ")}</p>}
              {m.body && <p className="whitespace-pre-line">{m.body}</p>}
              {m.error && <p className="mt-1 text-xs text-danger">{m.error}</p>}
              <p className="mt-1 flex items-center justify-end gap-1 text-[11px] opacity-60" title={formatDate(m.created_at, "datetime")}>{timeAgo(m.created_at)}<Ticks m={m} /></p>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
      {can("emails.create") && (
        <div className="space-y-3 rounded-xl border border-border p-4">
          {windowOpen && <div className="flex gap-1">{(["text", "template"] as const).map((k) => <button key={k} type="button" onClick={() => setMode(k)} aria-pressed={tab === k} className={cn("h-8 rounded-full border px-3 text-[13px] font-medium", tab === k ? "border-primary bg-primary-soft text-primary" : "border-border text-fg-muted hover:bg-surface-hover")}>{k === "text" ? "Message" : "Template"}</button>)}</div>}
          {tab === "text" ? (
            <div className="flex items-end gap-2"><Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder={`Message ${firstName}…`} maxLength={4096} className="flex-1" /><Button loading={busy} disabled={!text.trim()} onClick={() => send({ text })} aria-label="Send"><Send /></Button></div>
          ) : templates.isLoading ? <Skeleton className="h-10 w-full" /> : templates.isError ? <p className="text-sm text-danger">{errText(templates.error)}</p> : (
            <TemplateComposer templates={templates.data ?? []} defaults={[firstName]} busy={busy} onSend={(t, params) => send({ template: { name: t.name, language: t.language, params } })} />
          )}
        </div>
      )}
    </div>
  );
}

/** Brochures, floor plans and price lists for a unit (its own plus its project's), each sendable on WhatsApp. */
export function UnitDocuments({ unit, canEdit, defaultLead }: { unit: { id: string; project_id: string }; canEdit: boolean; defaultLead?: { id: string; name: string | null } | null }) {
  const qc = useQueryClient(); const toast = useToast(); const { can, has } = useAccess();
  const docs = useQuery({ queryKey: ["unit-docs", unit.id], queryFn: () => api.get<UnitDoc[]>(`/api/v1/units/${unit.id}/documents`) });
  const [kind, setKind] = React.useState("floor_plan"); const [scope, setScope] = React.useState<"unit" | "project">("unit"); const [uploading, setUploading] = React.useState(false);
  const [sending, setSending] = React.useState<UnitDoc | null>(null); const [del, setDel] = React.useState<UnitDoc | null>(null);
  const input = React.useRef<HTMLInputElement>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["unit-docs", unit.id] });
  const upload = async (f: File) => {
    setUploading(true);
    try {
      const fd = new FormData(); fd.append("file", f); fd.append("doc_kind", kind);
      if (scope === "project") fd.append("project_id", unit.project_id); else fd.append("unit_id", unit.id);
      await api.upload("/api/v1/files", fd); refresh(); toast.success(`${DOC_KINDS.find((k) => k[0] === kind)?.[1]} added`);
    } catch (e) { toast.error(`Couldn't upload ${f.name}`, errText(e)); } finally { setUploading(false); if (input.current) input.current.value = ""; }
  };
  const open = async (d: UnitDoc) => { const r = await api.get<{ url: string }>(`/api/v1/files/${d.id}/url`); window.open(r.url, "_blank"); };
  const wa = has("whatsapp_integration") && can("emails.create");
  return (
    <section aria-label="Brochures and floor plans">
      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><FileText className="size-4 text-fg-muted" /> Brochures & floor plans</h3>
      {docs.isLoading ? <Skeleton className="h-16 w-full" /> : !docs.data?.length ? <p className="mb-2 text-sm text-fg-muted">Nothing yet. Add a floor plan for this flat, or a brochure for the whole project.</p> : (
        <ul className="mb-3 divide-y divide-border rounded-xl border border-border">
          {docs.data.map((d) => (
            <li key={d.id} className="flex items-center gap-3 px-3 py-2.5">
              <FileText className="size-5 shrink-0 text-fg-subtle" />
              <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{d.filename}</p><p className="text-xs text-fg-subtle">{DOC_KINDS.find((k) => k[0] === d.doc_kind)?.[1] ?? "Document"} · {d.scope === "unit" ? "this flat" : "whole project"}</p></div>
              <Button variant="ghost" size="icon-sm" aria-label={`Download ${d.filename}`} onClick={() => open(d)}><Download /></Button>
              {wa && <Button variant="secondary" size="sm" onClick={() => setSending(sending?.id === d.id ? null : d)} style={{ color: WA_GREEN }}><MessageCircle /> Send</Button>}
              {canEdit && can("files.delete") && <Button variant="ghost" size="icon-sm" aria-label={`Delete ${d.filename}`} onClick={() => setDel(d)}><Trash2 /></Button>}
            </li>
          ))}
        </ul>
      )}
      {sending && <SendDocForm doc={sending} unitId={unit.id} defaultLead={defaultLead} onDone={() => setSending(null)} />}
      {canEdit && can("files.create") && (
        <div className="flex flex-wrap items-center gap-2">
          <NativeSelect value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Document type" className="h-8 w-auto text-[13px]">{DOC_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect>
          <NativeSelect value={scope} onChange={(e) => setScope(e.target.value as "unit" | "project")} aria-label="Applies to" className="h-8 w-auto text-[13px]"><option value="unit">This flat</option><option value="project">Whole project</option></NativeSelect>
          <Button variant="secondary" size="sm" loading={uploading} onClick={() => input.current?.click()}><UploadCloud /> Upload PDF</Button>
          <input ref={input} type="file" accept="application/pdf,image/jpeg,image/png" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </div>
      )}
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete ${del?.filename}?`} description="It won't be available to send any more." confirmLabel="Delete" onConfirm={async () => { await api.delete(`/api/v1/files/${del!.id}`); refresh(); toast.success("Deleted"); }} />
    </section>
  );
}

function SendDocForm({ doc, unitId, defaultLead, onDone }: { doc: UnitDoc; unitId: string; defaultLead?: { id: string; name: string | null } | null; onDone: () => void }) {
  const qc = useQueryClient(); const toast = useToast();
  const [to, setTo] = React.useState<"lead" | "contact">("lead");
  const [rid, setRid] = React.useState<string | null>(defaultLead?.id ?? null);
  const [caption, setCaption] = React.useState(""); const [busy, setBusy] = React.useState(false);
  const send = async () => {
    setBusy(true);
    try {
      const m = await api.post<WaMessage>("/api/v1/whatsapp/send", { [`${to}_id`]: rid, file_id: doc.id, unit_id: unitId, caption: caption || undefined });
      toast.success("Sent on WhatsApp", m.kind === "template" ? "They haven't replied in 24 hours, so it went with your brochure template." : undefined);
      ["unit-history", "timeline", "wa-conversation"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); onDone();
    } catch (e) { toast.error("Couldn't send", errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="mb-3 space-y-3 rounded-xl border border-border bg-surface p-4">
      <p className="text-sm">Send <b>{doc.filename}</b> on WhatsApp</p>
      <div className="flex gap-1">{(["lead", "contact"] as const).map((k) => <button key={k} type="button" onClick={() => { setTo(k); setRid(null); }} aria-pressed={to === k} className={cn("h-8 rounded-full border px-3 text-[13px] font-medium", to === k ? "border-primary bg-primary-soft text-primary" : "border-border text-fg-muted hover:bg-surface-hover")}>{k === "lead" ? "Lead" : "Client"}</button>)}</div>
      <Field label="To"><AsyncSelect value={rid} onChange={setRid} endpoint={`/api/v1/${to}s`} initialLabel={to === "lead" && rid === defaultLead?.id ? defaultLead?.name : undefined} placeholder={to === "lead" ? "Search your leads…" : "Search your clients…"} /></Field>
      <Field label="Message (optional)" hint="Sent with the file when they've written to you in the last 24 hours."><Input value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={1000} placeholder="Here's the floor plan we discussed" /></Field>
      <div className="flex justify-end gap-2"><Button variant="ghost" size="sm" onClick={onDone}>Cancel</Button><Button size="sm" loading={busy} disabled={!rid} onClick={send}><Send /> Send</Button></div>
    </div>
  );
}
