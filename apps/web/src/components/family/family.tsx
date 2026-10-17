"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Check, Clock, Copy, Eye, FileCheck2, Globe2, Languages, Link2, Lock, MessageCircle, Moon, MoreHorizontal, Pencil, Plus, Send, Trash2, Users, Video, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { ApiError, Badge, Button, Card, Checkbox, ConfirmDialog, Dialog, DialogContent, DialogFooter, DropdownContent, DropdownItem, DropdownMenu, DropdownSeparator, DropdownTrigger, EmptyState, ErrorState, Field, Input, NativeSelect, Skeleton, SkeletonRows, Switch, Textarea, cn, formatDate, timeAgo, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { TemplateComposer, WA_GREEN, type WaMessage, useWaTemplates } from "../whatsapp/whatsapp";
import { SettingsSection } from "../settings/ui";

export type RecordRef = { entity: "lead" | "contact" | "deal"; id: string };
type Price = { label: string; inr: number; inr_text: string; currency: string; amount: number | null; amount_text: string | null; rate: number | null };
type CheckItem = { key: string; label: string; hint: string; done: boolean; done_at?: string | null };
export type Walk = { id: string; member_id: string; starts_at: string; timezone: string; status: "requested" | "confirmed" | "cancelled"; note: string | null; requested_via: "link" | "rep"; meeting_url: string | null; local_label: string };
export type FamilyMember = {
  id: string; name: string; relation: string; relation_label: string; role: string; role_label: string; phone: string | null; phone_masked?: boolean; email: string | null;
  language: string; language_label: string; timezone: string; place: string; city: string | null; is_nri: boolean; currency: string; notes: string | null;
  local_time: string; quiet: boolean; next_morning: string; prices: Price[]; checklist: CheckItem[]; checklist_done: number; link: string | null; walkthroughs: Walk[]; scheduled_messages: number;
};
type Options = { relations: Record<string, string>; roles: Record<string, string>; languages: Record<string, { name: string; native: string }>; currencies: Record<string, string>; timezones: string[]; checklist: { key: string; label: string; hint: string }[] };
type Fx = { rates: Record<string, number>; updated_at: string | null; updated_by: string | null };
type FamilyData = { members: FamilyMember[]; fx: Fx; options: Options; can_edit: boolean; can_message: boolean; can_view_phones: boolean; can_reveal: boolean; is_owner: boolean };
type Queued = { id: string; status: "scheduled" | "failed"; body: string; send_at: string; local_label: string; error: string | null };
type Conversation = { connected: boolean; has_phone: boolean; window_open: boolean; messages: WaMessage[]; queued: Queued[] };

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
const place = (tz: string) => tz.split("/").pop()!.replace(/_/g, " ");
/** "7:42 pm" right now in their zone, ticking. */
function useClock(tz: string) {
  const [now, setNow] = React.useState(() => new Date());
  React.useEffect(() => { const t = setInterval(() => setNow(new Date()), 30_000); return () => clearInterval(t); }, []);
  const time = now.toLocaleTimeString("en-IN", { timeZone: tz, hour: "numeric", minute: "2-digit" }).toLowerCase();
  const hour = Number(now.toLocaleString("en-GB", { timeZone: tz, hour: "2-digit", hourCycle: "h23" }));
  return { time, quiet: hour >= 21 || hour < 9 };
}
const copy = async (text: string, toast: ReturnType<typeof useToast>, what = "Copied") => { try { await navigator.clipboard.writeText(text); toast.success(what); } catch { toast.error("Couldn't copy", "Select the text and copy it yourself."); } };

export function useFamily(record: RecordRef) {
  return useQuery({ queryKey: ["family", record.entity, record.id], queryFn: () => api.get<FamilyData>("/api/v1/family", { record: `${record.entity}:${record.id}` }) });
}

