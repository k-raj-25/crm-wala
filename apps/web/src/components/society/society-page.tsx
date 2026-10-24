"use client";
import {
  ArrowUpDown, BadgeCheck, Baby, Building2, Car, ChevronLeft, ChevronRight, Download, Dumbbell, ExternalLink, FileText, Footprints, Gamepad2, Images, LayoutTemplate,
  MapPin, MessageCircle, PartyPopper, Phone, PlayCircle, Ruler, ShieldCheck, Sparkles, Trees, Waves, Zap,
} from "lucide-react";
import * as React from "react";
import { Avatar, Button, Dialog, DialogContent, cn } from "@crm/ui";

export type PublicFile = { id: string; filename: string; mime_type: string; size_bytes: number; url: string; download_url: string };
export type SocietyPageData = {
  society: {
    name: string; developer: string | null; kind: string; stage: string; stage_key: string; possession: string | null; location: string | null; city: string | null;
    address: string | null; rera_id: string | null; description: string | null; amenities: string[]; video_url: string | null; towers: number; total_flats: number;
    available: number; starting_price: string | null; price_range: string | null; avg_rate: string | null;
  };
  sizes: { label: string; area: string | null; from_price: string | null; available: number; floor_plan: PublicFile | null }[];
  photos: PublicFile[];
  brochure: PublicFile | null;
  floor_plans: PublicFile[];
  contact: { name: string; avatar_url: string | null; phone: string | null; whatsapp: string | null; company_number: boolean } | null;
  company: { name: string; logo_url: string | null; website: string | null } | null;
  shared_with: string | null;
};

type View = { title: string; items: PublicFile[]; i: number };
const isImage = (f: PublicFile) => f.mime_type.startsWith("image/");
const mb = (b: number) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const AMENITY_ICONS: [RegExp, React.ElementType][] = [
  [/gym|fitness/i, Dumbbell], [/pool|swim/i, Waves], [/garden|park|landscap|green/i, Trees], [/kid|child|play area|creche/i, Baby], [/jog|walk|track|cycl/i, Footprints],
  [/power|backup|generator/i, Zap], [/secur|cctv|gated|guard/i, ShieldCheck], [/park(ing)?\b|car/i, Car], [/lift|elevator/i, ArrowUpDown], [/game|sport|court|tennis|badminton|squash/i, Gamepad2],
  [/party|banquet|hall|community/i, PartyPopper], [/club/i, Building2],
];
const amenityIcon = (a: string) => AMENITY_ICONS.find(([re]) => re.test(a))?.[1] ?? Sparkles;

/** A YouTube link becomes an embedded player; any other video link stays a button. */
function youtubeEmbed(url: string | null): string | null {
  if (!url) return null;
  const m = /(?:youtu\.be\/|youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/|live\/))([\w-]{11})/.exec(url);
  return m ? `https://www.youtube-nocookie.com/embed/${m[1]}` : null;
}

