"use client";
import { Building2, Check, ChevronLeft, ChevronRight, Download, FileText, Hand, MapPin, X } from "lucide-react";
import * as React from "react";
import { Badge, Button, Dialog, DialogContent, DialogFooter, Field, Input, LogoMark, Spinner, Textarea, cn, formatDate } from "@crm/ui";

type Flat = {
  id: string; title: string; subtitle: string; status: string; bhk: string | null; area: string | null; floor: string | null; facing: string | null;
  price: string | null; rate: string | null; rent: string | null; availability: string | null; can_hold: boolean; hold_requested: boolean;
};
type Row = { key: string; label: string; values: string[]; best: number[]; same: boolean };
export type PublicRecap = {
  workspace: string | null; rep: { name: string | null; job_role: string | null }; buyer_first_name: string | null; visited_on: string;
  project: { name: string; location: string | null; developer: string | null; rera_id: string | null; address: string | null } | null;
  message: string | null; flats: Flat[]; comparison: { flats: Flat[]; rows: Row[] } | null; photos: string[];
  documents: { id: string; kind: string; label: string; filename: string; mime_type: string }[]; has_price_list: boolean;
};

const Section = ({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) => (
  <section className={cn("space-y-3", className)}><h2 className="text-[13px] font-semibold uppercase tracking-wide text-fg-muted">{title}</h2>{children}</section>
);

function Gallery({ urls }: { urls: string[] }) {
  const [at, setAt] = React.useState<number | null>(null);
  const step = (n: number) => setAt((i) => (i === null ? i : (i + n + urls.length) % urls.length));
  React.useEffect(() => {
    if (at === null) return;
    const k = (e: KeyboardEvent) => { if (e.key === "ArrowRight") step(1); if (e.key === "ArrowLeft") step(-1); if (e.key === "Escape") setAt(null); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      <div className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:grid sm:grid-cols-3 sm:px-0">
        {urls.map((u, i) => (
          <button key={u} type="button" onClick={() => setAt(i)} className="aspect-[4/3] w-[72%] shrink-0 snap-start overflow-hidden rounded-xl bg-bg-subtle sm:w-auto">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={u} alt={`Photo ${i + 1} from your visit`} loading={i < 2 ? "eager" : "lazy"} className="size-full object-cover" />
          </button>
        ))}
      </div>
      {at !== null && (
        <div role="dialog" aria-label="Photo" className="fixed inset-0 z-50 flex items-center justify-center bg-black/90" onClick={() => setAt(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={urls[at]} alt={`Photo ${at + 1}`} className="max-h-full max-w-full object-contain" onClick={(e) => e.stopPropagation()} />
          <button type="button" aria-label="Close" className="absolute right-3 top-3 flex size-10 items-center justify-center rounded-full bg-white/15 text-white" onClick={() => setAt(null)}><X /></button>
          {urls.length > 1 && <>
            <button type="button" aria-label="Previous photo" className="absolute left-2 flex size-10 items-center justify-center rounded-full bg-white/15 text-white" onClick={(e) => { e.stopPropagation(); step(-1); }}><ChevronLeft /></button>
            <button type="button" aria-label="Next photo" className="absolute right-2 flex size-10 items-center justify-center rounded-full bg-white/15 text-white" onClick={(e) => { e.stopPropagation(); step(1); }}><ChevronRight /></button>
            <p className="absolute bottom-4 text-sm text-white/80">{at + 1} / {urls.length}</p>
          </>}
        </div>
      )}
    </>
  );
}

function HoldDialog({ flat, token, repName, onClose, onDone }: { flat: Flat; token: string; repName: string; onClose: () => void; onDone: () => void }) {
  const [name, setName] = React.useState(""); const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const res = await fetch(`/api/v1/public/recaps/${token}/hold`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ unit_id: flat.id, name: name.trim() || undefined, note: note.trim() || undefined }) });
      const j = await res.json().catch(() => null);
      if (!res.ok) throw new Error(j?.error?.message ?? "Couldn't send your request. Please try again.");
      onDone();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm" title={`Hold ${flat.title}?`} description={`${repName} gets your request right away and will call you to confirm the hold. Nothing is booked or paid yet.`}>
        <div className="space-y-3">
          <Field label="Your name (optional)"><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="So they know who's asking" /></Field>
          <Field label="Anything to add? (optional)"><Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="e.g. Please hold it till Sunday, my parents want to see it" /></Field>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={busy}><Hand /> Request hold</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FlatCard({ f, onHold }: { f: Flat; onHold: () => void }) {
  const facts = [["Size", f.bhk], ["Area", f.area], ["Floor", f.floor], ["Facing", f.facing], ["Per sq ft", f.rate], ["Status", f.availability]].filter(([, v]) => v) as [string, string][];
  return (
    <article className="overflow-hidden rounded-2xl border border-border bg-surface shadow-xs">
      <div className="flex items-start justify-between gap-3 p-4 pb-3">
        <div className="min-w-0"><h3 className="text-lg font-semibold tracking-tight">{f.title}</h3>{f.subtitle && <p className="text-sm text-fg-muted">{f.subtitle}</p>}</div>
        <div className="text-right">{f.price && <p className="tabular text-lg font-semibold">{f.price}</p>}{f.rent && <p className="tabular text-sm text-fg-muted">{f.rent}</p>}</div>
      </div>
      {facts.length > 0 && <dl className="grid grid-cols-3 gap-x-3 gap-y-2 border-t border-border px-4 py-3 text-sm">{facts.map(([k, v]) => <div key={k} className="min-w-0"><dt className="text-xs text-fg-muted">{k}</dt><dd className="truncate font-medium">{v}</dd></div>)}</dl>}
      <div className="border-t border-border p-3">
        {f.hold_requested ? <p className="flex items-center justify-center gap-2 py-1.5 text-sm font-medium text-success"><Check className="size-4" /> Hold requested. You'll get a call to confirm.</p>
          : f.can_hold ? <Button className="w-full" onClick={onHold}><Hand /> Hold this flat</Button>
            : <p className="py-1.5 text-center text-sm text-fg-muted">This flat is no longer available.</p>}
      </div>
    </article>
  );
}

function Comparison({ c }: { c: NonNullable<PublicRecap["comparison"]> }) {
  const rows = c.rows.filter((r) => !r.same || r.key === "price");
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <table className="w-full min-w-[480px] border-separate border-spacing-0 overflow-hidden rounded-xl border border-border bg-surface text-sm">
        <thead><tr><th className="sticky left-0 z-[1] bg-surface px-3 py-2.5 text-left text-xs font-medium text-fg-muted" />{c.flats.map((f) => <th key={f.id} className="border-l border-border px-3 py-2.5 text-left font-semibold">{f.title}</th>)}</tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.key}><th scope="row" className="sticky left-0 z-[1] border-t border-border bg-surface px-3 py-2.5 text-left text-xs font-medium text-fg-muted">{r.label}</th>
            {r.values.map((v, i) => <td key={i} className={cn("border-l border-t border-border px-3 py-2.5 align-top", r.best.includes(i) && "font-semibold text-success", r.key === "price" && "font-semibold")}>{v}{r.best.includes(i) && <Check className="ml-1 inline size-3.5" aria-label="best" />}</td>)}</tr>
        ))}</tbody>
      </table>
      <p className="mt-2 text-xs text-fg-muted">Green marks the best value: lowest price, lowest rate, biggest area.</p>
    </div>
  );
}

