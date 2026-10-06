"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, ArrowRight, Check, CheckCircle2, Download, FileSpreadsheet, GitMerge, Search, UploadCloud, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { Avatar, Badge, Button, Card, EmptyState, Input, NativeSelect, Progress, Segmented, Skeleton, Table, TD, TH, THead, TR, cn, formatDate, timeAgo, useDebounce, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { Divided, FieldRow, SettingsSection } from "./ui";

type Ent = "leads" | "contacts" | "companies" | "deals";
type FieldDef = { key: string; label: string; required?: boolean; hint?: string };
type Parsed = { headers: string[]; rows: Record<string, string>[]; suggested_mapping: Record<string, string>; fields: FieldDef[]; filename: string };
type Err = { row: number; field: string; message: string; severity?: string; value?: string };
type Validation = { total: number; valid: number; errors: Err[] };

function ImportWizard() {
  const sp = useSearchParams(); const toast = useToast(); const qc = useQueryClient();
  const [ent, setEnt] = React.useState<Ent>((sp.get("import") as Ent) || "contacts"); const [step, setStep] = React.useState(0);
  const [parsed, setParsed] = React.useState<Parsed | null>(null); const [rows, setRows] = React.useState<Record<string, string>[]>([]); const [map, setMap] = React.useState<Record<string, string>>({});
  const [val, setVal] = React.useState<Validation | null>(null); const [busy, setBusy] = React.useState(false); const [skipDup, setSkipDup] = React.useState(true); const [result, setResult] = React.useState<{ created: number; skipped: number; errors: Err[] } | null>(null); const [drag, setDrag] = React.useState(false);
  const input = React.useRef<HTMLInputElement>(null);
  const reset = () => { setStep(0); setParsed(null); setRows([]); setMap({}); setVal(null); setResult(null); };
  const upload = async (f: File) => {
    setBusy(true); const fd = new FormData(); fd.append("file", f); fd.append("entity_type", ent);
    try { const p = await api.upload<Parsed>("/api/v1/import/parse", fd); setParsed(p); setRows(p.rows); setMap(p.suggested_mapping); setStep(1); } catch (e) { toast.error("Couldn't read that file", (e as Error).message); } finally { setBusy(false); }
  };
  const validate = async () => { setBusy(true); try { const v = await api.post<Validation>("/api/v1/import/validate", { entity_type: ent, mapping: map, rows }); setVal(v); setStep(2); } catch (e) { toast.error("Check your mapping", (e as Error).message); } finally { setBusy(false); } };
  const commit = async () => { setBusy(true); try { const r = await api.post<{ created: number; skipped: number; errors: Err[] }>("/api/v1/import/commit", { entity_type: ent, mapping: map, rows, skip_duplicates: skipDup, filename: parsed?.filename }); setResult(r); setStep(3); ["leads", "contacts", "companies", "deals", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); } catch (e) { toast.error("Import failed", (e as Error).message); } finally { setBusy(false); } };
  const required = parsed?.fields.filter((f) => f.required).map((f) => f.key) ?? []; const nameMapped = map.first_name || map.full_name || map.name;
  const errRows = val ? [...new Set(val.errors.filter((e) => e.severity !== "warning").map((e) => e.row))] : []; const dupRows = val ? [...new Set(val.errors.filter((e) => e.severity === "warning").map((e) => e.row))] : [];
  const steps = ["Upload", "Map columns", "Review", "Done"];
  return (
    <SettingsSection title="Import data" description="Bring leads, contacts, companies or deals from a CSV. Fix problems before anything is imported.">
      <ol className="mb-6 flex items-center gap-2 text-sm" aria-label="Import steps">{steps.map((s, i) => <li key={s} className="flex items-center gap-2"><span className={cn("flex size-6 items-center justify-center rounded-full text-xs font-semibold", i < step ? "bg-success text-white" : i === step ? "bg-primary text-primary-fg" : "bg-bg-subtle text-fg-subtle")}>{i < step ? <Check className="size-3.5" /> : i + 1}</span><span className={cn("hidden sm:inline", i === step ? "font-medium" : "text-fg-muted")}>{s}</span>{i < 3 && <span className="mx-1 h-px w-6 bg-border" />}</li>)}</ol>
      {step === 0 && (
        <div className="space-y-4"><Segmented value={ent} onChange={(v) => setEnt(v)} options={[{ value: "contacts", label: "Contacts" }, { value: "leads", label: "Leads" }, { value: "companies", label: "Companies" }, { value: "deals", label: "Deals" }]} />
          <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); }} className={cn("flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed p-12 text-center transition-colors", drag ? "border-primary bg-primary-soft/40" : "border-border")}>
            <span className="flex size-12 items-center justify-center rounded-xl bg-primary-soft text-primary"><UploadCloud className="size-6" /></span><p className="text-sm">Drag a CSV here, or <button className="font-medium text-primary hover:underline" onClick={() => input.current?.click()}>choose a file</button></p><p className="text-xs text-fg-subtle">Up to 5,000 rows · first row must be headers · UTF-8 or Excel-exported CSV</p>{busy && <Progress value={60} className="w-48" />}
            <input ref={input} type="file" accept=".csv,text/csv" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></div>
          <p className="text-xs text-fg-subtle">Tip: a header like “Name”, “Email”, “Company” maps automatically. <a className="text-primary hover:underline" href={`data:text/csv;charset=utf-8,${encodeURIComponent(ent === "deals" ? "name,company,value,stage,expected_close_date\nAcme rollout,Acme Corp,500000,Proposal,2026-12-01\n" : "first_name,last_name,email,phone,company,job_title\nAsha,Rao,asha@acme.io,+91 98765 43210,Acme Corp,CEO\n")}`} download={`${ent}-template.csv`}>Download a sample file</a></p></div>
      )}
      {step === 1 && parsed && (
        <div className="space-y-4"><p className="flex items-center gap-2 text-sm text-fg-muted"><FileSpreadsheet className="size-4" />{parsed.filename} · {rows.length} rows</p>
          <div className="overflow-x-auto rounded-xl border border-border"><Table><THead><TR><TH className="pl-4">CRM field</TH><TH>CSV column</TH><TH>Preview</TH></TR></THead><tbody>
            {parsed.fields.map((f) => <TR key={f.key}><TD className="pl-4"><span className="font-medium">{f.label}</span>{f.required && <span className="ml-1 text-danger">*</span>}{f.hint && <span className="block text-xs text-fg-subtle">{f.hint}</span>}</TD><TD><NativeSelect className="max-w-56" value={map[f.key] ?? ""} onChange={(e) => setMap((m) => { const n = { ...m }; e.target.value ? (n[f.key] = e.target.value) : delete n[f.key]; return n; })} aria-label={`Column for ${f.label}`}><option value="">— skip —</option>{parsed.headers.map((h) => <option key={h}>{h}</option>)}</NativeSelect></TD><TD className="max-w-[260px] truncate text-[13px] text-fg-muted">{map[f.key] ? rows.slice(0, 3).map((r) => r[map[f.key]]).filter(Boolean).join(" · ") : "—"}</TD></TR>)}</tbody></Table></div>
          {!nameMapped && <p role="alert" className="text-sm text-warning">Map a name column to continue.</p>}
          <div className="flex justify-between"><Button variant="ghost" onClick={reset}><ArrowLeft /> Start over</Button><Button onClick={validate} loading={busy} disabled={!nameMapped && required.length > 0}>Review & validate <ArrowRight /></Button></div></div>
      )}
      {step === 2 && val && parsed && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3"><Card className="p-4"><p className="text-xs text-fg-muted">Ready to import</p><p className="tabular mt-1 text-2xl font-semibold text-success">{val.valid - dupRows.filter((r) => !errRows.includes(r)).length * (skipDup ? 1 : 0)}</p></Card><Card className="p-4"><p className="text-xs text-fg-muted">Rows with errors</p><p className="tabular mt-1 text-2xl font-semibold text-danger">{errRows.length}</p></Card><Card className="p-4"><p className="text-xs text-fg-muted">Possible duplicates</p><p className="tabular mt-1 text-2xl font-semibold text-warning">{dupRows.length}</p></Card></div>
          {errRows.length > 0 && <div><p className="mb-2 text-sm font-medium">Fix errors below (or skip those rows)</p><div className="max-h-80 overflow-auto rounded-xl border border-border"><Table><THead><TR><TH className="pl-4">Row</TH><TH>Field</TH><TH>Value (editable)</TH><TH>Problem</TH></TR></THead><tbody>
            {val.errors.filter((e) => e.severity !== "warning").slice(0, 100).map((e, i) => { const header = map[e.field] ?? (e.field === "first_name" ? map.full_name : undefined); return <TR key={i}><TD className="pl-4 tabular text-fg-muted">{e.row + 2}</TD><TD>{parsed.fields.find((f) => f.key === e.field)?.label ?? e.field}</TD><TD>{header ? <Input className="h-8 min-w-40" value={rows[e.row]?.[header] ?? ""} onChange={(ev) => setRows((r) => r.map((x, k) => (k === e.row ? { ...x, [header]: ev.target.value } : x)))} aria-label={`Fix ${e.field} on row ${e.row + 2}`} /> : <span className="text-fg-subtle">—</span>}</TD><TD className="text-[13px] text-danger">{e.message}</TD></TR>; })}</tbody></Table></div><Button className="mt-3" variant="secondary" size="sm" onClick={validate} loading={busy}>Re-check after edits</Button></div>}
          {dupRows.length > 0 && <label className="flex items-center gap-3 rounded-lg border border-border p-3.5 text-sm"><input type="checkbox" checked={skipDup} onChange={(e) => setSkipDup(e.target.checked)} className="size-4 accent-[var(--primary)]" /><span><strong>Skip {dupRows.length} possible duplicate{dupRows.length === 1 ? "" : "s"}</strong><span className="block text-xs text-fg-muted">Same email already in your CRM or earlier in this file.</span></span></label>}
          <div className="flex justify-between"><Button variant="ghost" onClick={() => setStep(1)}><ArrowLeft /> Back</Button><Button onClick={commit} loading={busy} disabled={val.valid === 0}>Import {val.valid - (skipDup ? dupRows.filter((r) => !errRows.includes(r)).length : 0)} {ent}<ArrowRight /></Button></div>
        </div>
      )}
      {step === 3 && result && (
        <div className="flex flex-col items-center py-8 text-center"><span className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-success-soft text-success"><CheckCircle2 className="size-7" /></span><h3 className="text-xl font-semibold">Import complete</h3><p className="mt-1 text-fg-muted"><strong className="text-fg">{result.created}</strong> {ent} created{result.skipped ? ` · ${result.skipped} skipped` : ""}.</p>
          <div className="mt-6 flex gap-2"><Button asChild><Link href={`/app/${ent}`}>View {ent}</Link></Button><Button variant="secondary" onClick={reset}>Import another file</Button></div></div>
      )}
    </SettingsSection>
  );
}

