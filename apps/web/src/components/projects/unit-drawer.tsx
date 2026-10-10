"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CalendarPlus, Handshake, History, Pencil, Phone, Sparkles, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { ApiError, Button, Drawer, Field, Input, NativeSelect, Skeleton, Textarea, cn, formatDate, timeAgo, useTheme, useToast } from "@crm/ui";
import { AsyncSelect, toLocalInput } from "@/components/forms/fields";
import { api } from "@/lib/api";
import { BHK_OPTIONS, FACINGS, STATUS, STATUS_ORDER, UNIT_KINDS, holdLeft, money, priceLine } from "@/lib/realestate";
import type { MatchLead, Unit, UnitEvent, UnitStatus } from "@/lib/realestate";

const HOLDS = [[24, "1 day"], [48, "2 days"], [72, "3 days"], [168, "1 week"]] as const;
const NEEDS_CLIENT: UnitStatus[] = ["booked", "sold", "rented"];

function StatusPill({ status, big }: { status: UnitStatus; big?: boolean }) {
  const { resolved } = useTheme();
  const s = STATUS[status];
  const Icon = s.icon;
  return <span className={cn("inline-flex items-center gap-1.5 rounded-full font-semibold", big ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs")} style={{ background: resolved === "dark" ? s.bgDark : s.bg, color: s.ink }}><Icon className={big ? "size-4" : "size-3"} />{s.label}</span>;
}

export function UnitDrawer({ unitId, onClose, canEdit }: { unitId: string | null; onClose: () => void; canEdit: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const router = useRouter();
  const { resolved } = useTheme();
  const [pending, setPending] = React.useState<UnitStatus | null>(null);
  const [hours, setHours] = React.useState(48);
  const [clientId, setClientId] = React.useState<string | null>(null);
  const [leadId, setLeadId] = React.useState<string | null>(null);
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [visit, setVisit] = React.useState<{ lead: string | null; at: string } | null>(null);
  React.useEffect(() => { setPending(null); setEditing(false); setVisit(null); setClientId(null); setLeadId(null); setNote(""); }, [unitId]);

  const unit = useQuery({ queryKey: ["unit", unitId], enabled: !!unitId, queryFn: () => api.get<Unit>(`/api/v1/units/${unitId}`) });
  const u = unit.data;
  const history = useQuery({ queryKey: ["unit-history", unitId], enabled: !!unitId, queryFn: () => api.get<UnitEvent[]>(`/api/v1/units/${unitId}/history`) });
  const sellable = !!u && ["vacant", "for_sale", "for_rent", "on_hold"].includes(u.status);
  const matches = useQuery({ queryKey: ["unit-matches", unitId, u?.status, u?.sale_price, u?.bhk], enabled: !!unitId && sellable, queryFn: () => api.get<MatchLead[]>(`/api/v1/units/${unitId}/matches`) });

  const refresh = () => { ["unit", "unit-history", "unit-matches", "building", "project", "projects", "units"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); };
  const fail = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

  const setStatus = async (status: UnitStatus, extra: Record<string, unknown> = {}) => {
    setBusy(true);
    try {
      await api.post(`/api/v1/units/${unitId}/status`, { status, ...extra });
      toast.success(`${u?.name ?? "Unit"} is now ${STATUS[status].label.toLowerCase()}`);
      setPending(null); setNote(""); setClientId(null); setLeadId(null);
      refresh();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const pick = (s: UnitStatus) => {
    if (!canEdit || !u || s === u.status) return;
    if (s === "on_hold" || NEEDS_CLIENT.includes(s)) setPending(s); else setStatus(s);
  };
  const confirm = () => {
    if (!pending) return;
    setStatus(pending, { note: note || undefined, ...(pending === "on_hold" ? { hold_hours: hours, lead_id: leadId } : { contact_id: clientId }) });
  };
  const holdFor = (m: MatchLead) => setStatus("on_hold", { hold_hours: 48, lead_id: m.id, note: `Held for ${m.name}` });

  const scheduleVisit = async () => {
    if (!visit || !u) return;
    setBusy(true);
    try {
      const start = new Date(visit.at);
      const lead = (matches.data ?? []).find((m) => m.id === visit.lead);
      await api.post("/api/v1/meetings", { title: `Site visit — ${lead?.name ?? "client"}, ${u.name}`, kind: "site_visit", starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 45 * 60000).toISOString(),
        lead_id: visit.lead, unit_id: u.id, location: `${u.project_name ?? ""}${u.tower_name ? `, ${u.tower_name}` : ""}` });
      toast.success("Site visit scheduled"); setVisit(null); refresh(); qc.invalidateQueries({ queryKey: ["meetings"] });
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const startDeal = async () => {
    if (!u) return;
    setBusy(true);
    try {
      const d = await api.post<{ id: string }>("/api/v1/deals", { name: `${u.name}, ${u.tower_name ?? ""}`.replace(/, $/, ""), unit_id: u.id, value: (u.status === "for_rent" ? u.monthly_rent : u.sale_price) ?? 0, contact_id: u.occupant_contact?.id ?? undefined });
      router.push(`/app/deals/${d.id}`);
    } catch (e) { fail(e); setBusy(false); }
  };

  return (
    <Drawer open={!!unitId} onOpenChange={(o) => !o && onClose()} width={540} title={u ? `${u.name} · ${u.tower_name ?? ""}` : "Flat"} description={u ? `${u.floor_label} · ${u.project_name}${u.project_city ? `, ${u.project_city}` : ""}` : undefined}>
      {!u ? <div className="space-y-4"><Skeleton className="h-16 w-full" /><Skeleton className="h-40 w-full" /><Skeleton className="h-32 w-full" /></div> : (
        <div className="space-y-6">
          <section className="rounded-xl border border-border bg-surface-2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <StatusPill status={u.status} big />
              <p className="text-right text-xs text-fg-muted">{u.days_in_status != null && (u.days_in_status === 0 ? "Changed today" : `For ${u.days_in_status} day${u.days_in_status === 1 ? "" : "s"}`)}</p>
            </div>
            {u.status === "on_hold" && (
              <p className="mt-3 rounded-lg px-3 py-2 text-sm" style={{ background: "color-mix(in srgb, #7c3aed 12%, transparent)" }}>
                Held {u.hold_lead ? <>for <Link href={`/app/leads/${u.hold_lead.id}`} className="font-medium text-primary hover:underline">{u.hold_lead.name}</Link></> : "for a client"}{u.held_by_name ? ` by ${u.held_by_name}` : ""} · <b>{holdLeft(u.hold_until)}</b>
              </p>
            )}
          </section>

          {canEdit && (
            <section aria-label="Change status">
              <h3 className="mb-2 text-sm font-semibold">Change status</h3>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {STATUS_ORDER.map((s) => {
                  const m = STATUS[s]; const Icon = m.icon; const cur = u.status === s;
                  return (
                    <button key={s} type="button" disabled={busy} onClick={() => pick(s)} aria-pressed={cur} title={m.hint}
                      className={cn("flex h-11 items-center gap-2 rounded-lg border px-2 text-left text-[12.5px] font-medium transition-all", cur ? "border-transparent shadow-sm" : "border-border bg-surface hover:-translate-y-px hover:border-border-strong hover:shadow-xs", pending === s && "ring-2 ring-primary")}
                      style={cur ? { background: resolved === "dark" ? m.bgDark : m.bg, color: m.ink } : undefined}>
                      <span className="grid size-6 shrink-0 place-items-center rounded-md" style={{ background: resolved === "dark" ? m.bgDark : m.bg, color: m.ink }}><Icon className="size-3.5" /></span>
                      <span className="line-clamp-2 leading-tight">{m.label}</span>
                    </button>
                  );
                })}
              </div>
              {pending && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-3 overflow-hidden">
                  <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
                    {pending === "on_hold" ? (
                      <>
                        <Field label="Hold for how long?"><div className="flex flex-wrap gap-1.5">{HOLDS.map(([h, l]) => <button key={h} type="button" onClick={() => setHours(h)} aria-pressed={hours === h} className={cn("h-8 rounded-full border px-3 text-[13px] font-medium", hours === h ? "border-primary bg-primary-soft text-primary" : "border-border text-fg-muted hover:bg-surface-hover")}>{l}</button>)}</div></Field>
                        <Field label="For which client? (optional)"><AsyncSelect value={leadId} onChange={setLeadId} endpoint="/api/v1/leads" placeholder="Search your leads…" /></Field>
                      </>
                    ) : (
                      <Field label={pending === "rented" ? "Who is the tenant? (optional)" : "Who is the buyer? (optional)"}><AsyncSelect value={clientId} onChange={setClientId} endpoint="/api/v1/contacts" placeholder="Search your contacts…" /></Field>
                    )}
                    <Field label="Note (optional)"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anything worth remembering" maxLength={500} /></Field>
                    <div className="flex justify-end gap-2"><Button variant="ghost" size="sm" onClick={() => setPending(null)}>Cancel</Button><Button size="sm" loading={busy} onClick={confirm}>Mark as {STATUS[pending].label.toLowerCase()}</Button></div>
                  </div>
                </motion.div>
              )}
            </section>
          )}

          <section aria-label="Details">
            <div className="mb-2 flex items-center justify-between"><h3 className="text-sm font-semibold">Details</h3>{canEdit && !editing && <Button variant="ghost" size="sm" onClick={() => setEditing(true)}><Pencil /> Edit</Button>}</div>
            {editing ? <EditUnit u={u} onDone={() => { setEditing(false); refresh(); }} onError={fail} /> : (
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl border border-border p-4 text-sm">
                {[["Size", u.bhk ?? "—"], ["Area", u.area_sqft ? `${Math.round(u.area_sqft).toLocaleString("en-IN")} sq ft` : "—"], ["Facing", u.facing ?? "—"], ["Type", UNIT_KINDS.find((k) => k[0] === u.kind)?.[1] ?? u.kind],
                  ["Sale price", money(u.sale_price)], ["Monthly rent", money(u.monthly_rent)], ["Per sq ft", u.sale_price && u.area_sqft ? `₹${Math.round(u.sale_price / u.area_sqft).toLocaleString("en-IN")}` : "—"], ["Asking", priceLine(u)]].map(([k, v]) => (
                  <div key={k}><dt className="text-xs text-fg-muted">{k}</dt><dd className="mt-0.5 font-medium tabular-nums">{v}</dd></div>))}
                {u.notes && <div className="col-span-2"><dt className="text-xs text-fg-muted">Notes</dt><dd className="mt-0.5 whitespace-pre-line">{u.notes}</dd></div>}
              </dl>
            )}
          </section>

          {(u.owner_contact || u.occupant_contact) && (
            <section aria-label="People" className="grid gap-2 sm:grid-cols-2">
              {([["Owner", u.owner_contact], [u.status === "rented" ? "Tenant" : "Buyer", u.occupant_contact]] as const).map(([label, p]) => p && (
                <Link key={label} href={`/app/contacts/${p.id}`} className="flex items-center gap-3 rounded-xl border border-border p-3 transition-colors hover:bg-surface-hover">
                  <span className="grid size-9 place-items-center rounded-full bg-primary-soft text-primary"><UserRound className="size-4" /></span>
                  <span className="min-w-0"><span className="block text-xs text-fg-muted">{label}</span><span className="block truncate text-sm font-medium">{p.name}</span>{p.phone && <span className="block truncate text-xs text-fg-subtle">{p.phone}</span>}</span>
                </Link>
              ))}
            </section>
          )}

          {canEdit && (
            <section className="flex flex-wrap gap-2" aria-label="Actions">
              <Button variant="secondary" size="sm" onClick={() => setVisit({ lead: null, at: toLocalInput(new Date(Date.now() + 864e5).toISOString().replace(/T.*/, "T11:00:00")) })}><CalendarPlus /> Schedule site visit</Button>
              <Button variant="secondary" size="sm" loading={busy} onClick={startDeal}><Handshake /> Start a deal</Button>
            </section>
          )}
          {visit && (
            <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
              <Field label="Who is visiting?"><AsyncSelect value={visit.lead} onChange={(id) => setVisit({ ...visit, lead: id })} endpoint="/api/v1/leads" placeholder="Search your leads…" /></Field>
              <Field label="When?"><Input type="datetime-local" value={visit.at} onChange={(e) => setVisit({ ...visit, at: e.target.value })} /></Field>
              <div className="flex justify-end gap-2"><Button variant="ghost" size="sm" onClick={() => setVisit(null)}>Cancel</Button><Button size="sm" loading={busy} onClick={scheduleVisit} disabled={!visit.at}>Schedule</Button></div>
            </div>
          )}

          {sellable && (matches.data?.length ?? 0) > 0 && (
            <section aria-label="Clients who may want this">
              <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><Sparkles className="size-4 text-primary" /> Clients who may want this</h3>
              <ul className="divide-y divide-border rounded-xl border border-border">
                {matches.data!.map((m) => (
                  <li key={m.id} className="flex items-center gap-3 px-3 py-2.5">
                    <div className="min-w-0 flex-1">
                      <Link href={`/app/leads/${m.id}`} className="block truncate text-sm font-medium hover:text-primary">{m.name}</Link>
                      <p className="truncate text-xs text-fg-muted">{[m.intent, m.bhk, m.budget_max ? `up to ${money(m.budget_max)}` : null].filter(Boolean).join(" · ")}{m.reasons.length ? ` — ${m.reasons.join(", ")}` : ""}</p>
                    </div>
                    {m.phone && <a href={`tel:${m.phone}`} aria-label={`Call ${m.name}`} className="grid size-8 place-items-center rounded-md text-fg-muted hover:bg-surface-hover hover:text-fg"><Phone className="size-4" /></a>}
                    {canEdit && u.status !== "on_hold" && <Button variant="secondary" size="sm" onClick={() => holdFor(m)} disabled={busy}>Hold</Button>}
                    {canEdit && <Button variant="ghost" size="sm" onClick={() => setVisit({ lead: m.id, at: toLocalInput(new Date(Date.now() + 864e5).toISOString().replace(/T.*/, "T11:00:00")) })}>Visit</Button>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-label="History">
            <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><History className="size-4 text-fg-muted" /> History</h3>
            {history.isLoading ? <Skeleton className="h-20 w-full" /> : !(history.data?.length) ? <p className="text-sm text-fg-muted">Nothing yet.</p> : (
              <ol className="relative space-y-3 border-l border-border pl-4">
                {history.data.map((e) => (
                  <li key={e.id} className="relative text-sm">
                    <span className="absolute -left-[21px] top-1.5 size-2.5 rounded-full border-2 border-surface" style={{ background: e.to_status ? STATUS[e.to_status].bg : "var(--fg-subtle)" }} />
                    <p>{e.type === "status" && e.to_status ? <>Marked <b>{STATUS[e.to_status].label.toLowerCase()}</b>{e.from_status ? <span className="text-fg-muted"> (was {STATUS[e.from_status].label.toLowerCase()})</span> : null}</> : e.type === "visit" ? "Site visit" : e.type === "created" ? "Added to inventory" : e.note}</p>
                    {e.note && e.type !== "note" && <p className="text-[13px] text-fg-muted">{e.note}</p>}
                    <p className="text-xs text-fg-subtle" title={formatDate(e.created_at, "datetime")}>{e.user_name ? `${e.user_name} · ` : ""}{timeAgo(e.created_at)}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      )}
    </Drawer>
  );
}

function EditUnit({ u, onDone, onError }: { u: Unit; onDone: () => void; onError: (e: unknown) => void }) {
  const [f, setF] = React.useState({ number: u.number, kind: u.kind, bhk: u.bhk ?? "", area_sqft: u.area_sqft?.toString() ?? "", facing: u.facing ?? "", sale_price: u.sale_price?.toString() ?? "", monthly_rent: u.monthly_rent?.toString() ?? "", notes: u.notes ?? "", owner_contact_id: u.owner_contact_id });
  const [busy, setBusy] = React.useState(false);
  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const save = async () => {
    setBusy(true);
    try {
      await api.patch(`/api/v1/units/${u.id}`, { number: f.number, kind: f.kind, bhk: f.bhk || null, area_sqft: num(f.area_sqft), facing: f.facing || null, sale_price: num(f.sale_price), monthly_rent: num(f.monthly_rent), notes: f.notes || null, owner_contact_id: f.owner_contact_id });
      onDone();
    } catch (e) { onError(e); } finally { setBusy(false); }
  };
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="grid grid-cols-2 gap-3 rounded-xl border border-border p-4">
      <Field label="Flat number"><Input value={f.number} onChange={set("number")} maxLength={20} /></Field>
      <Field label="Type"><NativeSelect value={f.kind} onChange={set("kind")}>{UNIT_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></Field>
      <Field label="Size"><NativeSelect value={f.bhk} onChange={set("bhk")}><option value="">—</option>{BHK_OPTIONS.map((b) => <option key={b}>{b}</option>)}</NativeSelect></Field>
      <Field label="Area (sq ft)"><Input type="number" min={0} value={f.area_sqft} onChange={set("area_sqft")} /></Field>
      <Field label="Facing"><NativeSelect value={f.facing} onChange={set("facing")}><option value="">—</option>{FACINGS.map((b) => <option key={b}>{b}</option>)}</NativeSelect></Field>
      <Field label="Owner"><AsyncSelect value={f.owner_contact_id} onChange={(id) => setF({ ...f, owner_contact_id: id })} endpoint="/api/v1/contacts" initialLabel={u.owner_contact?.name} placeholder="Search contacts…" /></Field>
      <Field label="Sale price (₹)"><Input type="number" min={0} value={f.sale_price} onChange={set("sale_price")} /></Field>
      <Field label="Monthly rent (₹)"><Input type="number" min={0} value={f.monthly_rent} onChange={set("monthly_rent")} /></Field>
      <div className="col-span-2"><Field label="Notes"><Textarea rows={3} value={f.notes} onChange={set("notes")} maxLength={5000} /></Field></div>
      <div className="col-span-2 flex justify-end gap-2"><Button variant="ghost" size="sm" onClick={onDone}>Cancel</Button><Button size="sm" loading={busy} onClick={save}>Save details</Button></div>
    </div>
  );
}