export function RecapPage({ token, preview }: { token: string; preview?: boolean }) {
  const [d, setD] = React.useState<PublicRecap | null>(null);
  const [state, setState] = React.useState<"loading" | "ok" | "gone">("loading");
  const [hold, setHold] = React.useState<Flat | null>(null);
  const [done, setDone] = React.useState<string | null>(null);
  React.useEffect(() => {
    fetch(`/api/v1/public/recaps/${token}${preview ? "?meta=1" : ""}`).then(async (r) => { if (!r.ok) throw new Error(); setD((await r.json()).data); setState("ok"); }).catch(() => setState("gone"));
  }, [token, preview]);

  if (state === "loading") return <div className="flex min-h-dvh items-center justify-center"><Spinner className="size-8 text-primary" /></div>;
  if (state === "gone" || !d) return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center"><Building2 className="size-10 text-fg-subtle" /><h1 className="text-lg font-semibold">This link has expired</h1><p className="max-w-sm text-sm text-fg-muted">Ask your sales contact to send you a fresh one.</p></div>
  );
  const rep = d.rep.name ?? "Your sales contact";
  const photo = (id: string) => `/api/v1/public/recaps/${token}/files/${id}`;
  return (
    <div className="min-h-dvh bg-bg">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto max-w-2xl px-4 pb-6 pt-5">
          <p className="text-sm font-medium text-fg-muted">{d.workspace}</p>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight">{d.buyer_first_name ? `${d.buyer_first_name}, here's` : "Here's"} your visit{d.project ? ` to ${d.project.name}` : ""}</h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-muted">
            <span>{formatDate(d.visited_on, "long")}</span>
            {d.project?.location && <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" />{d.project.location}</span>}
          </p>
          {preview && <Badge tone="warning" className="mt-3">Preview: your views don't count as the buyer opening it</Badge>}
        </div>
      </header>

      <main className="mx-auto max-w-2xl space-y-8 px-4 py-6">
        {d.message && (
          <figure className="rounded-2xl bg-primary-soft/60 p-4">
            <blockquote className="whitespace-pre-line text-[15px] leading-relaxed">{d.message}</blockquote>
            {!(d.rep.name && d.message.trim().endsWith(d.rep.name)) && <figcaption className="mt-2 text-sm text-fg-muted">{rep}{d.rep.job_role ? `, ${d.rep.job_role}` : ""}</figcaption>}
          </figure>
        )}

        {d.photos.length > 0 && <Section title="Photos from your visit"><Gallery urls={d.photos.map(photo)} /></Section>}

        {d.flats.length > 0 && (
          <Section title={d.flats.length === 1 ? "The flat you saw" : `The ${d.flats.length} flats you saw`}>
            {done && <p className="flex items-start gap-2 rounded-xl bg-success-soft p-3 text-sm text-fg"><Check className="mt-0.5 size-4 shrink-0 text-success" />{rep} has your request to hold {done} and will call you to confirm.</p>}
            <div className="space-y-3">{d.flats.map((f) => <FlatCard key={f.id} f={f} onHold={() => setHold(f)} />)}</div>
          </Section>
        )}

        {d.comparison && <Section title="Side by side"><Comparison c={d.comparison} /></Section>}

        {d.flats.some((f) => f.price || f.rent) && (
          <Section title="Price details">
            <div className="divide-y divide-border rounded-xl border border-border bg-surface text-sm">
              {d.flats.filter((f) => f.price || f.rent).map((f) => (
                <div key={f.id} className="flex items-center justify-between gap-3 px-4 py-3"><span className="min-w-0"><span className="font-medium">{f.title}</span>{f.area && <span className="text-fg-muted"> · {f.area}</span>}</span>
                  <span className="text-right tabular"><span className="font-semibold">{f.price ?? f.rent}</span>{f.rate && <span className="block text-xs text-fg-muted">{f.rate} per sq ft</span>}</span></div>
              ))}
            </div>
            <p className="text-xs text-fg-muted">{d.has_price_list ? "These are the listed prices. The price list below has the full breakdown." : `These are the listed prices. Ask ${rep} for the full cost sheet with taxes, registration and other charges.`}</p>
          </Section>
        )}

        {d.documents.length > 0 && (
          <Section title="Documents">
            <ul className="divide-y divide-border rounded-xl border border-border bg-surface">{d.documents.map((doc) => (
              <li key={doc.id}><a href={photo(doc.id)} target="_blank" rel="noreferrer" className="flex items-center gap-3 px-4 py-3 hover:bg-surface-hover">
                <FileText className="size-5 shrink-0 text-primary" /><span className="min-w-0 flex-1"><span className="block text-sm font-medium">{doc.label}</span><span className="block truncate text-xs text-fg-muted">{doc.filename}</span></span><Download className="size-4 text-fg-muted" /></a></li>
            ))}</ul>
          </Section>
        )}

        {d.project && (d.project.developer || d.project.rera_id || d.project.address) && (
          <Section title="About the project">
            <dl className="space-y-1.5 text-sm">{[["Developer", d.project.developer], ["RERA", d.project.rera_id], ["Address", d.project.address]].filter(([, v]) => v).map(([k, v]) => <div key={k} className="flex gap-3"><dt className="w-24 shrink-0 text-fg-muted">{k}</dt><dd>{v}</dd></div>)}</dl>
          </Section>
        )}

        <footer className="flex items-center justify-center gap-2 border-t border-border pt-6 text-xs text-fg-subtle"><LogoMark size={16} /> Shared by {rep}{d.workspace ? `, ${d.workspace}` : ""}</footer>
      </main>
      {hold && <HoldDialog flat={hold} token={token} repName={rep} onClose={() => setHold(null)} onDone={() => {
        setDone(hold.title); setD((x) => x && { ...x, flats: x.flats.map((f) => (f.id === hold.id ? { ...f, hold_requested: true } : f)) }); setHold(null);
      }} />}
    </div>
  );
}