/** The Family tab on a lead, client or deal: who decides, pays and advises, in their own language, time zone and currency. */
export function FamilyTab({ record }: { record: RecordRef }) {
  const q = useFamily(record); const [edit, setEdit] = React.useState<FamilyMember | "new" | null>(null);
  if (q.isLoading) return <SkeletonRows rows={3} />;
  if (q.isError) return <ErrorState compact title="Couldn't load the family" description={(q.error as ApiError)?.status === 404 ? "The server doesn't have family mode yet. Restart the API and run database migrations, then try again." : errText(q.error)} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const needsRate = d.members.some((m) => m.currency !== "INR" && !d.fx.rates[m.currency]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-fg-muted">In India the family buys the house. Add the people who decide, pay or advise, and message each one in their own language and time zone.</p>
        {d.can_edit && <Button size="sm" onClick={() => setEdit("new")}><Plus /> Add family member</Button>}
      </div>
      {needsRate && <p className="rounded-lg border border-warning/30 bg-warning-soft px-3 py-2 text-[13px] text-warning">Prices in AED or USD show once the workspace owner sets the exchange rate in <Link href="/app/settings/workspace" className="font-medium underline">Settings → Workspace</Link>.</p>}
      {!d.members.length ? <EmptyState compact icon={<Users />} title="No family members yet" description="Add the spouse, parents, or a son working abroad. NRI members get prices in AED or USD, a document checklist and their own page to book a video walkthrough." action={d.can_edit ? <Button variant="secondary" size="sm" onClick={() => setEdit("new")}><Plus /> Add family member</Button> : undefined} />
        : <div className="grid items-start gap-3 xl:grid-cols-2">{d.members.map((m) => <MemberCard key={m.id} m={m} data={d} record={record} onEdit={() => setEdit(m)} />)}</div>}
      <MemberDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} member={edit === "new" ? null : edit} record={record} options={d.options} />
    </div>
  );
}

