"use client";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown } from "lucide-react";
import * as React from "react";
import { ApiError, Button, Field, Input, NativeSelect, Select, Textarea, Checkbox, cn, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { CALL_OUTCOMES, PRIORITIES, SOURCES, label as pretty } from "@/lib/constants";
import { useCustomFields, usePipelines, useMe } from "@/lib/queries";
import type { CustomFieldDef } from "@/lib/types";
import { AsyncSelect, MemberSelect, TagInput, fromLocalInput, toLocalInput } from "./fields";

export type Kind = "lead" | "contact" | "company" | "deal" | "task" | "meeting" | "note" | "call";
type FType = "text" | "email" | "tel" | "url" | "textarea" | "number" | "date" | "datetime" | "member" | "company" | "contact" | "tags" | "status" | "priority" | "source" | "stage" | "money" | "related" | "select" | "duration" | "checkbox";
export type FieldDef = { key: string; label: string; type: FType; required?: boolean; span?: 1 | 2; placeholder?: string; hint?: string; options?: [string, string][]; advanced?: boolean };

const F = (key: string, label: string, type: FType, extra: Partial<FieldDef> = {}): FieldDef => ({ key, label, type, ...extra });

export const FORMS: Record<Kind, { title: string; noun: string; endpoint: string; plural: string; fields: FieldDef[]; custom?: boolean }> = {
  lead: { title: "New lead", noun: "lead", plural: "leads", endpoint: "/api/v1/leads", custom: true, fields: [
    F("first_name", "First name", "text", { required: true }), F("last_name", "Last name", "text"), F("email", "Email", "email"), F("phone", "Phone", "tel"),
    F("company_name", "Company", "text"), F("job_title", "Job title", "text"), F("source", "Source", "source"), F("status", "Status", "status"), F("owner_id", "Owner", "member"),
    F("next_follow_up_at", "Next follow-up", "datetime"), F("location", "Location", "text", { advanced: true }), F("tags", "Tags", "tags", { span: 2, advanced: true }), F("description", "Notes", "textarea", { span: 2, advanced: true }),
  ] },
  contact: { title: "New contact", noun: "contact", plural: "contacts", endpoint: "/api/v1/contacts", custom: true, fields: [
    F("first_name", "First name", "text", { required: true }), F("last_name", "Last name", "text"), F("email", "Email", "email"), F("phone", "Phone", "tel"),
    F("company_id", "Company", "company"), F("job_title", "Job title", "text"), F("owner_id", "Owner", "member"), F("location", "Location", "text", { advanced: true }),
    F("tags", "Tags", "tags", { span: 2, advanced: true }), F("description", "Notes", "textarea", { span: 2, advanced: true }),
  ] },
  company: { title: "New company", noun: "company", plural: "companies", endpoint: "/api/v1/companies", custom: true, fields: [
    F("name", "Company name", "text", { required: true, span: 2 }), F("website", "Website", "url", { placeholder: "https://" }), F("industry", "Industry", "text"), F("size", "Size", "select", { options: [["1-10", "1–10"], ["11-50", "11–50"], ["51-200", "51–200"], ["201-500", "201–500"], ["501-1000", "501–1,000"], ["1001-5000", "1,001–5,000"], ["5000+", "5,000+"]] }),
    F("owner_id", "Owner", "member"), F("location", "Location", "text", { advanced: true }), F("annual_revenue", "Annual revenue", "number", { advanced: true }), F("phone", "Phone", "tel", { advanced: true }), F("tags", "Tags", "tags", { span: 2, advanced: true }), F("description", "Notes", "textarea", { span: 2, advanced: true }),
  ] },
  deal: { title: "New deal", noun: "deal", plural: "deals", endpoint: "/api/v1/deals", custom: true, fields: [
    F("name", "Deal name", "text", { required: true, span: 2 }), F("company_id", "Company", "company"), F("contact_id", "Contact", "contact"), F("value", "Value", "money"), F("stage_id", "Pipeline & stage", "stage"),
    F("expected_close_date", "Expected close", "date"), F("owner_id", "Owner", "member"), F("priority", "Priority", "priority"), F("source", "Source", "source", { advanced: true }), F("probability", "Probability %", "number", { advanced: true, hint: "Defaults to the stage's probability" }),
    F("tags", "Tags", "tags", { span: 2, advanced: true }), F("description", "Notes", "textarea", { span: 2, advanced: true }),
  ] },
  task: { title: "New task", noun: "task", plural: "tasks", endpoint: "/api/v1/tasks", fields: [
    F("title", "Title", "text", { required: true, span: 2 }), F("due_at", "Due", "datetime"), F("priority", "Priority", "priority"), F("assignee_id", "Assignee", "member"),
    F("kind", "Type", "select", { options: [["task", "Task"], ["follow_up", "Follow-up"], ["deadline", "Deadline"]] }), F("related", "Related to", "related", { span: 2 }), F("description", "Description", "textarea", { span: 2, advanced: true }),
  ] },
  meeting: { title: "Schedule meeting", noun: "meeting", plural: "meetings", endpoint: "/api/v1/meetings", fields: [
    F("title", "Title", "text", { required: true, span: 2 }), F("starts_at", "Starts", "datetime", { required: true }), F("duration", "Duration", "duration"), F("meeting_url", "Meeting link", "url", { placeholder: "https://meet…" }), F("location", "Location", "text"),
    F("attendees", "Attendee emails", "text", { span: 2, placeholder: "name@company.com, …", hint: "Separate with commas" }), F("related", "Related to", "related", { span: 2 }), F("description", "Agenda", "textarea", { span: 2, advanced: true }),
  ] },
  note: { title: "Add note", noun: "note", plural: "notes", endpoint: "/api/v1/notes", fields: [F("body", "Note", "textarea", { required: true, span: 2, placeholder: "Write a note…" }), F("related", "Related to", "related", { span: 2 })] },
  call: { title: "Log call", noun: "call", plural: "calls", endpoint: "/api/v1/calls", fields: [
    F("status", "Call", "select", { options: [["completed", "Completed (log it)"], ["scheduled", "Scheduled (for later)"]] }), F("direction", "Direction", "select", { options: [["outbound", "Outbound"], ["inbound", "Inbound"]] }),
    F("outcome", "Outcome", "select", { options: CALL_OUTCOMES.map(([a, b]) => [a, b] as [string, string]) }), F("when", "When", "datetime"), F("duration_minutes", "Duration (min)", "number"), F("phone", "Phone", "tel"),
    F("notes", "Call notes", "textarea", { span: 2 }), F("related", "Related to", "related", { span: 2 }),
  ] },
};

const REL_TYPES = [["contact", "Contact", "/api/v1/contacts"], ["deal", "Deal", "/api/v1/deals"], ["lead", "Lead", "/api/v1/leads"], ["company", "Company", "/api/v1/companies"]] as const;

function RelatedPicker({ value, onChange }: { value: { type: string; id: string } | null; onChange: (v: { type: string; id: string } | null) => void }) {
  const type = value?.type ?? "contact";
  const ep = REL_TYPES.find((r) => r[0] === type)![2];
  return (
    <div className="grid grid-cols-[130px_1fr] gap-2">
      <NativeSelect value={type} onChange={(e) => onChange(value ? { type: e.target.value, id: "" } : { type: e.target.value, id: "" })} aria-label="Related type">{REL_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect>
      <AsyncSelect endpoint={ep} value={value?.id} onChange={(id) => onChange(id ? { type, id } : null)} placeholder={`Link a ${type}…`} />
    </div>
  );
}

export function RecordForm({ kind, initial, defaults, onSaved, onCancel, id, submitLabel, hideActions, onView }: {
  kind: Kind; onView?: (rec: Record<string, unknown>) => void; initial?: Record<string, unknown> & { id?: string }; defaults?: Record<string, unknown>; onSaved: (rec: Record<string, unknown>) => void; onCancel?: () => void; id?: string; submitLabel?: string; hideActions?: boolean;
}) {
  const cfg = FORMS[kind];
  const qc = useQueryClient(); const toast = useToast();
  const { data: me } = useMe();
  const pipelines = usePipelines();
  const customDefs = useCustomFields(cfg.custom ? kind : undefined);
  const editing = !!initial?.id;
  const [values, setValues] = React.useState<Record<string, unknown>>(() => ({ ...(defaults ?? {}), ...(initial ?? {}) }));
  const [custom, setCustom] = React.useState<Record<string, unknown>>(() => ({ ...((initial?.custom as Record<string, unknown>) ?? {}) }));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [showAdvanced, setShowAdvanced] = React.useState(editing);
  const [dups, setDups] = React.useState<{ id: string; name: string; email: string }[]>([]);
  const set = (k: string, v: unknown) => { setValues((p) => ({ ...p, [k]: v })); if (errors[k]) setErrors((e) => { const n = { ...e }; delete n[k]; return n; }); };

  const stageOptions = (pipelines.data ?? []).flatMap((p) => p.stages.map((s) => ({ value: s.id, label: <span>{pipelines.data!.length > 1 && <span className="text-fg-subtle">{p.name} · </span>}{s.name}</span> })));
  const defaultStage = pipelines.data?.find((p) => p.is_default)?.stages.find((s) => s.kind === "open");
  React.useEffect(() => { if (kind === "deal" && !editing && !values.stage_id && defaultStage) set("stage_id", defaultStage.id); }, [defaultStage?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  React.useEffect(() => { if (kind === "lead" && !values.status) set("status", "new"); if (kind === "call" && !values.status) { set("status", "completed"); set("direction", "outbound"); } if (kind === "task" && !values.priority) { set("priority", "medium"); set("kind", "task"); } if (kind === "meeting" && !values.duration) set("duration", "30"); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const checkDup = async () => {
    if (editing || (kind !== "lead" && kind !== "contact") || !values.email) { setDups([]); return; }
    try { setDups(await api.get("/api/v1/duplicates/check", { entity_type: kind, email: values.email as string, phone: values.phone as string })); } catch { /* non-critical */ }
  };

  const render = (f: FieldDef) => {
    const v = values[f.key];
    const common = { id: `${id ?? kind}-${f.key}` };
    switch (f.type) {
      case "textarea": return <Textarea {...common} rows={f.key === "body" ? 5 : 3} value={(v as string) ?? ""} onChange={(e) => set(f.key, e.target.value)} placeholder={f.placeholder} />;
      case "member": return <MemberSelect {...common} value={v as string | null} onChange={(x) => set(f.key, x)} />;
      case "company": return <AsyncSelect {...common} endpoint="/api/v1/companies" value={v as string} initialLabel={(initial?.company as { name: string } | null)?.name ?? (defaults?._company_label as string)} onChange={(x) => set(f.key, x)} placeholder="Search companies…" onCreate={async (name) => { const c = await api.post<{ id: string; name: string }>("/api/v1/companies", { name }); qc.invalidateQueries({ queryKey: ["async-select"] }); return { id: c.id, label: c.name }; }} />;
      case "contact": return <AsyncSelect {...common} endpoint="/api/v1/contacts" value={v as string} initialLabel={(initial?.contact as { name: string } | null)?.name ?? (defaults?._contact_label as string)} onChange={(x, item) => { set(f.key, x); if (item?.company_id && !values.company_id && kind === "deal") { set("company_id", item.company_id); } }} placeholder="Search contacts…" />;
      case "tags": return <TagInput {...common} value={(v as string[]) ?? []} onChange={(x) => set(f.key, x)} />;
      case "status": return <Select {...common} value={(v as string) ?? "new"} onValueChange={(x) => set(f.key, x)} options={(me?.workspace?.lead_statuses ?? []).filter((s) => s.key !== "converted" || v === "converted").map((s) => ({ value: s.key, label: s.label }))} />;
      case "priority": return <Select {...common} value={(v as string) ?? "medium"} onValueChange={(x) => set(f.key, x)} options={PRIORITIES.map(([a, b]) => ({ value: a, label: b }))} />;
      case "source": return <Select {...common} value={(v as string) ?? undefined} onValueChange={(x) => set(f.key, x)} placeholder="Select source" options={SOURCES.map((s) => ({ value: s, label: pretty(s) }))} />;
      case "stage": return <Select {...common} value={(v as string) ?? undefined} onValueChange={(x) => set(f.key, x)} options={stageOptions} placeholder="Select stage" />;
      case "money": return <div className="flex gap-2"><Input {...common} type="number" min={0} inputMode="decimal" value={(v as string | number) ?? ""} onChange={(e) => set(f.key, e.target.value)} placeholder="0" /><NativeSelect className="w-24" value={(values.currency as string) ?? me?.workspace?.currency ?? "INR"} onChange={(e) => set("currency", e.target.value)} aria-label="Currency">{["INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD"].map((c) => <option key={c}>{c}</option>)}</NativeSelect></div>;
      case "number": return <Input {...common} type="number" min={0} value={(v as string | number) ?? ""} onChange={(e) => set(f.key, e.target.value)} />;
      case "date": return <Input {...common} type="date" value={(v as string) ?? ""} onChange={(e) => set(f.key, e.target.value)} />;
      case "datetime": return <Input {...common} type="datetime-local" value={toLocalInput(v as string)} onChange={(e) => set(f.key, fromLocalInput(e.target.value))} />;
      case "duration": return <NativeSelect {...common} value={(v as string) ?? "30"} onChange={(e) => set(f.key, e.target.value)}>{[15, 30, 45, 60, 90, 120].map((m) => <option key={m} value={m}>{m} minutes</option>)}</NativeSelect>;
      case "select": return <NativeSelect {...common} value={(v as string) ?? ""} onChange={(e) => set(f.key, e.target.value || null)}>{!f.options?.some(([k]) => k === (v ?? "")) && <option value="">Select…</option>}{f.options!.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect>;
      case "related": return <RelatedPicker value={v as { type: string; id: string } | null} onChange={(x) => set(f.key, x)} />;
      case "checkbox": return <Checkbox checked={!!v} onCheckedChange={(c) => set(f.key, c)} />;
      default: return <Input {...common} type={f.type === "tel" ? "tel" : f.type} value={(v as string) ?? ""} onChange={(e) => set(f.key, e.target.value)} onBlur={f.key === "email" || f.key === "phone" ? checkDup : undefined} placeholder={f.placeholder} />;
    }
  };

  const payload = () => {
    const p: Record<string, unknown> = {};
    for (const f of cfg.fields) {
      let v = values[f.key];
      if (f.key === "duration" || f.key === "when" || f.key === "duration_minutes") continue;
      if (f.type === "related") {
        const r = v as { type: string; id: string } | null;
        if (r?.id) p[`${r.type}_id`] = r.id;
        for (const t of ["lead", "contact", "company", "deal"]) if (defaults?.[`${t}_id`] && !p[`${t}_id`]) p[`${t}_id`] = defaults[`${t}_id`];
        continue;
      }
      if (v === "" || v === undefined) v = null;
      if (f.key === "attendees") v = typeof v === "string" ? v.split(",").map((s) => s.trim()).filter(Boolean).map((email) => ({ name: email.split("@")[0], email })) : [];
      if (["value", "annual_revenue", "probability"].includes(f.key) && v !== null) v = Number(v);
      if (f.key === "tags") v = v ?? [];
      p[f.key] = v;
    }
    if (kind === "deal") { p.currency = values.currency ?? me?.workspace?.currency ?? "INR"; if (!p.value) p.value = 0; }
    if (kind === "meeting") { const start = new Date(values.starts_at as string); p.ends_at = new Date(start.getTime() + Number(values.duration ?? 30) * 60000).toISOString(); }
    if (kind === "call") { const when = values.when as string | null; if (p.status === "scheduled") p.scheduled_at = when; else p.occurred_at = when ?? new Date().toISOString(); p.duration_seconds = values.duration_minutes ? Number(values.duration_minutes) * 60 : null; if (!p.outcome) p.outcome = null; }
    if (kind === "meeting" || kind === "task" || kind === "note" || kind === "call") for (const t of ["lead", "contact", "company", "deal"]) if (defaults?.[`${t}_id`] && !p[`${t}_id`]) p[`${t}_id`] = defaults[`${t}_id`];
    if (cfg.custom && Object.keys(custom).length) p.custom = custom;
    return p;
  };

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const errs: Record<string, string> = {};
    for (const f of cfg.fields) if (f.required && !String(values[f.key] ?? "").trim()) errs[f.key] = `${f.label} is required`;
    if (kind === "call" && values.status === "scheduled" && !values.when) errs.when = "Choose when the call is scheduled";
    for (const d of customDefs.data ?? []) if (d.required && (custom[d.key] === undefined || custom[d.key] === "" || (Array.isArray(custom[d.key]) && !(custom[d.key] as unknown[]).length))) errs[`custom.${d.key}`] = `${d.label} is required`;
    if (Object.keys(errs).length) { setErrors(errs); setShowAdvanced(true); return; }
    setBusy(true); setFormError(null);
    try {
      const rec = editing ? await api.patch<Record<string, unknown>>(`${cfg.endpoint}/${initial!.id}`, payload()) : await api.post<Record<string, unknown>>(cfg.endpoint, payload());
      qc.invalidateQueries({ queryKey: [cfg.plural] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); qc.invalidateQueries({ queryKey: ["timeline"] }); qc.invalidateQueries({ queryKey: ["board"] }); qc.invalidateQueries({ queryKey: ["tasks-summary-badge"] });
      qc.invalidateQueries({ queryKey: ["record"] }); qc.invalidateQueries({ queryKey: ["calendar"] });
      toast.toast({ tone: "success", title: `${pretty(cfg.noun)} ${editing ? "updated" : kind === "note" ? "added" : kind === "call" ? "logged" : "created"}`, action: onView && !editing ? { label: "View", onClick: () => onView(rec) } : undefined });
      onSaved(rec);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.details ?? {});
        const mapped = Object.keys(err.details ?? {}).some((k) => cfg.fields.some((f) => f.key === k) || k.startsWith("custom."));
        setFormError(err.code === "validation_error" && mapped ? null : err.message);
        if (err.code === "plan_limit_reached") setFormError(err.message);
      } else setFormError("Something went wrong. Please try again.");
    } finally { setBusy(false); }
  };

  const main = cfg.fields.filter((f) => !f.advanced);
  const adv = cfg.fields.filter((f) => f.advanced);
  const hasAdvanced = adv.length > 0 || (customDefs.data?.length ?? 0) > 0;
  const grid = (fs: FieldDef[]) => fs.map((f) => (
    <Field key={f.key} label={f.label} required={f.required} error={errors[f.key]} hint={f.hint} className={cn(f.span === 2 && "sm:col-span-2")}>{render(f)}</Field>
  ));

  return (
    <form id={id ?? `form-${kind}`} onSubmit={submit} className="space-y-5" noValidate>
      {dups.length > 0 && (
        <div role="alert" className="flex gap-3 rounded-lg border border-warning/40 bg-warning-soft p-3.5 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
          <div><p className="font-medium text-warning">Possible duplicate</p><p className="mt-0.5 text-fg-muted">{dups.map((d) => `${d.name}${d.email ? ` (${d.email})` : ""}`).join(", ")} already exists. You can still save.</p></div>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">{grid(main)}</div>
      {hasAdvanced && (
        <div>
          <button type="button" onClick={() => setShowAdvanced((s) => !s)} aria-expanded={showAdvanced} className="flex items-center gap-1.5 text-sm font-medium text-fg-muted hover:text-fg"><ChevronDown className={cn("size-4 transition-transform", showAdvanced && "rotate-180")} />{showAdvanced ? "Fewer options" : "More options"}</button>
          {showAdvanced && (
            <div className="mt-4 grid animate-fade-in gap-4 sm:grid-cols-2">
              {grid(adv)}
              {(customDefs.data ?? []).map((d) => <Field key={d.id} label={d.label} required={d.required} error={errors[`custom.${d.key}`]} className={cn(d.field_type === "multi_select" && "sm:col-span-2")}><CustomInput def={d} value={custom[d.key]} onChange={(v) => setCustom((c) => ({ ...c, [d.key]: v }))} /></Field>)}
            </div>
          )}
        </div>
      )}
      {formError && <p role="alert" className="rounded-lg bg-danger-soft px-3.5 py-2.5 text-sm text-danger">{formError}</p>}
      {!hideActions && <div className="flex justify-end gap-2 pt-1">{onCancel && <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>}<Button type="submit" loading={busy}>{submitLabel ?? (editing ? "Save changes" : `Create ${cfg.noun}`)}</Button></div>}
    </form>
  );
}

export function CustomInput({ def, value, onChange }: { def: CustomFieldDef; value: unknown; onChange: (v: unknown) => void }) {
  const v = value as never;
  switch (def.field_type) {
    case "number": case "currency": return <Input type="number" value={(v as string) ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />;
    case "date": return <Input type="date" value={(v as string) ?? ""} onChange={(e) => onChange(e.target.value)} />;
    case "checkbox": return <div className="flex h-9 items-center"><Checkbox checked={!!v} onCheckedChange={onChange} /></div>;
    case "dropdown": return <NativeSelect value={(v as string) ?? ""} onChange={(e) => onChange(e.target.value)}><option value="">—</option>{def.options.map((o) => <option key={o}>{o}</option>)}</NativeSelect>;
    case "multi_select": { const cur = (v as string[]) ?? []; return <div className="flex flex-wrap gap-2">{def.options.map((o) => <button type="button" key={o} onClick={() => onChange(cur.includes(o) ? cur.filter((x) => x !== o) : [...cur, o])} className={cn("rounded-full border px-3 py-1 text-xs font-medium", cur.includes(o) ? "border-primary bg-primary-soft text-primary" : "border-border text-fg-muted hover:bg-surface-hover")}>{o}</button>)}</div>; }
    default: return <Input type={def.field_type === "email" ? "email" : def.field_type === "url" ? "url" : def.field_type === "phone" ? "tel" : "text"} value={(v as string) ?? ""} onChange={(e) => onChange(e.target.value)} />;
  }
}
