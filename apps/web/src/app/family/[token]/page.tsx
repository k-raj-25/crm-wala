"use client";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle, Clock, MapPin, Video } from "lucide-react";
import { useParams } from "next/navigation";
import * as React from "react";
import { ApiError, Avatar, Badge, Button, Card, ErrorState, Field, Input, NativeSelect, Spinner, Textarea, cn } from "@crm/ui";
import { api } from "@/lib/api";

/** A buyer's family member's own page (no sign-in; the link is the key): the flat and its price in their currency, the
 *  NRI document checklist, and a form to ask for a video walkthrough at a time in their own time zone. */
type Page = {
  workspace: { name: string; logo_url: string | null };
  member: { first_name: string; timezone: string; place: string; currency: string; is_nri: boolean };
  project: { name: string; city: string | null; locality: string | null; rera_id: string | null; possession: string | null } | null;
  prices: { label: string; inr_text: string; amount_text: string | null; rate: number | null; currency: string }[];
  checklist: { key: string; label: string; hint: string; done: boolean }[];
  walkthroughs: { id: string; status: "requested" | "confirmed"; starts_at: string; local_label: string; meeting_url: string | null }[];
};

const SLOTS = Array.from({ length: 29 }, (_, i) => `${String(8 + Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`); // 8:00 am to 10:00 pm
const slotLabel = (s: string) => { const [h, m] = s.split(":").map(Number); return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`; };
const today = (tz: string) => new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date());

export default function FamilyPage() {
  const { token } = useParams<{ token: string }>();
  const q = useQuery({ queryKey: ["family-page", token], retry: false, queryFn: () => api.get<Page>(`/api/v1/public/family/${token}`) });
  const [data, setData] = React.useState<Page | null>(null);
  const d = data ?? q.data;
  if (q.isLoading) return <Shell><div className="flex justify-center py-24"><Spinner className="size-8 text-primary" /></div></Shell>;
  if (!d) return <Shell><ErrorState title="This link doesn't work any more" description="Ask the person who sent it to share a new one." /></Shell>;
  const tz = d.member.timezone;
  return (
    <Shell>
      <header className="flex items-center gap-3">
        <Avatar name={d.workspace.name} src={d.workspace.logo_url ?? undefined} size={40} square />
        <div><p className="text-xs text-fg-muted">Shared with you by</p><p className="font-semibold">{d.workspace.name}</p></div>
      </header>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Hi {d.member.first_name}</h1>
        <p className="mt-1 text-sm text-fg-muted">Everything about the home your family is looking at, with times in {d.member.place} time{d.member.currency !== "INR" ? ` and prices in ${d.member.currency}` : ""}.</p>
      </div>

      {(d.project || d.prices.length > 0) && <Card className="p-5">
        {d.project && <><p className="text-lg font-semibold">{d.project.name}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-fg-muted">{(d.project.locality || d.project.city) && <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" />{[d.project.locality, d.project.city].filter(Boolean).join(", ")}</span>}
            {d.project.possession && <span>Possession {new Date(d.project.possession).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}</span>}{d.project.rera_id && <span>RERA {d.project.rera_id}</span>}</p></>}
        {d.prices.length > 0 && <dl className="mt-4 divide-y divide-border">{d.prices.map((p) => (
          <div key={p.label} className="flex flex-wrap items-baseline justify-between gap-2 py-2.5"><dt className="text-sm text-fg-muted">{p.label}</dt>
            <dd className="text-right"><span className="tabular text-lg font-semibold">{p.amount_text ?? p.inr_text}</span>{p.amount_text && <span className="block text-xs text-fg-muted">{p.inr_text}</span>}</dd></div>))}</dl>}
        {d.prices.some((p) => p.rate) && <p className="mt-2 text-[11px] text-fg-subtle">{d.member.currency} amounts are approximate, at ₹{d.prices.find((p) => p.rate)!.rate} per {d.member.currency}. The final price is in rupees.</p>}
      </Card>}

      <Walkthroughs d={d} token={token} onChange={setData} tz={tz} />

      {d.checklist.length > 0 && <Card className="p-5">
        <p className="font-semibold">Documents for buying from abroad</p>
        <p className="mt-0.5 text-[13px] text-fg-muted">{d.checklist.filter((i) => i.done).length} of {d.checklist.length} received. Send clear scans on WhatsApp.</p>
        <ul className="mt-4 space-y-3">{d.checklist.map((i) => (
          <li key={i.key} className="flex gap-3">{i.done ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-label="Received" /> : <Circle className="mt-0.5 size-5 shrink-0 text-fg-subtle" aria-label="Needed" />}
            <span><span className={cn("text-sm font-medium", i.done && "text-fg-muted")}>{i.label}</span><span className="block text-xs text-fg-muted">{i.hint}</span></span></li>))}</ul>
        <p className="mt-4 text-[11px] text-fg-subtle">General guidance, not legal advice. Your bank and the sales team will confirm what your case needs.</p>
      </Card>}
    </Shell>
  );
}

function Walkthroughs({ d, token, tz, onChange }: { d: Page; token: string; tz: string; onChange: (p: Page) => void }) {
  const [day, setDay] = React.useState(""); const [slot, setSlot] = React.useState("19:00"); const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null); const [sent, setSent] = React.useState(false);
  const min = today(tz);
  const ask = async () => {
    setBusy(true); setErr(null);
    try { onChange(await api.post<Page>(`/api/v1/public/family/${token}/walkthrough`, { starts_at: `${day}T${slot}`, note: note || null })); setSent(true); setNote(""); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Couldn't send. Please try again."); } finally { setBusy(false); }
  };
  return (
    <Card className="p-5">
      <p className="flex items-center gap-2 font-semibold"><Video className="size-5 text-primary" />Video walkthrough</p>
      <p className="mt-0.5 text-[13px] text-fg-muted">Pick a time that suits you. Someone from the site walks you through the flat on a video call.</p>
      {d.walkthroughs.length > 0 && <ul className="mt-4 space-y-2">{d.walkthroughs.map((w) => (
        <li key={w.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2.5 text-sm">
          <Clock className="size-4 text-fg-muted" /><span className="flex-1">{w.local_label}</span>
          {w.status === "confirmed" ? (w.meeting_url ? <Button size="sm" asChild><a href={w.meeting_url} target="_blank" rel="noreferrer">Join</a></Button> : <Badge tone="success">Confirmed</Badge>) : <Badge tone="warning">Waiting for confirmation</Badge>}
        </li>))}</ul>}
      {sent && <p className="mt-3 text-sm text-success">Thanks! We&apos;ll confirm with a video link on WhatsApp.</p>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label="Date"><Input type="date" min={min} value={day} onChange={(e) => setDay(e.target.value)} /></Field>
        <Field label={`Time (${d.member.place})`}><NativeSelect value={slot} onChange={(e) => setSlot(e.target.value)}>{SLOTS.map((s) => <option key={s} value={s}>{slotLabel(s)}</option>)}</NativeSelect></Field>
        <Field label="Anything to show you? (optional)" className="sm:col-span-2"><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="The balcony view, the parking, the kitchen…" /></Field>
      </div>
      {err && <p role="alert" className="mt-2 text-sm text-danger">{err}</p>}
      <Button className="mt-4 w-full sm:w-auto" loading={busy} disabled={!day} onClick={ask}>Ask for this time</Button>
    </Card>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="min-h-dvh bg-bg"><div className="mx-auto max-w-xl space-y-5 px-4 py-8 sm:py-12">{children}</div></main>;
}