function MemberCard({ m, data, record, onEdit }: { m: FamilyMember; data: FamilyData; record: RecordRef; onEdit: () => void }) {
  const qc = useQueryClient(); const toast = useToast(); const { can } = useAccess(); const clock = useClock(m.timezone);
  const [msg, setMsg] = React.useState(false); const [del, setDel] = React.useState(false); const [shown, setShown] = React.useState<string | null>(null);
  const [walk, setWalk] = React.useState<Walk | "new" | null>(null); const [docs, setDocs] = React.useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["family", record.entity, record.id] }); qc.invalidateQueries({ queryKey: ["timeline"] }); };
  const reveal = async () => { try { setShown((await api.post<{ phone: string }>(`/api/v1/family/${m.id}/reveal-phone`)).phone); } catch (e) { toast.error("Couldn't show the number", errText(e)); } };
  const link = async () => { try { const r = await api.post<{ link: string }>(`/api/v1/family/${m.id}/link`); refresh(); await copy(r.link, toast, "Link copied. Send it to them on WhatsApp."); } catch (e) { toast.error("Couldn't make the link", errText(e)); } };
  const tick = async (item: string, done: boolean) => { try { await api.put(`/api/v1/family/${m.id}/checklist`, { item, done }); refresh(); } catch (e) { toast.error("Couldn't save", errText(e)); } };
  const requested = m.walkthroughs.filter((w) => w.status === "requested"); const confirmed = m.walkthroughs.filter((w) => w.status === "confirmed" && new Date(w.starts_at).getTime() > Date.now() - 2 * 3600_000);
  const phone = shown ?? m.phone;
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5 font-medium">{m.name}<Badge tone="neutral">{m.relation_label}</Badge><Badge tone={m.role === "pays" ? "success" : m.role === "decides" ? "primary" : "outline"}>{m.role_label}</Badge>{m.is_nri && <Badge tone="info"><Globe2 className="size-3" /> NRI</Badge>}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-fg-muted">
            <span className="inline-flex items-center gap-1" title={m.timezone}>{clock.quiet ? <Moon className="size-3.5 text-info" /> : <Clock className="size-3.5" />}{clock.time} in {m.city || m.place}</span>
            <span className="inline-flex items-center gap-1"><Languages className="size-3.5" />{m.language_label}</span>
            {phone && (m.phone_masked && !shown ? <span className="inline-flex items-center gap-1 tabular" title="Hidden by your workspace owner"><Lock className="size-3" />{phone}{data.can_reveal && <Button size="xs" variant="ghost" onClick={reveal} title="Your workspace owner can see who viewed each number"><Eye /> Show</Button>}</span> : <a href={`tel:${phone}`} className="tabular hover:text-primary">{phone}</a>)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {data.can_message && m.phone && <Button size="sm" variant="secondary" onClick={() => setMsg(true)}><MessageCircle style={{ color: WA_GREEN }} /> Message</Button>}
          <DropdownMenu><DropdownTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={`More for ${m.name}`}><MoreHorizontal /></Button></DropdownTrigger>
            <DropdownContent>
              {data.can_edit && <DropdownItem icon={<Link2 />} onSelect={link}>{m.link ? "Copy their page link" : "Make their page link"}</DropdownItem>}
              {can("meetings.create") && <DropdownItem icon={<Video />} onSelect={() => setWalk("new")}>Book a video walkthrough</DropdownItem>}
              {data.can_edit && <DropdownItem icon={<Pencil />} onSelect={onEdit}>Edit</DropdownItem>}
              {data.can_edit && <><DropdownSeparator /><DropdownItem danger icon={<Trash2 />} onSelect={() => setDel(true)}>Remove from family</DropdownItem></>}
            </DropdownContent></DropdownMenu>
        </div>
      </div>

      {m.prices.length > 0 && <div className="mt-3 space-y-1 rounded-lg bg-bg-subtle px-3 py-2 text-[13px]">{m.prices.map((p) => (
        <div key={p.label} className="flex flex-wrap items-baseline justify-between gap-x-3"><span className="truncate text-fg-muted">{p.label}</span><span className="tabular font-medium">{p.inr_text}{p.amount_text && <span className="ml-2 text-primary">≈ {p.amount_text}</span>}</span></div>))}
        {m.currency !== "INR" && <p className="text-[11px] text-fg-subtle">{m.prices[0].rate ? `At ₹${m.prices[0].rate} per ${m.currency}, set by the owner` : `No ${m.currency} rate set yet`}</p>}
      </div>}

      {(requested.length > 0 || confirmed.length > 0) && <ul className="mt-3 space-y-1.5">{[...requested, ...confirmed].map((w) => (
        <li key={w.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2 text-[13px]">
          <Video className="size-4 shrink-0 text-primary" /><span className="min-w-0 flex-1"><span className="font-medium">{w.status === "requested" ? "Walkthrough requested" : "Walkthrough"}</span> · {w.local_label}{w.note && <span className="block text-xs text-fg-muted">“{w.note}”</span>}</span>
          {w.status === "requested" ? can("meetings.create") && <Button size="xs" onClick={() => setWalk(w)}><Check /> Confirm</Button> : w.meeting_url && <a href={w.meeting_url} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary hover:underline">Join link</a>}
        </li>))}</ul>}

      {m.is_nri && <div className="mt-3">
        <button type="button" onClick={() => setDocs(!docs)} className="flex w-full items-center gap-2 text-[13px] font-medium text-fg-muted hover:text-fg" aria-expanded={docs}><FileCheck2 className="size-4" />NRI documents<span className="ml-auto tabular text-xs">{m.checklist_done} of {m.checklist.length}</span></button>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-bg-subtle"><div className="h-full rounded-full bg-success transition-all" style={{ width: `${(m.checklist_done / Math.max(m.checklist.length, 1)) * 100}%` }} /></div>
        {docs && <ul className="mt-2 space-y-1.5">{m.checklist.map((i) => (
          <li key={i.key} className="flex items-start gap-2.5 text-[13px]"><Checkbox checked={i.done} disabled={!data.can_edit} onCheckedChange={(v) => tick(i.key, !!v)} aria-label={i.label} className="mt-0.5" /><span><span className={cn("font-medium", i.done && "text-fg-muted line-through")}>{i.label}</span><span className="block text-xs text-fg-muted">{i.hint}</span></span></li>))}</ul>}
      </div>}
      {m.notes && <p className="mt-3 whitespace-pre-line text-[13px] text-fg-muted">{m.notes}</p>}
      {m.scheduled_messages > 0 && <p className="mt-2 text-xs text-fg-muted"><CalendarClock className="mr-1 inline size-3.5 align-[-2px]" />{m.scheduled_messages} message{m.scheduled_messages > 1 ? "s" : ""} waiting for morning in {m.place}</p>}

      {msg && <MessageDialog m={m} onOpenChange={setMsg} onSent={refresh} />}
      {walk && <WalkthroughDialog m={m} walk={walk === "new" ? null : walk} onOpenChange={(o) => !o && setWalk(null)} onDone={refresh} />}
      <ConfirmDialog open={del} onOpenChange={setDel} title={`Remove ${m.name}?`} description="Their page link stops working and messages waiting for morning are cancelled. Messages already sent stay on the timeline." confirmLabel="Remove"
        onConfirm={async () => { await api.delete(`/api/v1/family/${m.id}`); refresh(); toast.success(`${m.name} removed`); }} />
    </Card>
  );
}

function MemberDialog({ open, onOpenChange, member, record, options }: { open: boolean; onOpenChange: (o: boolean) => void; member: FamilyMember | null; record: RecordRef; options: Options }) {
  const qc = useQueryClient(); const toast = useToast();
  const blank = { name: "", relation: "spouse", role: "decides", phone: "", email: "", language: "hi", timezone: "Asia/Kolkata", city: "", is_nri: false, currency: "INR", notes: "" };
  const [f, setF] = React.useState(blank); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  React.useEffect(() => { if (open) { setErr(null); setF(member ? { name: member.name, relation: member.relation, role: member.role, phone: member.phone ?? "", email: member.email ?? "", language: member.language, timezone: member.timezone, city: member.city ?? "", is_nri: member.is_nri, currency: member.currency, notes: member.notes ?? "" } : blank); } }, [open, member?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (p: Partial<typeof f>) => setF((x) => ({ ...x, ...p }));
  // Abroad usually means NRI and their local currency; the rep can still change both.
  const setZone = (tz: string) => set({ timezone: tz, ...(member ? {} : tz === "Asia/Kolkata" ? { is_nri: false, currency: "INR" } : { is_nri: true, currency: tz === "Asia/Dubai" ? "AED" : f.currency === "INR" ? "USD" : f.currency }) });
  const zones = options.timezones.includes(f.timezone) ? options.timezones : [f.timezone, ...options.timezones];
  const save = async () => {
    setBusy(true); setErr(null);
    const body = { ...f, phone: f.phone || null, email: f.email || null, city: f.city || null, notes: f.notes || null };
    try {
      if (member) await api.patch(`/api/v1/family/${member.id}`, body); else await api.post("/api/v1/family", { ...body, record: `${record.entity}:${record.id}` });
      qc.invalidateQueries({ queryKey: ["family", record.entity, record.id] }); qc.invalidateQueries({ queryKey: ["timeline"] }); toast.success(member ? "Saved" : `${f.name} added to the family`); onOpenChange(false);
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={member ? `Edit ${member.name}` : "Add family member"} description="Someone who decides, pays or advises on this home.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name" required className="sm:col-span-2"><Input autoFocus value={f.name} onChange={(e) => set({ name: e.target.value })} placeholder="Rohan Gupta" /></Field>
          <Field label="Relation"><NativeSelect value={f.relation} onChange={(e) => set({ relation: e.target.value })}>{Object.entries(options.relations).map(([k, l]) => <option key={k} value={k}>{k === "other" ? "Other" : l}</option>)}</NativeSelect></Field>
          <Field label="Role in the decision"><NativeSelect value={f.role} onChange={(e) => set({ role: e.target.value })}>{Object.entries(options.roles).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect></Field>
          <Field label="Mobile (WhatsApp)" hint={member?.phone_masked ? "Hidden. Leave it as it is to keep the saved number." : "With country code, like +971 50 123 4567"}><Input type="tel" value={f.phone} onChange={(e) => set({ phone: e.target.value })} disabled={!!member?.phone_masked} /></Field>
          <Field label="Email"><Input type="email" value={f.email} onChange={(e) => set({ email: e.target.value })} /></Field>
          <Field label="Messages in"><NativeSelect value={f.language} onChange={(e) => set({ language: e.target.value })}>{Object.entries(options.languages).map(([k, l]) => <option key={k} value={k}>{l.name}{l.native !== l.name ? ` · ${l.native}` : ""}</option>)}</NativeSelect></Field>
          <Field label="Lives in (time zone)"><NativeSelect value={f.timezone} onChange={(e) => setZone(e.target.value)}>{zones.map((z) => <option key={z} value={z}>{place(z)}{z === "Asia/Kolkata" ? " (India)" : ""}</option>)}</NativeSelect></Field>
          <Field label="City" hint="Optional, shown next to their local time"><Input value={f.city} onChange={(e) => set({ city: e.target.value })} placeholder={place(f.timezone)} /></Field>
          <Field label="Prices in"><NativeSelect value={f.currency} onChange={(e) => set({ currency: e.target.value })}>{Object.entries(options.currencies).map(([k, l]) => <option key={k} value={k}>{k} · {l}</option>)}</NativeSelect></Field>
          <label className="flex items-center justify-between gap-4 rounded-lg border border-border p-3 text-sm sm:col-span-2"><span><span className="block font-medium">NRI (lives outside India)</span><span className="text-xs text-fg-muted">Adds the POA and NRE-account document checklist</span></span><Switch checked={f.is_nri} onCheckedChange={(v) => set({ is_nri: v })} aria-label="NRI" /></label>
          <Field label="Notes" className="sm:col-span-2"><Textarea rows={2} value={f.notes} onChange={(e) => set({ notes: e.target.value })} placeholder="Has the final say on the budget. Prefers calls after 8 pm Dubai time." /></Field>
        </div>
        {err && <p role="alert" className="mt-3 text-sm text-danger">{err}</p>}
        <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={busy} disabled={!f.name.trim()} onClick={save}>{member ? "Save" : "Add"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** WhatsApp to one family member: drafts, translation into their language, and "send at 9 am their time". */
function MessageDialog({ m, onOpenChange, onSent }: { m: FamilyMember; onOpenChange: (o: boolean) => void; onSent: () => void }) {
  const toast = useToast(); const clock = useClock(m.timezone);
  const conv = useQuery({ queryKey: ["family-conv", m.id], refetchInterval: 20_000, queryFn: () => api.get<Conversation>(`/api/v1/family/${m.id}/messages`) });
  const c = conv.data; const templates = useWaTemplates(!!c?.connected);
  const [text, setText] = React.useState(""); const [tr, setTr] = React.useState<{ text: string; ai: boolean; note?: string } | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null); const [when, setWhen] = React.useState<"now" | "morning">(m.quiet ? "morning" : "now");
  const end = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [c?.messages.length]);
  const english = m.language === "en";
  const draft = async (kind: string) => { setBusy(kind); try { setText((await api.post<{ text: string }>(`/api/v1/family/${m.id}/draft`, { kind })).text); setTr(null); if (kind === "link") onSent(); } catch (e) { toast.error("Couldn't draft", errText(e)); } finally { setBusy(null); } };
  const translate = async () => { setBusy("translate"); try { setTr(await api.post(`/api/v1/family/${m.id}/translate`, { text })); } catch (e) { toast.error("Couldn't translate", errText(e)); } finally { setBusy(null); } };
  const send = async (body: Record<string, unknown>) => {
    setBusy("send");
    try {
      const r = await api.post<{ status: string; local_label: string }>(`/api/v1/family/${m.id}/messages`, { ...body, when });
      toast.success(r.status === "sent" ? `Sent to ${m.name}` : `Will go out ${r.local_label}`); setText(""); setTr(null); conv.refetch(); onSent();
    } catch (e) { toast.error("Couldn't send", errText(e)); } finally { setBusy(null); }
  };
  const cancel = async (id: string) => { try { await api.delete(`/api/v1/family/messages/${id}`); conv.refetch(); onSent(); } catch (e) { toast.error("Couldn't cancel", errText(e)); } };
  const outgoing = tr ? tr.text : text;
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent size="lg" title={`Message ${m.name}`} description={`${m.relation_label} · writes in ${m.language_label} · ${clock.time} in ${m.city || m.place}${clock.quiet ? " (night there)" : ""}`}>
        {conv.isLoading ? <Skeleton className="h-48" /> : conv.isError ? <ErrorState compact title="Couldn't load messages" description={errText(conv.error)} onRetry={() => conv.refetch()} /> : !c!.connected ? (
          <EmptyState compact icon={<MessageCircle />} title="WhatsApp isn't connected" description="Connect your WhatsApp Business number in Integrations to message the family from here." />
        ) : (
          <div className="space-y-3">
            <div className="max-h-64 space-y-2 overflow-y-auto rounded-xl border border-border bg-bg-subtle p-3">
              {!c!.messages.length && !c!.queued.length ? <p className="py-4 text-center text-sm text-fg-muted">No messages with {m.name.split(" ")[0]} yet.</p> : c!.messages.map((w) => (
                <div key={w.id} className={cn("flex", w.direction === "outbound" ? "justify-end" : "justify-start")}>
                  <div className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-xs", w.direction === "outbound" ? "rounded-br-sm bg-[#dcf8c6] text-[#111b21] dark:bg-[#005c4b] dark:text-[#e9edef]" : "rounded-bl-sm bg-surface")}>
                    {w.template_name && <p className="mb-0.5 text-[11px] uppercase tracking-wide opacity-60">Template · {w.template_name.replace(/_/g, " ")}</p>}
                    {w.body && <p className="whitespace-pre-line">{w.body}</p>}{w.error && <p className="mt-1 text-xs text-danger">{w.error}</p>}
                    <p className="mt-1 text-right text-[11px] opacity-60" title={formatDate(w.created_at, "datetime")}>{timeAgo(w.created_at)}</p>
                  </div>
                </div>))}
              {c!.queued.map((q) => (
                <div key={q.id} className="flex justify-end"><div className={cn("max-w-[85%] rounded-2xl rounded-br-sm border border-dashed px-3 py-2 text-sm", q.status === "failed" ? "border-danger/40" : "border-border")}>
                  <p className="whitespace-pre-line">{q.body}</p>
                  <p className="mt-1 flex items-center justify-end gap-2 text-[11px] text-fg-muted">{q.status === "failed" ? <span className="text-danger">Not sent: {q.error}</span> : <><CalendarClock className="size-3" />{q.local_label}</>}<button type="button" onClick={() => cancel(q.id)} className="font-medium hover:text-danger">{q.status === "failed" ? "Dismiss" : "Cancel"}</button></p>
                </div></div>))}
              <div ref={end} />
            </div>
            {!c!.window_open ? (
              <div className="space-y-2 rounded-xl border border-border p-3">
                <p className="text-xs text-fg-muted">{m.name.split(" ")[0]} hasn&apos;t messaged you in the last 24 hours, so WhatsApp only allows an approved template. Pick one in {m.language_label} if you have it; once they reply you can write freely.</p>
                {templates.isLoading ? <Skeleton className="h-10" /> : <TemplateComposer templates={(templates.data ?? []).slice().sort((a, b) => Number(b.language.startsWith(m.language)) - Number(a.language.startsWith(m.language)))} defaults={[m.name.split(" ")[0]]} busy={busy === "send"} onSend={(t, params) => send({ template: { name: t.name, language: t.language, params } })} />}
              </div>
            ) : (
              <div className="space-y-2.5 rounded-xl border border-border p-3">
                <div className="flex flex-wrap gap-1.5">
                  {([["hello", "Hello"], ...(m.prices.length ? [["prices", `Prices in ${m.currency}`]] : []), ...(m.is_nri ? [["checklist", "Documents needed"]] : []), ["link", "Their page"]] as [string, string][]).map(([k, l]) =>
                    <Button key={k} size="xs" variant="secondary" loading={busy === k} onClick={() => draft(k)}>{l}</Button>)}
                </div>
                <Textarea rows={4} value={text} onChange={(e) => { setText(e.target.value); setTr(null); }} placeholder={english ? `Message ${m.name.split(" ")[0]}…` : `Write in English or Hinglish. It goes out in ${m.language_label}.`} maxLength={3000} />
                {!english && text.trim() && !tr && <Button size="sm" variant="soft" loading={busy === "translate"} onClick={translate}><Languages /> Translate to {m.language_label}</Button>}
                {tr && <div className="space-y-1.5">
                  <p className="text-xs font-medium text-fg-muted">{tr.ai ? `In ${m.language_label}. Edit it if anything reads wrong.` : "Goes out as you wrote it."}{tr.note && <span className="block font-normal text-fg-subtle">{tr.note}</span>}</p>
                  {tr.ai && <Textarea rows={4} dir="auto" value={tr.text} onChange={(e) => setTr({ ...tr, text: e.target.value })} maxLength={4096} />}
                </div>}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                  <div className="flex gap-1">{(["now", "morning"] as const).map((k) => <button key={k} type="button" onClick={() => setWhen(k)} aria-pressed={when === k} className={cn("h-8 rounded-full border px-3 text-[13px] font-medium", when === k ? "border-primary bg-primary-soft text-primary" : "border-border text-fg-muted hover:bg-surface-hover")}>{k === "now" ? "Send now" : `9 am in ${m.city || m.place}`}</button>)}</div>
                  <Button loading={busy === "send"} disabled={!outgoing.trim() || (!english && !tr)} onClick={() => send({ text: outgoing, original: tr?.ai ? text : undefined })}><Send /> {when === "now" ? "Send" : "Schedule"}</Button>
                </div>
                {!english && !tr && text.trim() && <p className="text-[11px] text-fg-subtle">Translate first so you can check the message before it goes.</p>}
                {clock.quiet && when === "now" && <p className="text-xs text-warning"><Moon className="mr-1 inline size-3.5 align-[-2px]" />It&apos;s {clock.time} in {m.city || m.place}. Consider sending at 9 am their time.</p>}
              </div>
            )}
          </div>
        )}
        <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Wall-clock "YYYY-MM-DDTHH:mm" for an instant, in a time zone. */
const localInput = (d: Date, tz: string) => { const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(d).map((x) => [x.type, x.value])); return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`; };

/** Book a walkthrough for a member (rep), or confirm one they asked for with a meeting link. Times are in their time zone. */
function WalkthroughDialog({ m, walk, onOpenChange, onDone }: { m: FamilyMember; walk: Walk | null; onOpenChange: (o: boolean) => void; onDone: () => void }) {
  const toast = useToast(); const tz = walk?.timezone ?? m.timezone;
  const [at, setAt] = React.useState(() => walk ? localInput(new Date(walk.starts_at), tz) : localInput(new Date(Date.now() + 86_400_000), tz).slice(0, 11) + "19:00");
  const [url, setUrl] = React.useState(""); const [note, setNote] = React.useState(""); const [notify, setNotify] = React.useState(true);
  const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null); const [done, setDone] = React.useState<{ message: string; sent: boolean; reason: string | null; emailed?: boolean } | null>(null);
  const ist = React.useMemo(() => { // what their chosen time is in India, for the rep
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(at)) return null;
    const guess = new Date(`${at}:00Z`); const offset = new Date(localInput(guess, tz) + ":00Z").getTime() - guess.getTime();
    return new Date(guess.getTime() - offset).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  }, [at, tz]);
  const go = async () => {
    setBusy(true); setErr(null);
    try {
      if (walk) {
        const changed = at !== localInput(new Date(walk.starts_at), tz);
        const r = await api.post<{ message: string; sent: boolean; reason: string | null; emailed?: boolean }>(`/api/v1/family/walkthroughs/${walk.id}/confirm`, { meeting_url: url.trim(), notify, ...(changed ? { starts_at: at } : {}) });
        onDone(); if (r.sent || !notify) { toast.success("Walkthrough confirmed", r.sent ? `${m.name} got the link on WhatsApp.` : "It's on your calendar."); onOpenChange(false); } else setDone(r);
      } else { await api.post(`/api/v1/family/${m.id}/walkthroughs`, { starts_at: at, note: note || null }); onDone(); toast.success("Walkthrough added", "Confirm it with a meeting link when you have one."); onOpenChange(false); }
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent title={walk ? "Confirm video walkthrough" : "Book a video walkthrough"} description={walk ? `${m.name} asked for this time. Add the meeting link and it goes on your calendar.` : `For ${m.name}. You'll confirm it with a meeting link.`}>
        {done ? (
          <div className="space-y-3">
            <p className="text-sm">Confirmed and on your calendar. {done.reason ? `The WhatsApp didn't go out: ${done.reason}` : ""}{done.emailed ? " We emailed them the link." : ""} Copy the message and send it another way:</p>
            <p className="whitespace-pre-line rounded-lg bg-bg-subtle px-3 py-2 text-[13px]" dir="auto">{done.message}</p>
            <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Close</Button><Button onClick={() => copy(done.message, toast, "Message copied")}><Copy /> Copy message</Button></DialogFooter>
          </div>
        ) : <>
          <div className="space-y-3">
            <Field label={`Time in ${place(tz)}`} hint={ist ? `That's ${ist} in India` : undefined}><Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} /></Field>
            {walk?.note && <p className="rounded-lg bg-bg-subtle px-3 py-2 text-[13px] text-fg-muted">“{walk.note}”</p>}
            {walk ? <>
              <Field label="Meeting link" hint="Google Meet, Zoom, or a WhatsApp video call link"><Input autoFocus value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://meet.google.com/…" /></Field>
              <label className="flex items-center justify-between gap-4 text-sm"><span>Send {m.name.split(" ")[0]} the time and link in {m.language_label}</span><Switch checked={notify} onCheckedChange={setNotify} aria-label="Notify them" /></label>
            </> : <Field label="Note (optional)"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Show the balcony view and the parking" /></Field>}
          </div>
          {err && <p role="alert" className="mt-3 text-sm text-danger">{err}</p>}
          <DialogFooter>
            {walk && <Button variant="ghost" className="mr-auto" onClick={async () => { await api.post(`/api/v1/family/walkthroughs/${walk.id}/cancel`); onDone(); onOpenChange(false); toast.success("Request declined"); }}><X /> Decline</Button>}
            <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button loading={busy} disabled={walk ? !/^https:\/\/\S+$/.test(url.trim()) : !at} onClick={go}>{walk ? <><Check /> Confirm</> : "Book"}</Button>
          </DialogFooter>
        </>}
      </DialogContent>
    </Dialog>
  );
}

/** Settings → Workspace: the rupee rate for AED and USD prices. Only the owner sets it. */
export function ExchangeRates() {
  const qc = useQueryClient(); const toast = useToast();
  const q = useQuery({ queryKey: ["fx-rates"], queryFn: () => api.get<Fx & { is_owner: boolean }>("/api/v1/family/settings") });
  const [f, setF] = React.useState({ AED: "", USD: "" }); const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (q.data) setF({ AED: q.data.rates.AED ? String(q.data.rates.AED) : "", USD: q.data.rates.USD ? String(q.data.rates.USD) : "" }); }, [q.data]);
  if (!q.data) return null; const owner = q.data.is_owner;
  const save = async () => { setBusy(true); try { await api.put("/api/v1/family/settings", { AED: Number(f.AED) || null, USD: Number(f.USD) || null }); qc.invalidateQueries({ queryKey: ["fx-rates"] }); qc.invalidateQueries({ queryKey: ["family"] }); toast.success("Exchange rates saved"); } catch (e) { toast.error("Couldn't save", errText(e)); } finally { setBusy(false); } };
  return (
    <SettingsSection title="Prices for NRI families" description="NRI family members see prices in AED or USD at the rate you set here. It doesn't follow the market, so a price your team quoted doesn't change overnight." actions={owner && <Button onClick={save} loading={busy}>Save rates</Button>}>
      <div className="grid gap-3 sm:grid-cols-2">
        {(["AED", "USD"] as const).map((c) => <Field key={c} label={`1 ${c} =`}><Input type="number" min={1} step="0.01" icon={<span className="text-sm text-fg-muted">₹</span>} value={f[c]} onChange={(e) => setF({ ...f, [c]: e.target.value })} disabled={!owner} placeholder={c === "AED" ? "22.70" : "83.40"} /></Field>)}
      </div>
      <p className="mt-2 text-xs text-fg-muted">{q.data.updated_at ? `Last set ${timeAgo(q.data.updated_at)}${q.data.updated_by ? ` by ${q.data.updated_by}` : ""}.` : "Not set yet, so AED and USD prices are hidden."}{!owner && " Only the workspace owner can change these."}</p>
    </SettingsSection>
  );
}
