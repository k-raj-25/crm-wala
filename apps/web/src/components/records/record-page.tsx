"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Building2, Calendar, CheckSquare, ChevronRight, Copy, Handshake, Link2, Mail, MoreHorizontal, Pencil, Phone, Sparkles, StickyNote, Trash2, Trophy, UserCheck, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, ColorChip, ConfirmDialog, Dialog, DialogContent, DialogFooter, Drawer, DropdownContent, DropdownItem, DropdownMenu, DropdownSeparator, DropdownTrigger, ErrorState, Field, Input, Skeleton, Switch, Tabs, TabsContent, TabsList, TabsTrigger, cn, formatDate, formatMoney, timeAgo, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { celebrate } from "@/lib/confetti";
import { PRIORITIES, SOURCES, label } from "@/lib/constants";
import { useAccess, useCustomFields, useMe, usePipelines } from "@/lib/queries";
import type { Company, Contact, Deal, Lead } from "@/lib/types";
import { AsyncSelect, MemberSelect, TagInput, fromLocalInput, toLocalInput } from "../forms/fields";
import { FORMS, RecordForm } from "../forms/record-form";
import { Markdown } from "../markdown";
import { PageContainer } from "../shell/page";
import { useUI } from "../shell/ui-context";
import { InlineField } from "./inline-field";
import { CallsTab, ContactsTab, DealsTab, EmailsTab, FilesTab, MeetingsTab, NotesTab, TasksTab, type Scope } from "./related";
import { Timeline } from "./timeline";
import { ScorePill } from "../list/cells";