type Group = { reason: string; key: string; records: { id: string; name: string; email: string | null; phone: string | null; company: string | null; created_at: string }[] };
function Duplicates() {
  const { can } = useAccess(); const toast = useToast(); const [type, setType] = React.useState<"contact" | "lead">("contact"); const [primary, setPrimary] = React.useState<Record<string, string>>({});
  const q = useQuery({ queryKey: ["duplicates", type], queryFn: () => api.get<Group[]>("/api/v1/duplicates", { entity_type: type }) });
  const merge = async (g: Group) => { const p = primary[g.key] ?? g.records[0].id; try { await api.post("/api/v1/duplicates/merge", { entity_type: type, primary_id: p, merge_ids: g.records.map((r) => r.id).filter((x) => x !== p) }); toast.success("Merged", "History and related records moved to the kept record."); q.refetch(); } catch (e) { toast.error("Couldn't merge", (e as Error).message); } };
  const ignore = async (g: Group) => { await api.post("/api/v1/duplicates/ignore", { entity_type: type, ids: g.records.map((r) => r.id) }); toast.success("Marked as not duplicates"); q.refetch(); };
  return (
    <SettingsSection title="Possible duplicates" description="Matched on email, phone and name + company. Merging keeps all history." actions={<Segmented size="sm" value={type} onChange={setType} options={[{ value: "contact", label: "Contacts" }, { value: "lead", label: "Leads" }]} />}>
      {q.isLoading ? <Skeleton className="h-32" /> : !q.data?.length ? <EmptyState compact icon={<CheckCircle2 />} title="No duplicates found" description="Your data looks clean." /> : (
        <ul className="space-y-4">{q.data.map((g) => (
          <li key={g.key} className="rounded-xl border border-border"><div className="flex items-center justify-between border-b border-border bg-surface-2 px-4 py-2.5"><span className="flex items-center gap-2 text-[13px] font-medium"><AlertTriangle className="size-4 text-warning" />Possible duplicate · <span className="text-fg-muted">{g.reason}</span></span>{can(`${type}s.update`) && <div className="flex gap-2"><Button size="xs" variant="ghost" onClick={() => ignore(g)}>Ignore</Button><Button size="xs" onClick={() => merge(g)} disabled={!can(`${type}s.delete`)}><GitMerge /> Merge</Button></div>}</div>
            <ul className="divide-y divide-border">{g.records.map((r, i) => <li key={r.id}><label className="flex cursor-pointer items-center gap-3 px-4 py-3"><input type="radio" name={g.key} checked={(primary[g.key] ?? g.records[0].id) === r.id} onChange={() => setPrimary({ ...primary, [g.key]: r.id })} className="accent-[var(--primary)]" aria-label={`Keep ${r.name}`} /><Avatar name={r.name} size={32} /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{r.name}{i === 0 && <Badge tone="neutral" className="ml-2">Oldest</Badge>}</span><span className="block truncate text-xs text-fg-muted">{[r.email, r.phone, r.company].filter(Boolean).join(" · ")}</span></span><span className="text-xs text-fg-subtle">added {timeAgo(r.created_at)}</span></label></li>)}</ul><p className="border-t border-border px-4 py-2 text-xs text-fg-subtle">Selected record is kept; the others are merged into it.</p></li>))}</ul>)}
    </SettingsSection>
  );
}