export function SocietyPage({ data, token }: { data: SocietyPageData; token: string }) {
  const { society: s, sizes, photos, brochure, contact, company } = data;
  const [view, setView] = React.useState<View | null>(null);
  const embed = youtubeEmbed(s.video_url);
  const plans = sizes.map((z) => z.floor_plan).filter((f): f is PublicFile => !!f);
  const planImages = plans.filter(isImage);
  const openPlan = (f: PublicFile) => (isImage(f) ? setView({ title: "Floor plans", items: planImages, i: Math.max(planImages.indexOf(f), 0) }) : window.open(f.url, "_blank", "noopener"));
  const openPhoto = (i: number) => setView({ title: "Photos", items: photos, i });
  const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent([s.name, s.address || s.location].filter(Boolean).join(", "))}`;
  const waText = `Hi${contact ? ` ${contact.name.split(" ")[0]}` : ""}, I'm looking at ${s.name} and would like to know more.`;
  const call = contact?.phone ? `tel:${contact.phone}` : null;
  const whatsapp = contact?.whatsapp ? `https://wa.me/${contact.whatsapp}?text=${encodeURIComponent(waText)}` : null;

  // tell the employee their client is looking (once per visit; link-preview bots never run this)
  React.useEffect(() => {
    const key = `society-opened:${token}`;
    try { if (sessionStorage.getItem(key)) return; sessionStorage.setItem(key, "1"); } catch { /* private mode: still note it */ }
    fetch(`/api/v1/public/societies/${token}/opened`, { method: "POST", keepalive: true }).catch(() => {});
  }, [token]);

  const facts = [
    s.starting_price && { label: "Starting from", value: s.starting_price },
    s.price_range && s.price_range !== s.starting_price && { label: "Price range", value: s.price_range },
    s.avg_rate && { label: "Avg. per sq ft", value: s.avg_rate },
    { label: "Status", value: s.possession && s.stage_key !== "ready" ? `Possession ${s.possession}` : s.stage },
    s.towers > 0 && { label: s.towers === 1 ? "Tower" : "Towers", value: String(s.towers) },
    s.total_flats > 0 && { label: "Available now", value: `${s.available} of ${s.total_flats}` },
    sizes.length > 0 && { label: "Layouts", value: sizes.map((z) => z.label).slice(0, 3).join(", ") + (sizes.length > 3 ? ` +${sizes.length - 3}` : "") },
    s.developer && { label: "Developer", value: s.developer },
  ].filter(Boolean) as { label: string; value: string }[];

  return (
    <div className="min-h-dvh pb-28 text-fg sm:pb-12">
      {/* top bar: who's sharing */}
      <header className="glass sticky top-0 z-30 border-b border-border bg-surface/80">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-2.5">
            {company?.logo_url ? <img src={company.logo_url} alt="" className="size-8 rounded-lg object-contain" />
              : <span className="grid size-8 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-fg">{(company?.name ?? s.name).slice(0, 1).toUpperCase()}</span>}
            <span className="truncate text-sm font-semibold tracking-tight">{company?.name ?? s.name}</span>
          </div>
          <div className="hidden items-center gap-2 sm:flex">
            {call && <Button asChild variant="secondary" size="sm"><a href={call}><Phone /> Call</a></Button>}
            {whatsapp && <Button asChild size="sm"><a href={whatsapp} target="_blank" rel="noopener noreferrer"><MessageCircle /> WhatsApp</a></Button>}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 sm:px-6">
        {/* hero */}
        <section className="pt-4 sm:pt-8">
          {data.shared_with && <p className="mb-3 text-sm text-fg-muted">Hi {data.shared_with}, here is everything about this society{contact ? `, shared by ${contact.name}` : ""}.</p>}
          <Gallery photos={photos} name={s.name} onOpen={openPhoto} />
          <div className="mt-5 flex flex-col gap-4 sm:mt-7 lg:flex-row lg:items-end lg:justify-between">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", s.stage_key === "ready" ? "bg-success-soft text-success" : s.stage_key === "under_construction" ? "bg-warning-soft text-warning" : "bg-info-soft text-info")}>{s.stage}</span>
                <span className="rounded-full bg-bg-subtle px-2.5 py-1 text-xs font-medium text-fg-muted">{s.kind}</span>
                {s.rera_id && <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-medium"><BadgeCheck className="size-3.5 text-success" />RERA {s.rera_id}</span>}
              </div>
              <h1 className="text-[28px] font-semibold leading-tight tracking-tight sm:text-4xl">{s.name}</h1>
              <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px] text-fg-muted">
                {s.location && <a href={maps} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-fg"><MapPin className="size-4" />{s.location}</a>}
                {s.developer && <span>by {s.developer}</span>}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {brochure && <Button asChild size="lg"><a href={brochure.download_url} download={brochure.filename}><Download /> Download brochure</a></Button>}
              {s.video_url && !embed && <Button asChild variant="secondary" size="lg"><a href={s.video_url} target="_blank" rel="noopener noreferrer"><PlayCircle /> Watch video</a></Button>}
            </div>
          </div>
        </section>

        {/* key facts */}
        {facts.length > 0 && (
          <section aria-label="Key facts" className="glass mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border shadow-sm sm:grid-cols-4">
            {facts.map((f) => (
              <div key={f.label} className="bg-surface-solid/90 px-4 py-3.5 sm:px-5 sm:py-4">
                <p className="text-xs font-medium uppercase tracking-wide text-fg-subtle">{f.label}</p>
                <p className="mt-1 text-[15px] font-semibold leading-snug tabular-nums [overflow-wrap:anywhere] sm:text-base">{f.value}</p>
              </div>
            ))}
          </section>
        )}

        <div className="mt-8 grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-10">
            {/* layouts + floor plans */}
            {sizes.length > 0 && (
              <Section title="Layouts & floor plans" icon={<Ruler />} note={plans.length > 1 ? <DownloadAll files={plans} /> : undefined}>
                <ul className="grid gap-3 sm:grid-cols-2">
                  {sizes.map((z, i) => (
                    <li key={`${z.label}-${i}`} className="glass flex flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
                      {z.floor_plan && isImage(z.floor_plan) && (
                        <button type="button" onClick={() => openPlan(z.floor_plan!)} className="group relative block aspect-[16/10] overflow-hidden bg-white" aria-label={`View the ${z.label} floor plan`}>
                          <img src={z.floor_plan.url} alt={`${z.label} floor plan`} loading="lazy" className="size-full object-contain p-2 transition-transform duration-500 group-hover:scale-[1.03]" />
                        </button>
                      )}
                      <div className="flex flex-1 flex-col gap-3 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-lg font-semibold leading-snug">{z.label}</p>
                            {z.area && <p className="text-sm tabular-nums text-fg-muted">{z.area}</p>}
                          </div>
                          {z.from_price && <p className="shrink-0 text-right text-sm"><span className="block text-xs text-fg-subtle">from</span><span className="font-semibold">{z.from_price}</span></p>}
                        </div>
                        <p className={cn("text-xs font-medium", z.available ? "text-success" : "text-fg-subtle")}>{z.available ? `${z.available} available right now` : "Ask about availability"}</p>
                        {z.floor_plan && (
                          <div className="mt-auto flex gap-2">
                            <Button variant="secondary" size="sm" className="flex-1" onClick={() => openPlan(z.floor_plan!)}><LayoutTemplate /> View plan</Button>
                            <Button asChild variant="soft" size="sm" className="flex-1"><a href={z.floor_plan.download_url} download={z.floor_plan.filename}><Download /> Download</a></Button>
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {embed && (
              <Section title="Video walkthrough" icon={<PlayCircle />}>
                <div className="glass overflow-hidden rounded-2xl border border-border shadow-sm">
                  <iframe src={embed} title={`${s.name} video`} className="aspect-video w-full" loading="lazy" allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen" allowFullScreen />
                </div>
              </Section>
            )}

            {s.amenities.length > 0 && (
              <Section title="Amenities" icon={<Sparkles />}>
                <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {s.amenities.map((a) => { const Icon = amenityIcon(a); return (
                    <li key={a} className="glass flex items-center gap-3 rounded-xl border border-border bg-surface px-3 py-2.5 text-sm font-medium shadow-xs">
                      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary"><Icon className="size-4" /></span><span className="min-w-0 break-words">{a}</span>
                    </li>); })}
                </ul>
              </Section>
            )}

            {photos.length > 1 && (
              <Section title="Photos" icon={<Images />}>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {photos.map((f, i) => (
                    <button key={f.id} type="button" onClick={() => openPhoto(i)} className="group relative aspect-[4/3] overflow-hidden rounded-xl bg-bg-subtle" aria-label={`Open photo ${i + 1} of ${photos.length}`}>
                      <img src={f.url} alt="" loading="lazy" className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.04]" />
                    </button>
                  ))}
                </div>
              </Section>
            )}

            {(s.description || s.address) && (
              <Section title="About the society" icon={<Building2 />}>
                {s.description && <p className="whitespace-pre-line text-[15px] leading-relaxed text-fg-muted">{s.description}</p>}
                {s.address && <p className="mt-3 flex items-start gap-2 text-sm"><MapPin className="mt-0.5 size-4 shrink-0 text-fg-subtle" /><span>{s.address} · <a href={maps} target="_blank" rel="noopener noreferrer" className="font-medium text-primary hover:underline">Open in Maps</a></span></p>}
              </Section>
            )}
          </div>

          {/* side: advisor + downloads */}
          <aside className="space-y-4 lg:sticky lg:top-20">
            {contact && (
              <div className="glass rounded-2xl border border-border bg-surface p-5 shadow-md">
                <p className="text-xs font-medium uppercase tracking-wide text-fg-subtle">Your property advisor</p>
                <div className="mt-3 flex items-center gap-3">
                  <Avatar name={contact.name} src={contact.avatar_url ?? undefined} size={44} />
                  <div className="min-w-0"><p className="truncate font-semibold">{contact.name}</p>{company && <p className="truncate text-sm text-fg-muted">{company.name}</p>}</div>
                </div>
                {(call || whatsapp) && (
                  <div className="mt-4 grid gap-2">
                    {whatsapp && <Button asChild><a href={whatsapp} target="_blank" rel="noopener noreferrer"><MessageCircle /> Chat on WhatsApp</a></Button>}
                    {call && <Button asChild variant="secondary"><a href={call}><Phone /> Call {contact.company_number ? "us" : contact.name.split(" ")[0]}</a></Button>}
                  </div>
                )}
                <p className="mt-3 text-xs text-fg-subtle">Ask for a site visit, today's prices or a flat on a floor you like.</p>
              </div>
            )}
            {(brochure || plans.length > 0) && (
              <div className="glass rounded-2xl border border-border bg-surface p-5 shadow-sm">
                <p className="mb-3 text-xs font-medium uppercase tracking-wide text-fg-subtle">Downloads</p>
                <ul className="space-y-1.5">
                  {brochure && <FileRow file={brochure} label="Brochure" />}
                  {sizes.filter((z) => z.floor_plan).map((z, i) => <FileRow key={`${z.label}-${i}`} file={z.floor_plan!} label={`${z.label} floor plan`} />)}
                </ul>
              </div>
            )}
          </aside>
        </div>

        <footer className="mt-14 border-t border-border py-6 text-center text-xs text-fg-subtle">
          Prices and availability change often. Please confirm with your advisor before booking.{s.rera_id && ` RERA ${s.rera_id}.`}
        </footer>
      </main>

      {/* phone: actions stay in reach */}
      {(call || whatsapp || brochure) && (
        <div className="glass fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/85 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:hidden">
          <div className="flex gap-2">
            {brochure && <Button asChild variant="secondary" size="lg" className={cn(call || whatsapp ? "px-4" : "flex-1")}><a href={brochure.download_url} download={brochure.filename} aria-label="Download brochure"><Download />{!(call || whatsapp) && " Brochure"}</a></Button>}
            {call && <Button asChild variant="secondary" size="lg" className="flex-1"><a href={call}><Phone /> Call</a></Button>}
            {whatsapp && <Button asChild size="lg" className="flex-1"><a href={whatsapp} target="_blank" rel="noopener noreferrer"><MessageCircle /> WhatsApp</a></Button>}
          </div>
        </div>
      )}

      <Lightbox view={view} onClose={() => setView(null)} onMove={(i) => setView((x) => (x ? { ...x, i } : x))} />
    </div>
  );
}

function Section({ title, icon, note, children }: { title: string; icon: React.ReactNode; note?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight [&_svg]:size-5 [&_svg]:text-fg-subtle">{icon}{title}</h2>
        {note}
      </div>
      {children}
    </section>
  );
}

function FileRow({ file, label }: { file: PublicFile; label: string }) {
  return (
    <li>
      <a href={file.download_url} download={file.filename} className="group flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-surface-hover">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary">{isImage(file) ? <LayoutTemplate className="size-4" /> : <FileText className="size-4" />}</span>
        <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{label}</span><span className="block text-xs text-fg-subtle">{file.mime_type === "application/pdf" ? "PDF" : file.mime_type.split("/")[1]?.toUpperCase()} · {mb(file.size_bytes)}</span></span>
        <Download className="size-4 text-fg-subtle transition-colors group-hover:text-fg" />
      </a>
    </li>
  );
}

/** Downloads each floor plan in turn (browsers allow a short burst of downloads from one click). */
function DownloadAll({ files }: { files: PublicFile[] }) {
  const go = () => files.forEach((f, i) => setTimeout(() => {
    const a = document.createElement("a"); a.href = f.download_url; a.download = f.filename; document.body.appendChild(a); a.click(); a.remove();
  }, i * 400));
  return <Button variant="ghost" size="sm" onClick={go}><Download /> All plans</Button>;
}

function Gallery({ photos, name, onOpen }: { photos: PublicFile[]; name: string; onOpen: (i: number) => void }) {
  const strip = React.useRef<HTMLDivElement>(null);
  const [at, setAt] = React.useState(0);
  if (!photos.length) {
    return (
      <div className="relative grid h-44 place-items-center overflow-hidden rounded-3xl border border-border bg-gradient-to-br from-primary-soft via-surface to-surface-2 sm:h-64">
        <Building2 className="size-16 text-fg-subtle/60" strokeWidth={1.2} />
        <span className="sr-only">{name}</span>
      </div>
    );
  }
  const shown = photos.slice(0, 5);
  return (
    <>
      {/* phone: swipe through */}
      <div className="relative -mx-4 sm:hidden">
        <div ref={strip} onScroll={(e) => setAt(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}
          className="flex snap-x snap-mandatory overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {photos.map((f, i) => (
            <button key={f.id} type="button" onClick={() => onOpen(i)} className="aspect-[4/3] w-full shrink-0 snap-center px-4" aria-label={`Open photo ${i + 1} of ${photos.length}`}>
              <img src={f.url} alt={i === 0 ? name : ""} className="size-full rounded-2xl object-cover" loading={i === 0 ? "eager" : "lazy"} />
            </button>
          ))}
        </div>
        {photos.length > 1 && <span className="pointer-events-none absolute bottom-3 right-7 rounded-full bg-black/55 px-2.5 py-1 text-xs font-medium text-white backdrop-blur">{at + 1} / {photos.length}</span>}
      </div>
      {/* larger screens: a mosaic */}
      <div className="hidden h-[420px] grid-cols-4 grid-rows-2 gap-2 overflow-hidden rounded-3xl sm:grid">
        {shown.map((f, i) => (
          <button key={f.id} type="button" onClick={() => onOpen(i)} aria-label={`Open photo ${i + 1} of ${photos.length}`}
            className={cn("group relative overflow-hidden bg-bg-subtle",
              i === 0 ? (shown.length === 1 ? "col-span-4 row-span-2" : "col-span-2 row-span-2") : shown.length === 2 ? "col-span-2 row-span-2" : shown.length === 3 || (shown.length === 4 && i === 3) ? "col-span-2" : "")}>
            <img src={f.url} alt={i === 0 ? name : ""} className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.03]" />
            {i === shown.length - 1 && photos.length > shown.length && <span className="absolute inset-0 grid place-items-center bg-black/45 text-sm font-semibold text-white">+{photos.length - shown.length} more</span>}
          </button>
        ))}
      </div>
    </>
  );
}

function Lightbox({ view, onClose, onMove }: { view: View | null; onClose: () => void; onMove: (i: number) => void }) {
  const n = view?.items.length ?? 0;
  const f = view?.items[view.i];
  const go = React.useCallback((d: number) => view && onMove((view.i + d + n) % n), [view, n, onMove]);
  const touch = React.useRef<number | null>(null);
  React.useEffect(() => {
    if (!view || n < 2) return;
    const k = (e: KeyboardEvent) => { if (e.key === "ArrowRight") go(1); if (e.key === "ArrowLeft") go(-1); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [view, n, go]);
  return (
    <Dialog open={!!view} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="xl" title={view?.title ?? "Photos"} description={n > 1 ? `${(view?.i ?? 0) + 1} of ${n}` : undefined}>
        {f && (
          <div className="relative" onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
            onTouchEnd={(e) => { if (touch.current == null) return; const dx = e.changedTouches[0].clientX - touch.current; touch.current = null; if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1); }}>
            <img src={f.url} alt={f.filename} className="mx-auto max-h-[68vh] w-auto rounded-lg object-contain" />
            {n > 1 && <>
              <Button variant="secondary" size="icon" aria-label="Previous" onClick={() => go(-1)} className="absolute left-2 top-1/2 -translate-y-1/2"><ChevronLeft /></Button>
              <Button variant="secondary" size="icon" aria-label="Next" onClick={() => go(1)} className="absolute right-2 top-1/2 -translate-y-1/2"><ChevronRight /></Button>
            </>}
            <div className="mt-3 flex justify-center gap-2">
              <Button asChild variant="soft" size="sm"><a href={f.download_url} download={f.filename}><Download /> Download</a></Button>
              <Button asChild variant="ghost" size="sm"><a href={f.url} target="_blank" rel="noopener noreferrer"><ExternalLink /> Full size</a></Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
