"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Check, FileSignature, Plus, ScrollText, Sparkles, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { ApiError, Avatar, Badge, Button, Dialog, DialogContent, DialogFooter, EmptyState, Field, Input, NativeSelect, SkeletonRows, Textarea, cn, formatDate, timeAgo, useToast } from "@crm/ui";
import { type AiProposal, useAiFeature } from "@/lib/ai";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { ProposalList } from "../ai/proposal-card";
import { MemberSelect } from "../forms/fields";

export type PromiseStatus = "pending" | "approved" | "rejected" | "cancelled";
export type BuyerPromise = {
  id: string; title: string; kind: string; kind_label: string; details: string | null; value: number | string | null; status: PromiseStatus; status_label: string;
  source: string; source_label: string; source_text: string | null; promised_on: string | null; promised_by: string | null; promised_by_name: string | null;
  created_by: string | null; created_by_name: string | null; decided_by_name: string | null; decided_at: string | null; decision_note: string | null;
  buyer_name: string | null; unit_label: string | null; url: string | null; created_at: string;
};
export type PromiseSummary = { counts: Record<PromiseStatus, number>; can_approve: boolean; kinds: Record<string, string>; statuses: Record<PromiseStatus, string> };
export type RecordRef = { entity: "lead" | "contact" | "deal"; id: string };

export const KINDS: [string, string][] = [["discount", "Discount"], ["parking", "Parking"], ["fittings", "Fittings & furnishing"], ["possession", "Possession date"],
  ["payment_plan", "Payment plan"], ["waiver", "Charge waived"], ["other", "Other"]];
const TONE: Record<PromiseStatus, "warning" | "success" | "danger" | "neutral"> = { pending: "warning", approved: "success", rejected: "danger", cancelled: "neutral" };
const rupees = (v: number | string | null) => {
  if (v === null || v === undefined || v === "") return null; const n = Number(v);
  return n >= 1e7 ? `₹${+(n / 1e7).toFixed(2)} Cr` : n >= 1e5 ? `₹${+(n / 1e5).toFixed(2)} L` : `₹${n.toLocaleString("en-IN")}`;
};

export const usePromiseSummary = (enabled = true) => {
  const { can } = useAccess();
  return useQuery({ queryKey: ["promises", "summary"], enabled: enabled && can("promises.read"), staleTime: 30_000, queryFn: () => api.get<PromiseSummary>("/api/v1/promises/summary") });
};

/** Approve, reject or cancel. Reject and cancel ask for a reason (required to cancel an approved promise). */
function useDecide() {
  const qc = useQueryClient(); const toast = useToast();
  return useMutation({
    mutationFn: ({ p, action, note }: { p: BuyerPromise; action: "approve" | "reject" | "cancel"; note?: string }) => api.post<BuyerPromise>(`/api/v1/promises/${p.id}/${action}`, { note: note || undefined }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["promises"] }); qc.invalidateQueries({ queryKey: ["timeline"] }); toast.success(`Promise ${r.status_label.toLowerCase()}`, r.title); },
    onError: (e) => toast.error("Couldn't update the promise", (e as Error).message),
  });
}