export function DataSettings() {
  const { can } = useAccess(); const toast = useToast();
  const jobs = useQuery({ queryKey: ["import-jobs"], enabled: can("data.import"), queryFn: () => api.get<{ id: string; entity_type: string; filename: string | null; created_count: number; skipped_count: number; error_count: number; created_at: string }[]>("/api/v1/import/jobs") });
  const exp = async (path: string, name: string) => { const r = await api.raw("GET", path); if (!r.ok) return toast.error("Export failed"); const u = URL.createObjectURL(await r.blob()); const a = document.createElement("a"); a.href = u; a.download = name; a.click(); URL.revokeObjectURL(u); };
  return (
    <div className="space-y-6">
      {can("data.import") && <ImportWizard />}
      {can("data.export") && <SettingsSection title="Export your data" description="Your data is always yours — export it any time, even if your subscription lapses."><Divided>
        <FieldRow label="Everything" hint="ZIP with leads, contacts, companies, deals, tasks and notes (CSV)."><Button variant="secondary" onClick={() => exp("/api/v1/export/workspace", "workspace-export.zip")}><Download /> Download full export</Button></FieldRow>
        <FieldRow label="Individual lists"><div className="flex flex-wrap gap-2">{["leads", "contacts", "companies", "deals", "tasks"].map((e) => <Button key={e} size="sm" variant="secondary" onClick={() => exp(`/api/v1/${e}/export`, `${e}.csv`)}>{e[0].toUpperCase() + e.slice(1)} CSV</Button>)}</div></FieldRow></Divided></SettingsSection>}
      {can("contacts.update") && <Duplicates />}
      {!!jobs.data?.length && <SettingsSection title="Import history"><ul className="divide-y divide-border">{jobs.data.map((j) => <li key={j.id} className="flex items-center justify-between gap-3 py-3 text-sm"><span><span className="font-medium capitalize">{j.entity_type}</span> <span className="text-fg-muted">· {j.filename ?? "CSV"}</span></span><span className="text-xs text-fg-muted">{j.created_count} created · {j.skipped_count} skipped · {formatDate(j.created_at, "datetime")}</span></li>)}</ul></SettingsSection>}
    </div>
  );
}