type Entity = "lead" | "contact" | "company" | "deal";
const PLURAL: Record<Entity, string> = { lead: "leads", contact: "contacts", company: "companies", deal: "deals" };
type Rec = (Lead | Contact | Company | Deal) & Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function Section({ title, children, actions }: { title: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return <Card><CardHeader title={title} actions={actions} className="!pt-4" /><CardBody className="pt-2"><dl className="divide-y divide-border/60">{children}</dl></CardBody></Card>;
}

function ConvertDialog({ lead, open, onOpenChange }: { lead: Lead; open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter(); const qc = useQueryClient(); const toast = useToast(); const { can } = useAccess(); const pipelines = usePipelines();
  const [company, setCompany] = React.useState(true); const [deal, setDeal] = React.useState(false); const [name, setName] = React.useState(""); const [value, setValue] = React.useState(""); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  React.useEffect(() => { if (open) { setName(`${lead.company_name || lead.name} — New deal`); setValue(""); setErr(null); } }, [open, lead]);
  const go = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.post<{ contact_id: string; deal_id: string | null }>(`/api/v1/leads/${lead.id}/convert`, { create_company: company && !!lead.company_name, create_deal: deal, deal_name: name, deal_value: Number(value) || 0 });
      qc.invalidateQueries(); toast.success("Lead converted", deal ? "Contact and deal created." : "Contact created."); onOpenChange(false); router.push(r.deal_id ? `/app/deals/${r.deal_id}` : `/app/contacts/${r.contact_id}`);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm" title="Convert lead" description={`${lead.name} becomes a contact. Their history comes with them.`}>
        <div className="space-y-4">
          {lead.company_name && <label className="flex items-center justify-between gap-4 rounded-lg border border-border p-3.5 text-sm"><span><span className="block font-medium">Create company “{lead.company_name}”</span><span className="text-xs text-fg-muted">Reuses an existing company with the same name</span></span><Switch checked={company} onCheckedChange={setCompany} aria-label="Create company" /></label>}
          {can("deals.create") && <label className="flex items-center justify-between gap-4 rounded-lg border border-border p-3.5 text-sm"><span><span className="block font-medium">Create a deal</span><span className="text-xs text-fg-muted">Starts in {pipelines.data?.find((p) => p.is_default)?.stages[0]?.name ?? "the first stage"}</span></span><Switch checked={deal} onCheckedChange={setDeal} aria-label="Create deal" /></label>}
          {deal && <div className="animate-fade-in space-y-3"><Field label="Deal name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field><Field label="Deal value"><Input type="number" min={0} value={value} onChange={(e) => setValue(e.target.value)} placeholder="0" /></Field></div>}
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={go} loading={busy}><UserCheck /> Convert lead</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function StageStepper({ deal, onMove }: { deal: Deal; onMove: (stageId: string, extra?: Record<string, unknown>) => void }) {
  const { data } = usePipelines();
  const stages = data?.find((p) => p.id === deal.pipeline_id)?.stages ?? [];
  const open = stages.filter((s) => s.kind === "open"); const idx = open.findIndex((s) => s.id === deal.stage.id);
  return (
    <ol className="flex w-full overflow-x-auto" aria-label="Deal stage">
      {open.map((s, i) => {
        const state = deal.status !== "open" ? (deal.status === "won" ? "past" : "future") : i < idx ? "past" : i === idx ? "current" : "future";
        return <li key={s.id} className="min-w-[110px] flex-1"><button onClick={() => s.id !== deal.stage.id && onMove(s.id)} disabled={deal.status !== "open"} aria-current={state === "current" ? "step" : undefined} className={cn("relative flex h-9 w-full items-center justify-center px-4 text-[13px] font-medium transition-colors [clip-path:polygon(0_0,calc(100%-12px)_0,100%_50%,calc(100%-12px)_100%,0_100%,12px_50%)] first:[clip-path:polygon(0_0,calc(100%-12px)_0,100%_50%,calc(100%-12px)_100%,0_100%)]", state === "current" ? "bg-primary text-primary-fg" : state === "past" ? "bg-primary-soft text-primary" : "bg-bg-subtle text-fg-muted hover:bg-surface-hover disabled:hover:bg-bg-subtle")}>{s.name}</button></li>;
      })}
    </ol>
  );
}

export function RecordPage({ entity }: { entity: Entity }) {
  const { id } = useParams<{ id: string }>(); const router = useRouter(); const qc = useQueryClient(); const toast = useToast(); const ui = useUI();
  const { can, has } = useAccess(); const { data: me } = useMe(); const pipelines = usePipelines(); const customDefs = useCustomFields(entity);
  const plural = PLURAL[entity]; const base = `/api/v1/${plural}`;
  const q = useQuery({ queryKey: ["record", entity, id], queryFn: () => api.get<Rec>(`${base}/${id}`), retry: (n, e) => (e as { status?: number }).status !== 404 && n < 1 });
  const [tab, setTab] = React.useState("overview"); const [convert, setConvert] = React.useState(false); const [del, setDel] = React.useState(false); const [edit, setEdit] = React.useState(false); const [lostOpen, setLostOpen] = React.useState(false);
  const [ai, setAi] = React.useState<string | null>(null); const [aiBusy, setAiBusy] = React.useState(false); const [aiSug, setAiSug] = React.useState<{ suggested: number; reasons: string[] } | null>(null);
  const rec = q.data;
  const canEdit = can(`${plural}.update`);

  const patch = useMutation({
    mutationFn: (p: Record<string, unknown>) => api.patch<Rec>(`${base}/${id}`, p),
    onMutate: async (p) => { await qc.cancelQueries({ queryKey: ["record", entity, id] }); const prev = qc.getQueryData(["record", entity, id]); qc.setQueryData<Rec>(["record", entity, id], (r) => (r ? { ...r, ...p } : r)); return { prev }; },
    onError: (e, _p, ctx) => { qc.setQueryData(["record", entity, id], ctx?.prev); toast.error("Couldn't save", (e as Error).message); },
    onSuccess: (r) => { qc.setQueryData(["record", entity, id], r); qc.invalidateQueries({ queryKey: [plural] }); qc.invalidateQueries({ queryKey: ["timeline"] }); qc.invalidateQueries({ queryKey: ["board"] }); },
  });
  const save = (p: Record<string, unknown>) => patch.mutateAsync(p);
  const move = async (stageId: string, extra?: Record<string, unknown>) => {
    try { const r = await api.post<Deal>(`/api/v1/deals/${id}/move`, { stage_id: stageId, ...extra }); qc.setQueryData(["record", entity, id], r); qc.invalidateQueries({ queryKey: ["timeline"] }); qc.invalidateQueries({ queryKey: ["deals"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); if (r.status === "won") { celebrate(); toast.success("Deal won 🎉", `${r.name} — ${formatMoney(r.value, r.currency)}`); } else toast.success(`Moved to ${r.stage.name}`); }
    catch (e) { toast.error("Couldn't move deal", (e as Error).message); }
  };
  const runAi = async () => { setAiBusy(true); try { const r = await api.post<{ summary: string }>("/api/v1/ai/summarize", { entity, id }); setAi(r.summary); qc.invalidateQueries({ queryKey: ["ai-usage"] }); } catch (e) { toast.error("Couldn't summarize", (e as Error).message); } finally { setAiBusy(false); } };
  React.useEffect(() => { if (entity === "deal" && has("ai_assistant")) api.get<{ suggested: number; reasons: string[] }>(`${base}/${id}/ai/probability`).then(setAiSug).catch(() => {}); }, [entity, id, base, has, (rec as Deal | undefined)?.stage_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (q.isLoading) return <PageContainer><Skeleton className="h-6 w-24" /><div className="mt-6 flex gap-4"><Skeleton className="size-14 rounded-full" /><div className="flex-1 space-y-2"><Skeleton className="h-8 w-72" /><Skeleton className="h-4 w-48" /></div></div><div className="mt-8 grid gap-6 lg:grid-cols-[1fr_380px]"><Skeleton className="h-96" /><Skeleton className="h-96" /></div></PageContainer>;
  if (q.isError || !rec) return <PageContainer><ErrorState kind={(q.error as { status?: number })?.status === 404 ? "generic" : "unavailable"} title={(q.error as { status?: number })?.status === 404 ? `This ${entity} doesn't exist` : undefined} description={(q.error as { status?: number })?.status === 404 ? "It may have been deleted, or you may not have access." : undefined} onRetry={() => q.refetch()} action={<Button variant="secondary" asChild><Link href={`/app/${plural}`}>Back to {plural}</Link></Button>} /></PageContainer>;

  const name: string = (rec as Contact).name ?? (rec as Lead).name ?? "";
  const scope: Scope = { entity, id, label: name };
  const composeDefaults: Record<string, unknown> = { to: (rec as Lead).email ?? (rec as Contact).email ?? "", [`${entity}_id`]: id };
  const e = entity === "lead" || entity === "contact" ? (rec as Lead | Contact).email : null;
  const nameSave = (v: string | null) => save(entity === "company" || entity === "deal" ? { name: v } : { first_name: (v ?? "").split(" ")[0], last_name: (v ?? "").split(" ").slice(1).join(" ") || null });
  const statuses = me?.workspace?.lead_statuses ?? [];
  const lead = rec as Lead; const deal = rec as Deal; const contact = rec as Contact; const company = rec as Company;
  const custom = rec.custom as Record<string, unknown>;

  const tabs: [string, string][] = [["overview", "Activity"], ["notes", "Notes"], ["tasks", "Tasks"], ["emails", "Emails"], ["calls", "Calls"], ["meetings", "Meetings"], ...(entity === "contact" || entity === "company" ? [["deals", "Deals"] as [string, string]] : []), ...(entity === "company" ? [["contacts", "Contacts"] as [string, string]] : []), ["files", "Files"]];

  return (
    <PageContainer wide>
      <Link href={`/app/${plural}`} className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-fg-muted hover:text-fg"><ArrowLeft className="size-3.5" /> {label(plural)}</Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <Avatar name={name} src={(rec as Contact).avatar_url} size={56} square={entity === "company" || entity === "deal"} />
          <div className="min-w-0">
            <h1 className="line-clamp-2 break-words text-2xl font-semibold tracking-tight sm:text-[28px]">{canEdit ? <InlineTitle value={name} onSave={nameSave} /> : name}</h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-fg-muted">
              {entity === "lead" && <><ColorChip color={statuses.find((s) => s.key === lead.status)?.color}>{statuses.find((s) => s.key === lead.status)?.label ?? label(lead.status)}</ColorChip><ScorePill score={lead.score} />{lead.company_name && <span>{lead.job_title ? `${lead.job_title} · ` : ""}{lead.company_name}</span>}</>}
              {entity === "contact" && <>{contact.job_title}{contact.company && <> · <Link className="hover:text-primary" href={`/app/companies/${contact.company.id}`}>{contact.company.name}</Link></>}</>}
              {entity === "company" && <>{[company.industry, company.location].filter(Boolean).join(" · ")}{company.website && <a href={company.website} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-primary"><Link2 className="size-3.5" />{company.website.replace(/^https?:\/\//, "")}</a>}</>}
              {entity === "deal" && <><span className="tabular text-lg font-semibold text-fg">{formatMoney(deal.value, deal.currency)}</span><Badge tone={deal.status === "won" ? "success" : deal.status === "lost" ? "danger" : "primary"} dot>{label(deal.status)}</Badge>{deal.company && <Link className="hover:text-primary" href={`/app/companies/${deal.company.id}`}>{deal.company.name}</Link>}</>}
              {(rec.tags as string[])?.slice(0, 4).map((t) => <Badge key={t} tone="outline">{t}</Badge>)}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {entity === "lead" && lead.status !== "converted" && can("leads.convert") && <Button onClick={() => setConvert(true)}><UserCheck /> Convert lead</Button>}
          {entity === "lead" && lead.converted_contact_id && <Button variant="secondary" asChild><Link href={`/app/contacts/${lead.converted_contact_id}`}>View contact <ChevronRight /></Link></Button>}
          {entity === "deal" && deal.status === "open" && can("deals.close") && <><Button variant="soft" onClick={() => { const w = pipelines.data?.find((p) => p.id === deal.pipeline_id)?.stages.find((s) => s.kind === "won"); w && move(w.id); }}><Trophy /> Won</Button><Button variant="secondary" onClick={() => setLostOpen(true)}><XCircle /> Lost</Button></>}
          {entity === "deal" && deal.status !== "open" && canEdit && <Button variant="secondary" onClick={() => { const s = pipelines.data?.find((p) => p.id === deal.pipeline_id)?.stages.find((x) => x.kind === "open"); s && move(s.id); }}>Reopen</Button>}
          {e && can("emails.create") && <Button variant="secondary" onClick={() => ui.openCompose(composeDefaults)}><Mail /> Email</Button>}
          {can("meetings.create") && <Button variant="secondary" onClick={() => ui.openCreate("call", { [`${entity}_id`]: id })}><Phone /> <span className="hidden sm:inline">Call</span></Button>}
          <DropdownMenu><DropdownTrigger asChild><Button variant="secondary" size="icon" aria-label="More actions"><MoreHorizontal /></Button></DropdownTrigger>
            <DropdownContent>
              {can("meetings.create") && <DropdownItem icon={<Calendar />} onSelect={() => ui.openCreate("meeting", { [`${entity}_id`]: id })}>Schedule meeting</DropdownItem>}
              {can("tasks.create") && <DropdownItem icon={<CheckSquare />} onSelect={() => ui.openCreate("task", { [`${entity}_id`]: id })}>Create task</DropdownItem>}
              {can("notes.create") && <DropdownItem icon={<StickyNote />} onSelect={() => setTab("notes")}>Add note</DropdownItem>}
              {canEdit && <DropdownItem icon={<Pencil />} onSelect={() => setEdit(true)}>Edit all fields</DropdownItem>}
              <DropdownItem icon={<Copy />} onSelect={() => { navigator.clipboard?.writeText(window.location.href); toast.success("Link copied"); }}>Copy link</DropdownItem>
              {can(`${plural}.delete`) && <><DropdownSeparator /><DropdownItem danger icon={<Trash2 />} onSelect={() => setDel(true)}>Delete {entity}</DropdownItem></>}
            </DropdownContent></DropdownMenu>
        </div>
      </div>
      {entity === "deal" && <div className="mb-6"><StageStepper deal={deal} onMove={(s) => move(s)} /></div>}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 order-2 lg:order-1">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>{tabs.map(([k, l]) => <TabsTrigger key={k} value={k}>{l}</TabsTrigger>)}</TabsList>
            <div className="pt-6">
              <TabsContent value="overview"><Timeline entity={entity} id={id} /></TabsContent>
              <TabsContent value="notes"><NotesTab scope={scope} /></TabsContent>
              <TabsContent value="tasks"><TasksTab scope={scope} /></TabsContent>
              <TabsContent value="emails"><EmailsTab scope={scope} defaults={composeDefaults} /></TabsContent>
              <TabsContent value="calls"><CallsTab scope={scope} /></TabsContent>
              <TabsContent value="meetings"><MeetingsTab scope={scope} /></TabsContent>
              {(entity === "contact" || entity === "company") && <TabsContent value="deals"><DealsTab scope={scope} /></TabsContent>}
              {entity === "company" && <TabsContent value="contacts"><ContactsTab companyId={id} companyName={name} /></TabsContent>}
              <TabsContent value="files"><FilesTab scope={scope} /></TabsContent>
            </div>
          </Tabs>
        </div>

        <aside className="order-1 space-y-4 lg:sticky lg:top-20 lg:order-2">
          {has("ai_assistant") && can("ai.use") && (
            <Card className="overflow-hidden border-primary/20 bg-gradient-to-br from-primary-soft/60 to-surface">
              <div className="p-4">
                <div className="flex items-center justify-between"><p className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-primary" /> AI summary</p>{!ai && <Button size="xs" variant="soft" onClick={runAi} loading={aiBusy}>Summarize</Button>}</div>
                {ai ? <div className="mt-3 animate-fade-in"><Markdown>{ai}</Markdown><Button size="xs" variant="ghost" className="mt-2" onClick={runAi} loading={aiBusy}>Refresh</Button></div> : <p className="mt-1.5 text-[13px] text-fg-muted">Get the story so far and a suggested next step.</p>}
                {entity === "deal" && aiSug && <div className="mt-3 rounded-lg bg-surface/80 p-3 text-[13px]"><p className="font-medium">AI probability: <span className="tabular text-primary">{aiSug.suggested}%</span>{aiSug.suggested !== deal.probability && <button onClick={() => save({ probability: aiSug.suggested })} className="ml-2 text-xs font-medium text-primary hover:underline">Apply</button>}</p><ul className="mt-1 list-disc pl-4 text-xs text-fg-muted">{aiSug.reasons.map((r) => <li key={r}>{r}</li>)}</ul></div>}
                {entity === "lead" && lead.score_reasons?.length > 0 && <details className="mt-3 text-[13px]"><summary className="cursor-pointer font-medium text-fg-muted">Why score {lead.score}?</summary><ul className="mt-2 space-y-1">{lead.score_reasons.map((r) => <li key={r.label} className="flex justify-between"><span className="text-fg-muted">{r.label}</span><span className={cn("tabular font-medium", r.points < 0 ? "text-danger" : "text-success")}>{r.points > 0 ? "+" : ""}{r.points}</span></li>)}</ul></details>}
              </div>
            </Card>
          )}
          <Section title="Details" actions={canEdit && <Button variant="ghost" size="xs" onClick={() => setEdit(true)}><Pencil /> Edit all</Button>}>
            {entity === "lead" && <>
              <InlineField label="Email" type="email" value={lead.email} onSave={(v) => save({ email: v })} editable={canEdit} />
              <InlineField label="Phone" type="tel" value={lead.phone} onSave={(v) => save({ phone: v })} editable={canEdit} />
              <InlineField label="Company" value={lead.company_name} onSave={(v) => save({ company_name: v })} editable={canEdit} />
              <InlineField label="Job title" value={lead.job_title} onSave={(v) => save({ job_title: v })} editable={canEdit} />
              <InlineField label="Status" value={lead.status} display={<ColorChip color={statuses.find((s) => s.key === lead.status)?.color}>{statuses.find((s) => s.key === lead.status)?.label ?? lead.status}</ColorChip>} options={statuses.filter((s) => s.key !== "converted").map((s) => [s.key, s.label])} onSave={(v) => v && save({ status: v })} editable={canEdit && lead.status !== "converted"} />
              <InlineField label="Source" value={lead.source} display={lead.source && label(lead.source)} options={SOURCES.map((s) => [s, label(s)])} onSave={(v) => save({ source: v })} editable={canEdit} />
              <InlineField label="Follow-up" type="datetime-local" value={toLocalInput(lead.next_follow_up_at)} display={lead.next_follow_up_at && formatDate(lead.next_follow_up_at, "datetime")} onSave={(v) => save({ next_follow_up_at: fromLocalInput(v ?? "") })} editable={canEdit} placeholder="Schedule…" />
              <InlineField label="Location" value={lead.location} onSave={(v) => save({ location: v })} editable={canEdit} />
              <Row label="Last contacted">{lead.last_contacted_at ? timeAgo(lead.last_contacted_at) : "Never"}</Row>
            </>}
            {entity === "contact" && <>
              <InlineField label="Email" type="email" value={contact.email} onSave={(v) => save({ email: v })} editable={canEdit} />
              <InlineField label="Phone" type="tel" value={contact.phone} onSave={(v) => save({ phone: v })} editable={canEdit} />
              <InlineField label="Job title" value={contact.job_title} onSave={(v) => save({ job_title: v })} editable={canEdit} />
              <Row label="Company"><AsyncSelect endpoint="/api/v1/companies" value={contact.company_id} initialLabel={contact.company?.name} onChange={(c) => save({ company_id: c })} /></Row>
              <InlineField label="Location" value={contact.location} onSave={(v) => save({ location: v })} editable={canEdit} />
              <InlineField label="LinkedIn" value={contact.socials?.linkedin} onSave={(v) => save({ socials: { ...contact.socials, linkedin: v ?? "" } })} editable={canEdit} placeholder="Add profile URL" />
              <Row label="Last contacted">{contact.last_contacted_at ? timeAgo(contact.last_contacted_at) : "Never"}</Row>
            </>}
            {entity === "company" && <>
              <InlineField label="Website" type="url" value={company.website} onSave={(v) => save({ website: v })} editable={canEdit} />
              <InlineField label="Industry" value={company.industry} onSave={(v) => save({ industry: v })} editable={canEdit} />
              <InlineField label="Size" value={company.size} onSave={(v) => save({ size: v })} editable={canEdit} />
              <InlineField label="Location" value={company.location} onSave={(v) => save({ location: v })} editable={canEdit} />
              <InlineField label="Revenue" type="number" value={company.annual_revenue} display={company.annual_revenue ? formatMoney(company.annual_revenue) : undefined} onSave={(v) => save({ annual_revenue: v === null ? null : Number(v) })} editable={canEdit} mono />
              <InlineField label="Phone" type="tel" value={company.phone} onSave={(v) => save({ phone: v })} editable={canEdit} />
              <Row label="Contacts">{company.contacts_count}</Row><Row label="Open deals">{company.open_deals_count} · {formatMoney(company.open_deals_value)}</Row>
            </>}
            {entity === "deal" && <>
              <InlineField label="Value" type="number" value={deal.value} display={formatMoney(deal.value, deal.currency)} onSave={(v) => save({ value: Number(v ?? 0) })} editable={canEdit} mono />
              <InlineField label="Probability" type="number" value={deal.probability} display={`${deal.probability}%`} onSave={(v) => save({ probability: Number(v ?? 0) })} editable={canEdit && deal.status === "open"} mono />
              <Row label="Weighted">{formatMoney(deal.weighted_value, deal.currency)}</Row>
              <InlineField label="Expected close" type="date" value={deal.expected_close_date} display={deal.expected_close_date && formatDate(deal.expected_close_date + "T00:00:00", "long")} onSave={(v) => save({ expected_close_date: v })} editable={canEdit} placeholder="Set date…" />
              <InlineField label="Priority" value={deal.priority} display={label(deal.priority)} options={PRIORITIES.map(([k, l]) => [k, l])} onSave={(v) => v && save({ priority: v })} editable={canEdit} />
              <Row label="Company">{deal.company ? <Link className="text-primary hover:underline" href={`/app/companies/${deal.company.id}`}>{deal.company.name}</Link> : "—"}</Row>
              <Row label="Contact">{deal.contact ? <Link className="text-primary hover:underline" href={`/app/contacts/${deal.contact.id}`}>{deal.contact.name}</Link> : "—"}</Row>
              <InlineField label="Source" value={deal.source} display={deal.source && label(deal.source)} options={SOURCES.map((s) => [s, label(s)])} onSave={(v) => save({ source: v })} editable={canEdit} />
              <Row label="In stage">{deal.days_in_stage != null ? `${deal.days_in_stage} day${deal.days_in_stage === 1 ? "" : "s"}` : "—"}</Row>
              {deal.status === "lost" && deal.lost_reason && <Row label="Lost reason">{deal.lost_reason}</Row>}
            </>}
            <Row label="Owner"><MemberSelect size="sm" value={rec.owner_id} onChange={(v) => save({ owner_id: v })} /></Row>
            <div className="grid grid-cols-[110px_1fr] items-start gap-3 py-2 text-sm"><dt className="pt-1.5 text-[13px] text-fg-muted">Tags</dt><dd><TagInput value={rec.tags ?? []} onChange={(t) => save({ tags: t })} /></dd></div>
            {entity !== "deal" || true ? <InlineField label="Notes" multiline value={rec.description} onSave={(v) => save({ description: v })} editable={canEdit} placeholder="Add a description…" /> : null}
          </Section>
          {(customDefs.data?.length ?? 0) > 0 && has("custom_fields") && (
            <Section title="Custom fields">{customDefs.data!.map((d) => <CustomRow key={d.id} def={d} value={custom?.[d.key]} canEdit={canEdit} onSave={(v) => save({ custom: { [d.key]: v } })} />)}</Section>
          )}
          <Card className="px-5 py-3 text-xs text-fg-subtle"><p>Created {formatDate(rec.created_at, "datetime")}{rec.last_activity_at && <> · Last activity {timeAgo(rec.last_activity_at)}</>}</p></Card>
        </aside>
      </div>

      {entity === "lead" && <ConvertDialog lead={lead} open={convert} onOpenChange={setConvert} />}
      <ConfirmDialog open={del} onOpenChange={setDel} title={`Delete ${name}?`} description={<>This {entity} and its place in reports will be removed. It's recorded in the audit log.</>} confirmLabel={`Delete ${entity}`} onConfirm={async () => { await api.delete(`${base}/${id}`); qc.invalidateQueries({ queryKey: [plural] }); toast.success(`${label(entity)} deleted`); router.replace(`/app/${plural}`); }} />
      <ConfirmDialog open={lostOpen} onOpenChange={setLostOpen} title="Mark deal as lost?" description="Tell your team why — it makes win/loss reports far more useful." confirmLabel="Mark as lost" requireReason onConfirm={async ({ reason }) => { const l = pipelines.data?.find((p) => p.id === deal.pipeline_id)?.stages.find((s) => s.kind === "lost"); if (l) await move(l.id, { lost_reason: reason }); }} />
      <Drawer open={edit} onOpenChange={setEdit} title={`Edit ${entity}`} footer={<><Button variant="secondary" onClick={() => setEdit(false)}>Cancel</Button><Button type="submit" form={`form-${entity}`}>Save changes</Button></>}>
        <RecordForm kind={entity} initial={rec} hideActions onSaved={(r) => { qc.setQueryData(["record", entity, id], r); setEdit(false); }} />
      </Drawer>
    </PageContainer>
  );
}

function InlineTitle({ value, onSave }: { value: string; onSave: (v: string | null) => Promise<unknown> }) {
  const [edit, setEdit] = React.useState(false); const [v, setV] = React.useState(value);
  React.useEffect(() => setV(value), [value]);
  if (!edit) return <button onClick={() => setEdit(true)} className="-mx-2 max-w-full rounded-lg px-2 text-left transition-colors hover:bg-bg-subtle" aria-label="Edit name">{value}</button>;
  return <Input autoFocus value={v} onChange={(e) => setV(e.target.value)} onBlur={async () => { setEdit(false); if (v.trim() && v !== value) await onSave(v.trim()).catch(() => setV(value)); else setV(value); }} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") { setV(value); setEdit(false); } }} className="h-11 text-2xl font-semibold" />;
}
const Row = ({ label, children }: { label: string; children: React.ReactNode }) => <div className="grid grid-cols-[110px_1fr] items-center gap-3 py-2 text-sm"><dt className="text-[13px] text-fg-muted">{label}</dt><dd className="min-w-0">{children}</dd></div>;

function CustomRow({ def, value, canEdit, onSave }: { def: { label: string; field_type: string; options: string[]; key: string }; value: unknown; canEdit: boolean; onSave: (v: unknown) => Promise<unknown> }) {
  const t = def.field_type;
  if (t === "checkbox") return <Row label={def.label}><Switch checked={!!value} onCheckedChange={(c) => onSave(c)} disabled={!canEdit} aria-label={def.label} /></Row>;
  if (t === "multi_select") { const cur = (value as string[]) ?? []; return <Row label={def.label}><div className="flex flex-wrap gap-1.5">{def.options.map((o) => <button key={o} disabled={!canEdit} onClick={() => onSave(cur.includes(o) ? cur.filter((x) => x !== o) : [...cur, o])} className={cn("rounded-full border px-2.5 py-0.5 text-xs", cur.includes(o) ? "border-primary bg-primary-soft text-primary" : "border-border text-fg-subtle")}>{o}</button>)}</div></Row>; }
  const type = { number: "number", currency: "number", date: "date", url: "url", email: "email", phone: "tel" }[t] ?? "text";
  return <InlineField label={def.label} type={type} value={value as string} options={t === "dropdown" ? def.options.map((o) => [o, o]) : undefined} onSave={(v) => onSave(v === null ? null : type === "number" ? Number(v) : v)} editable={canEdit} />;
}
export { Building2, Handshake, FORMS };