function ReasonDialog({ open, onOpenChange, title, description, required, confirm, onConfirm, busy }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description: string; required?: boolean; confirm: string; onConfirm: (note: string) => void; busy?: boolean }) {
  const [note, setNote] = React.useState("");
  React.useEffect(() => { if (open) setNote(""); }, [open]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description={description}>
        <Field label={required ? "Reason" : "Reason (optional)"}><Textarea rows={3} autoFocus value={note} onChange={(e) => setNote(e.target.value)} placeholder="Shown to the rep and kept in the record" /></Field>
        <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Back</Button><Button variant="danger" loading={busy} disabled={required && !note.trim()} onClick={() => onConfirm(note.trim())}>{confirm}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PromiseRow({ p, showBuyer, canApprove }: { p: BuyerPromise; showBuyer?: boolean; canApprove: boolean }) {
  const { me } = useAccess(); const decide = useDecide(); const [ask, setAsk] = React.useState<"reject" | "cancel" | null>(null);
  const mine = p.created_by === me?.user?.id;
  const canCancel = (p.status === "pending" && (mine || canApprove)) || (p.status === "approved" && canApprove);
  const worth = rupees(p.value);
  return (
    <li className="px-4 py-3.5">
      <div className="flex flex-wrap items-start gap-3">
        <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full", p.status === "approved" ? "bg-success-soft text-success" : p.status === "pending" ? "bg-warning-soft text-warning" : "bg-bg-subtle text-fg-subtle")}><ScrollText className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium"><span className={cn(p.status === "cancelled" || p.status === "rejected" ? "text-fg-muted line-through decoration-fg-subtle" : "")}>{p.title}</span><Badge tone={TONE[p.status]} dot>{p.status_label}</Badge><Badge tone="outline">{p.kind_label}</Badge>{worth && <span className="tabular text-[13px] font-semibold">{worth}</span>}</p>
          {showBuyer && p.buyer_name && <p className="mt-0.5 text-[13px] text-fg-muted">To {p.url ? <Link className="font-medium text-fg hover:text-primary hover:underline" href={p.url}>{p.buyer_name}</Link> : p.buyer_name}{p.unit_label && <> · {p.unit_label}</>}</p>}
          {!showBuyer && p.unit_label && <p className="mt-0.5 text-[13px] text-fg-muted">{p.unit_label}</p>}
          {p.details && <p className="mt-1 whitespace-pre-line text-[13px] text-fg-muted">{p.details}</p>}
          {p.source_text && <blockquote className="mt-1.5 border-l-2 border-border pl-2.5 text-[12.5px] italic text-fg-muted">“{p.source_text}”<span className="not-italic text-fg-subtle"> · {p.source_label}</span></blockquote>}
          <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-xs text-fg-subtle"><Avatar name={p.promised_by_name ?? "?"} size={16} />Promised by <span className="font-medium text-fg-muted">{p.promised_by_name ?? "Unknown"}</span>{p.promised_on && <> on {formatDate(p.promised_on + "T00:00:00")}</>}{p.created_by_name && p.created_by_name !== p.promised_by_name && <> · recorded by {p.created_by_name}</>}</p>
          {p.decided_at && <p className={cn("mt-1 text-xs", p.status === "approved" ? "text-success" : p.status === "rejected" ? "text-danger" : "text-fg-subtle")}>{p.status_label} by {p.decided_by_name} {timeAgo(p.decided_at)}{p.decision_note && <span className="text-fg-muted">: {p.decision_note}</span>}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap gap-1.5">
          {p.status === "pending" && canApprove && <><Button size="sm" onClick={() => decide.mutate({ p, action: "approve" })} loading={decide.isPending && decide.variables?.action === "approve"}><Check /> Approve</Button><Button size="sm" variant="secondary" onClick={() => setAsk("reject")}><X /> Reject</Button></>}
          {canCancel && <Button size="sm" variant="ghost" onClick={() => setAsk("cancel")}><Ban /> Cancel</Button>}
        </div>
      </div>
      <ReasonDialog open={ask !== null} onOpenChange={(o) => !o && setAsk(null)} busy={decide.isPending}
        title={ask === "reject" ? `Reject “${p.title}”?` : `Cancel “${p.title}”?`}
        description={ask === "reject" ? `${p.promised_by_name ?? "The rep"} will be told it isn't approved, so they can tell the buyer.` : p.status === "approved" ? "It stays in the ledger as cancelled and comes off the booking form. Say why, for example the buyer agreed to drop it." : "It stays in the ledger as cancelled."}
        required={ask === "cancel" && p.status === "approved"} confirm={ask === "reject" ? "Reject" : "Cancel promise"}
        onConfirm={(note) => decide.mutate({ p, action: ask!, note }, { onSuccess: () => setAsk(null) })} />
    </li>
  );
}

function AddPromise({ open, onOpenChange, record }: { open: boolean; onOpenChange: (o: boolean) => void; record: RecordRef }) {
  const qc = useQueryClient(); const toast = useToast(); const { me } = useAccess();
  const empty = { title: "", kind: "other", value: "", details: "", promised_by: me?.user?.id ?? null as string | null, promised_on: new Date().toISOString().slice(0, 10) };
  const [f, setF] = React.useState(empty); const [err, setErr] = React.useState<string | null>(null);
  React.useEffect(() => { if (open) { setF({ ...empty, promised_by: me?.user?.id ?? null }); setErr(null); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: () => api.post<BuyerPromise>("/api/v1/promises", { [`${record.entity}_id`]: record.id, title: f.title.trim(), kind: f.kind, value: f.value === "" ? null : Number(f.value), details: f.details.trim() || null, promised_by: f.promised_by, promised_on: f.promised_on || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["promises"] }); qc.invalidateQueries({ queryKey: ["timeline"] }); toast.success("Promise recorded", "A manager will approve or reject it."); onOpenChange(false); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : (e as Error).message),
  });
  const set = (k: keyof typeof f) => (v: string | null) => setF((s) => ({ ...s, [k]: v ?? "" }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Record a promise" description="Anything you told the buyer that isn't in the standard price and terms. A manager approves it before it goes on the booking form.">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (f.title.trim().length >= 2) save.mutate(); }}>
          <Field label="What was promised" required><Input autoFocus value={f.title} onChange={(e) => set("title")(e.target.value)} placeholder="e.g. Free covered parking" maxLength={200} /></Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Type"><NativeSelect value={f.kind} onChange={(e) => set("kind")(e.target.value)}>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect></Field>
            <Field label="Worth (₹, optional)" hint={rupees(f.value) ?? undefined}><Input type="number" inputMode="decimal" min={0} value={f.value} onChange={(e) => set("value")(e.target.value)} placeholder="e.g. 300000" /></Field>
            <Field label="Promised by"><MemberSelect value={f.promised_by} onChange={set("promised_by")} allowNone={false} /></Field>
            <Field label="Promised on"><Input type="date" value={f.promised_on} onChange={(e) => set("promised_on")(e.target.value)} /></Field>
          </div>
          <Field label="Details (optional)"><Textarea rows={3} value={f.details} onChange={(e) => set("details")(e.target.value)} placeholder="Conditions, e.g. only if booked by 31 Oct" /></Field>
          {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{err}</p>}
          <DialogFooter><Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" loading={save.isPending} disabled={f.title.trim().length < 2}>Record promise</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type Scan = { proposals: AiProposal[]; scanned: number; already_recorded: number; ai: boolean };

/** Reads the buyer's WhatsApp messages and call/visit notes (or pasted text) and suggests promises as cards to confirm. */
function FindPromises({ open, onOpenChange, record }: { open: boolean; onOpenChange: (o: boolean) => void; record: RecordRef }) {
  const [text, setText] = React.useState(""); const [out, setOut] = React.useState<Scan | null>(null); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  const run = async (pasted?: string) => {
    setBusy(true); setErr(null);
    try { setOut(await api.post<Scan>("/api/v1/ai/promises/scan", { record: `${record.entity}:${record.id}`, text: pasted || undefined })); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  React.useEffect(() => { if (open) { setOut(null); setText(""); run(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Find promises</span>} description="I read this buyer's WhatsApp messages, call notes and visit notes for anything your team promised. Nothing is recorded until you approve a card.">
        <div className="space-y-3">
          {busy && !out ? <SkeletonRows rows={3} /> : out && (
            out.proposals.length ? <><p className="text-[13px] text-fg-muted">Found {out.proposals.length} promise{out.proposals.length === 1 ? "" : "s"} in {out.scanned} message{out.scanned === 1 ? "" : "s"} and notes{out.already_recorded ? `, plus ${out.already_recorded} already in the ledger` : ""}. Approving a card records it for a manager to approve.</p><ProposalList items={out.proposals} compact /></>
              : <p className="rounded-xl border border-dashed border-border px-4 py-3 text-[13px] text-fg-muted">{out.scanned ? `No new promises in ${out.scanned} message${out.scanned === 1 ? "" : "s"} and notes${out.already_recorded ? ` (${out.already_recorded} already recorded)` : ""}.` : "There are no WhatsApp messages or notes for this buyer yet."} You can paste call notes below.</p>)}
          {!out?.ai && out && <p className="text-xs text-fg-subtle">Basic mode looks for common promises (parking, discounts, fittings, possession dates, payment plans, waived charges). Connect an AI key in Settings to catch the rest.</p>}
          <Field label="Or paste a chat or call notes"><Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Told Priya we'll give free covered parking and possession by March 2027" /></Field>
          {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{err}</p>}
          <DialogFooter><Button variant="ghost" onClick={() => onOpenChange(false)}>Close</Button><Button variant="secondary" onClick={() => run(text.trim())} loading={busy && !!text.trim()} disabled={!text.trim()}><Sparkles /> Find in pasted text</Button></DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export async function downloadBookingForm(record: RecordRef) {
  const res = await api.raw("GET", `/api/v1/promises/booking-form?record=${record.entity}:${record.id}`);
  if (!res.ok) { const e = (await res.json().catch(() => null))?.error ?? {}; throw new ApiError(res.status, e.code ?? "error", e.message ?? "Couldn't make the booking form."); }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "Booking form.pdf";
  const url = URL.createObjectURL(await res.blob()); const a = document.createElement("a"); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** The "Promises" tab on a lead, client or deal: everything promised to this buyer, across their lead, client and deal records. */
export function PromisesTab({ record }: { record: RecordRef }) {
  const { can } = useAccess(); const toast = useToast(); const finder = useAiFeature("promises");
  const q = useQuery({ queryKey: ["promises", "record", record.entity, record.id], queryFn: () => api.page<BuyerPromise>("/api/v1/promises", { record: `${record.entity}:${record.id}`, per_page: 100, sort: "-created_at" }) });
  const summary = usePromiseSummary(); const canApprove = !!summary.data?.can_approve;
  const [add, setAdd] = React.useState(false); const [find, setFind] = React.useState(false); const [dl, setDl] = React.useState(false);
  const rows = q.data?.data ?? [];
  const order: PromiseStatus[] = ["pending", "approved", "rejected", "cancelled"];
  const sorted = [...rows].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status));
  const pending = rows.filter((p) => p.status === "pending").length; const approved = rows.filter((p) => p.status === "approved").length;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {can("promises.create") && <Button variant="secondary" size="sm" onClick={() => setAdd(true)}><Plus /> Record a promise</Button>}
        {can("promises.create") && finder && <Button variant="secondary" size="sm" onClick={() => setFind(true)}><Sparkles /> Find promises in chats</Button>}
        <Button variant="ghost" size="sm" loading={dl} onClick={async () => { setDl(true); try { await downloadBookingForm(record); } catch (e) { toast.error("Couldn't download", (e as Error).message); } finally { setDl(false); } }}><FileSignature /> Booking form PDF</Button>
      </div>
      {pending > 0 && <p className="rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning">{pending} promise{pending === 1 ? " is" : "s are"} waiting for a manager. Only approved promises print on the booking form{approved ? ` (${approved} now)` : ""}.</p>}
      {q.isLoading ? <SkeletonRows rows={3} /> : !rows.length ? <EmptyState compact icon={<ScrollText />} title="No promises yet" description="Record anything promised to this buyer, like free parking or an extra discount, so a manager can approve it and it prints on the booking form." /> : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">{sorted.map((p) => <PromiseRow key={p.id} p={p} canApprove={canApprove} />)}</ul>)}
      <AddPromise open={add} onOpenChange={setAdd} record={record} />
      {finder && <FindPromises open={find} onOpenChange={setFind} record={record} />}
    </div>
  );
}