type Log = { id: string; created_at: string; actor_type: string; actor_label: string | null; action: string; summary: string | null; before: unknown; after: unknown; ip: string | null };
export function AuditSettings() {
  const [q, setQ] = React.useState(""); const dq = useDebounce(q); const [page, setPage] = React.useState(1); const [open, setOpen] = React.useState<string | null>(null);
  const r = useQuery({ queryKey: ["audit", dq, page], queryFn: () => api.page<Log>("/api/v1/audit-logs", { q: dq, page, per_page: 30 }) });
  return (
    <SettingsSection title="Audit log" description="Who did what, and when — every important change in your workspace." actions={<div className="w-56"><Input icon={<Search />} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Search…" aria-label="Search audit log" /></div>}>
      {r.isLoading ? <Skeleton className="h-64" /> : !r.data?.data.length ? <EmptyState compact title="No events found" /> : <>
        <ul className="divide-y divide-border">{r.data.data.map((l) => (
          <li key={l.id} className="py-3"><button className="flex w-full items-start gap-3 text-left" onClick={() => setOpen(open === l.id ? null : l.id)}><Avatar name={l.actor_label ?? "System"} size={30} /><span className="min-w-0 flex-1"><span className="block text-sm">{l.summary ?? l.action}</span><span className="text-xs text-fg-muted">{l.actor_label ?? "System"}{l.actor_type === "admin" && <Badge tone="warning" className="ml-1.5">Support</Badge>} · <code>{l.action}</code>{l.ip ? ` · ${l.ip}` : ""}</span></span><time className="shrink-0 text-xs text-fg-subtle">{formatDate(l.created_at, "datetime")}</time></button>
            {open === l.id && (!!l.before || !!l.after) && <div className="ml-11 mt-2 grid gap-2 sm:grid-cols-2">{[["Before", l.before], ["After", l.after]].map(([t, v]) => <pre key={t as string} className="overflow-auto rounded-lg bg-bg-subtle p-3 text-xs"><span className="mb-1 block font-sans font-semibold text-fg-muted">{t as string}</span>{JSON.stringify(v ?? {}, null, 2)}</pre>)}</div>}</li>))}</ul>
        <div className="mt-4 flex items-center justify-between text-[13px] text-fg-muted"><span>Page {r.data.meta.page} of {r.data.meta.pages}</span><div className="flex gap-2"><Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><Button size="sm" variant="secondary" disabled={page >= r.data.meta.pages} onClick={() => setPage(page + 1)}>Next</Button></div></div></>}
    </SettingsSection>
  );
}
export { XCircle };
