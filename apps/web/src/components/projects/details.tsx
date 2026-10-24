"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ChevronLeft, ChevronRight, Download, FileText, ImagePlus, LayoutTemplate, Pencil, Plus, Ruler, Sparkles, Upload, Video, X } from "lucide-react";
import * as React from "react";
import { ApiError, Button, Card, Dialog, DialogContent, DialogFooter, Field, Input, Skeleton, cn, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { BHK_OPTIONS } from "@/lib/realestate";
import type { Project, ProjectMedia, ProjectSize, StoredFile } from "@/lib/realestate";

export const MAX_PHOTOS = 10;
const MAX_MB = 25;
const AMENITY_IDEAS = ["Clubhouse", "Swimming pool", "Gym", "Kids' play area", "Landscaped garden", "Jogging track", "Power backup", "24x7 security", "Covered parking", "Lifts", "Indoor games", "Party hall"];

/** A file picked on this screen (not uploaded yet), or one the project already has. */
type Picked = { key: string; file?: File; stored?: StoredFile; preview?: string };
type SizeDraft = { key: string; label: string; area: string; plan: Picked | null };
export type DetailsDraft = { rera: string; video: string; amenities: string[]; sizes: SizeDraft[]; brochure: Picked | null; photos: Picked[] };

const uid = () => Math.random().toString(36).slice(2, 10);
const picked = (file: File): Picked => ({ key: uid(), file, preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined });
const stored = (f: StoredFile): Picked => ({ key: f.id, stored: f, preview: f.mime_type.startsWith("image/") ? f.url : undefined });
const nameOf = (p: Picked) => p.file?.name ?? p.stored?.filename ?? "";
export const emptyDetails = (): DetailsDraft => ({ rera: "", video: "", amenities: [], sizes: [], brochure: null, photos: [] });
const tooBig = (f: File) => f.size > MAX_MB * 1024 * 1024;

export function draftFrom(p: Project, m: ProjectMedia): DetailsDraft {
  const plans = new Map(m.floor_plans.map((f) => [f.id, f]));
  return {
    rera: p.rera_id ?? "", video: p.video_url ?? "", amenities: p.amenities ?? [], brochure: m.brochures.length ? stored(m.brochures[m.brochures.length - 1]) : null, photos: m.photos.map(stored),
    sizes: (p.sizes ?? []).map((z) => ({ key: uid(), label: z.label, area: z.area_sqft != null ? String(z.area_sqft) : "", plan: z.floor_plan_file_id && plans.get(z.floor_plan_file_id) ? stored(plans.get(z.floor_plan_file_id)!) : null })),
  };
}

/** RERA number, amenities, flat sizes with floor plans, brochure and society photos. Used when creating a project and when editing its details. */
export function DetailsFields({ v, onChange }: { v: DetailsDraft; onChange: (v: DetailsDraft) => void }) {
  const toast = useToast();
  const set = <K extends keyof DetailsDraft>(k: K, val: DetailsDraft[K]) => onChange({ ...v, [k]: val });
  const photoInput = React.useRef<HTMLInputElement>(null);
  const brochureInput = React.useRef<HTMLInputElement>(null);
  const [amenity, setAmenity] = React.useState("");

  const addAmenity = (raw: string) => { const a = raw.trim().replace(/,$/, "").slice(0, 60); if (a && !v.amenities.some((x) => x.toLowerCase() === a.toLowerCase())) set("amenities", [...v.amenities, a]); setAmenity(""); };
  const addPhotos = (files: FileList | null) => {
    if (!files) return;
    const imgs = Array.from(files).filter((f) => f.type.startsWith("image/") && !tooBig(f));
    if (imgs.length < files.length) toast.error("Some files were skipped", `Photos must be JPG, PNG or WebP images under ${MAX_MB} MB.`);
    const room = MAX_PHOTOS - v.photos.length;
    if (imgs.length > room) toast.error(`You can add up to ${MAX_PHOTOS} society photos`, room > 0 ? `Only the first ${room} were added.` : "Remove one to add another.");
    set("photos", [...v.photos, ...imgs.slice(0, Math.max(room, 0)).map(picked)]);
    if (photoInput.current) photoInput.current.value = "";
  };
  const pickBrochure = (f?: File) => {
    if (!f) return;
    if (f.type !== "application/pdf" || tooBig(f)) { toast.error("Upload the brochure as a PDF", `Up to ${MAX_MB} MB.`); return; }
    set("brochure", picked(f));
    if (brochureInput.current) brochureInput.current.value = "";
  };
  const setSize = (i: number, patch: Partial<SizeDraft>) => set("sizes", v.sizes.map((z, j) => (j === i ? { ...z, ...patch } : z)));
  const addSize = () => { const used = new Set(v.sizes.map((z) => z.label)); set("sizes", [...v.sizes, { key: uid(), label: BHK_OPTIONS.find((b) => !used.has(b)) ?? "", area: "", plan: null }]); };

  return (
    <div className="space-y-6">
      <section className="grid gap-3 sm:grid-cols-2">
        <Field label="RERA No." hint="Shown on the project page, comparisons and booking forms"><Input value={v.rera} onChange={(e) => set("rera", e.target.value)} maxLength={80} placeholder="RC/REP/HARERA/GGM/2024/12" /></Field>
        <Field label="Brochure" hint={`PDF, up to ${MAX_MB} MB`}>
          <div>
            {v.brochure ? (
              <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-sm shadow-xs">
                <FileText className="size-4 shrink-0 text-primary" /><span className="min-w-0 flex-1 truncate">{nameOf(v.brochure)}</span>
                <button type="button" onClick={() => brochureInput.current?.click()} className="text-xs font-medium text-primary hover:underline">Replace</button>
                <button type="button" aria-label="Remove brochure" onClick={() => set("brochure", null)} className="rounded p-0.5 text-fg-subtle hover:bg-surface-hover hover:text-fg"><X className="size-3.5" /></button>
              </div>
            ) : <Button type="button" variant="secondary" className="w-full justify-start" onClick={() => brochureInput.current?.click()}><Upload /> Upload brochure</Button>}
            <input ref={brochureInput} type="file" accept="application/pdf" hidden onChange={(e) => pickBrochure(e.target.files?.[0])} />
          </div>
        </Field>
        <div className="sm:col-span-2"><Field label="Video link" hint="A walkthrough or drone video on YouTube, Google Drive or Instagram"><Input icon={<Video />} type="url" inputMode="url" value={v.video} onChange={(e) => set("video", e.target.value)} onBlur={() => { const t = v.video.trim(); if (t && !/^https?:\/\//i.test(t)) set("video", `https://${t}`); }} maxLength={500} placeholder="https://youtu.be/…" /></Field></div>
      </section>

      <section>
        <div className="mb-2 flex items-end justify-between gap-3">
          <div><h3 className="text-sm font-medium">Society images</h3><p className="text-xs text-fg-muted">Elevation, entrance, clubhouse, pool. Up to {MAX_PHOTOS}; the first one is the cover.</p></div>
          <span className="shrink-0 text-xs tabular-nums text-fg-subtle">{v.photos.length}/{MAX_PHOTOS}</span>
        </div>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          {v.photos.map((p, i) => (
            <div key={p.key} className="group relative aspect-[4/3] overflow-hidden rounded-lg border border-border bg-bg-subtle">
              {p.preview && <img src={p.preview} alt={nameOf(p)} className="size-full object-cover" />}
              {i === 0 && <span className="absolute bottom-1 left-1 rounded-full bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur">Cover</span>}
              <button type="button" aria-label={`Remove ${nameOf(p)}`} onClick={() => set("photos", v.photos.filter((x) => x.key !== p.key))} className="absolute right-1 top-1 rounded-full bg-black/55 p-1 text-white backdrop-blur transition-opacity hover:bg-black/75 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"><X className="size-3" /></button>
            </div>
          ))}
          {v.photos.length < MAX_PHOTOS && (
            <button type="button" onClick={() => photoInput.current?.click()} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); addPhotos(e.dataTransfer.files); }}
              className="flex aspect-[4/3] flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-border text-xs text-fg-muted transition-colors hover:border-primary hover:bg-primary-soft/40 hover:text-primary">
              <ImagePlus className="size-5" />Add photos
            </button>
          )}
        </div>
        <input ref={photoInput} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={(e) => addPhotos(e.target.files)} />
      </section>

      <section>
        <h3 className="text-sm font-medium">Amenities</h3>
        <div className="mt-2 flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1.5 shadow-xs focus-within:border-primary focus-within:ring-4 focus-within:ring-[var(--ring)]">
          {v.amenities.map((a) => <span key={a} className="inline-flex items-center gap-1 rounded-full bg-primary-soft py-0.5 pl-2.5 pr-1 text-xs font-medium text-primary">{a}<button type="button" aria-label={`Remove ${a}`} onClick={() => set("amenities", v.amenities.filter((x) => x !== a))} className="rounded-full p-0.5 hover:bg-black/10"><X className="size-3" /></button></span>)}
          <input aria-label="Add an amenity" value={amenity} onChange={(e) => setAmenity(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addAmenity(amenity); } else if (e.key === "Backspace" && !amenity && v.amenities.length) set("amenities", v.amenities.slice(0, -1)); }} onBlur={() => amenity && addAmenity(amenity)}
            placeholder={v.amenities.length ? "Add more…" : "Type an amenity and press Enter"} className="min-w-[140px] flex-1 bg-transparent text-sm outline-none placeholder:text-fg-subtle" />
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {AMENITY_IDEAS.filter((a) => !v.amenities.includes(a)).slice(0, 8).map((a) => <button key={a} type="button" onClick={() => addAmenity(a)} className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-xs text-fg-muted transition-colors hover:border-border-strong hover:bg-surface-hover hover:text-fg"><Plus className="size-3" />{a}</button>)}
        </div>
      </section>

      <section>
        <div className="mb-2"><h3 className="text-sm font-medium">Sizes and floor plans</h3><p className="text-xs text-fg-muted">Each flat size on offer, with its floor plan (PDF or image).</p></div>
        <datalist id="size-options">{BHK_OPTIONS.map((b) => <option key={b} value={b} />)}</datalist>
        <div className="space-y-2">
          {v.sizes.map((z, i) => <SizeRow key={z.key} z={z} onChange={(patch) => setSize(i, patch)} onRemove={() => set("sizes", v.sizes.filter((x) => x.key !== z.key))} />)}
        </div>
        {v.sizes.length < 20 && <Button type="button" variant="secondary" size="sm" className="mt-2" onClick={addSize}><Plus /> Add a size</Button>}
      </section>
    </div>
  );
}

function SizeRow({ z, onChange, onRemove }: { z: SizeDraft; onChange: (patch: Partial<SizeDraft>) => void; onRemove: () => void }) {
  const toast = useToast();
  const input = React.useRef<HTMLInputElement>(null);
  const pick = (f?: File) => {
    if (!f) return;
    if (!["application/pdf", "image/jpeg", "image/png", "image/webp"].includes(f.type) || tooBig(f)) { toast.error("Upload the floor plan as a PDF or image", `Up to ${MAX_MB} MB.`); return; }
    onChange({ plan: picked(f) });
    if (input.current) input.current.value = "";
  };
  return (
    <div className="grid grid-cols-[1fr_auto] gap-2 rounded-xl border border-border bg-surface-2/60 p-2 sm:grid-cols-[minmax(0,1fr)_120px_minmax(0,1.2fr)_auto] sm:items-center">
      <Input aria-label="Size" list="size-options" value={z.label} onChange={(e) => onChange({ label: e.target.value })} maxLength={40} placeholder="3 BHK" />
      <button type="button" aria-label={`Remove ${z.label || "size"}`} onClick={onRemove} className="grid size-9 place-items-center rounded-md text-fg-subtle hover:bg-surface-hover hover:text-fg sm:order-last"><X className="size-4" /></button>
      <div className="relative"><Input aria-label="Area in sq ft" type="number" min={0} value={z.area} onChange={(e) => onChange({ area: e.target.value })} placeholder="1800" className="pr-12" /><span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-fg-subtle">sq ft</span></div>
      <div className="col-span-2 sm:col-span-1">
        {z.plan ? (
          <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-sm shadow-xs">
            {z.plan.preview ? <img src={z.plan.preview} alt="" className="size-6 rounded object-cover" /> : <LayoutTemplate className="size-4 shrink-0 text-primary" />}
            <span className="min-w-0 flex-1 truncate text-[13px]">{nameOf(z.plan)}</span>
            <button type="button" aria-label="Remove floor plan" onClick={() => onChange({ plan: null })} className="rounded p-0.5 text-fg-subtle hover:bg-surface-hover hover:text-fg"><X className="size-3.5" /></button>
          </div>
        ) : <Button type="button" variant="ghost" className="w-full justify-start border border-dashed border-border" onClick={() => input.current?.click()}><Upload /> Floor plan</Button>}
        <input ref={input} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" hidden onChange={(e) => pick(e.target.files?.[0])} />
      </div>
    </div>
  );
}

/** Uploads new files, removes dropped ones and saves RERA, amenities and sizes. Returns the names of files that couldn't be uploaded. */
export async function saveDetails(projectId: string, v: DetailsDraft, before?: DetailsDraft, onProgress?: (done: number, total: number) => void): Promise<string[]> {
  const failed: string[] = [];
  const keep = new Set([v.brochure, ...v.photos, ...v.sizes.map((z) => z.plan)].filter(Boolean).map((p) => p!.stored?.id).filter(Boolean));
  const dropped = before ? [before.brochure, ...before.photos, ...before.sizes.map((z) => z.plan)].filter((p) => p?.stored && !keep.has(p.stored.id)) : [];
  // Delete first so a full set of photos can be swapped for new ones
  await Promise.all(dropped.map((p) => api.delete(`/api/v1/files/${p!.stored!.id}`).catch(() => undefined)));

  const uploads: [Picked, string][] = [...(v.brochure?.file ? [[v.brochure, "brochure"] as [Picked, string]] : []), ...v.photos.filter((p) => p.file).map((p) => [p, "photo"] as [Picked, string]),
    ...v.sizes.filter((z) => z.plan?.file).map((z) => [z.plan!, "floor_plan"] as [Picked, string])];
  const ids = new Map<string, string>();
  let done = 0;
  onProgress?.(0, uploads.length);
  for (const [p, kind] of uploads) {
    const fd = new FormData(); fd.append("file", p.file!); fd.append("project_id", projectId); fd.append("doc_kind", kind);
    try { ids.set(p.key, (await api.upload<{ id: string }>("/api/v1/files", fd)).id); } catch (e) { failed.push(e instanceof ApiError && e.message ? `${p.file!.name} (${e.message})` : p.file!.name); }
    onProgress?.(++done, uploads.length);
  }
  const sizes: ProjectSize[] = v.sizes.filter((z) => z.label.trim()).map((z) => ({ label: z.label.trim(), area_sqft: z.area ? Number(z.area) : null, floor_plan_file_id: z.plan ? (z.plan.stored?.id ?? ids.get(z.plan.key) ?? null) : null }));
  await api.patch(`/api/v1/projects/${projectId}`, { rera_id: v.rera.trim() || null, video_url: v.video.trim() || null, amenities: v.amenities, sizes });
  return failed;
}

export const useProjectMedia = (projectId?: string) =>
  useQuery({ queryKey: ["project", projectId, "media"], enabled: !!projectId, staleTime: 30 * 60_000, queryFn: () => api.get<ProjectMedia>(`/api/v1/projects/${projectId}/media`) });

export function EditDetailsDialog({ open, onOpenChange, project }: { open: boolean; onOpenChange: (o: boolean) => void; project: Project }) {
  const qc = useQueryClient(); const toast = useToast();
  const media = useProjectMedia(open ? project.id : undefined);
  const [v, setV] = React.useState<DetailsDraft | null>(null);
  const [before, setBefore] = React.useState<DetailsDraft | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  React.useEffect(() => { if (!open) { setV(null); setBefore(null); } else if (media.data && !v) { const d = draftFrom(project, media.data); setV(d); setBefore(d); } }, [open, media.data, project, v]);
  const save = async () => {
    if (!v) return;
    setBusy("Saving…");
    try {
      const failed = await saveDetails(project.id, v, before ?? undefined, (d, t) => t && setBusy(`Uploading ${Math.min(d + 1, t)} of ${t}…`));
      qc.invalidateQueries({ queryKey: ["project", project.id] }); qc.invalidateQueries({ queryKey: ["projects"] });
      if (failed.length) toast.error("Some files couldn't be uploaded", failed.join(", ")); else toast.success("Project details saved");
      onOpenChange(false);
    } catch (e) { toast.error(e instanceof ApiError ? e.message : "Couldn't save the details"); } finally { setBusy(null); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent size="lg" title="Project details" description="What buyers ask about first: RERA, sizes, floor plans, photos, a video and the brochure.">
        {!v ? <div className="space-y-3"><Skeleton className="h-9" /><Skeleton className="h-28" /><Skeleton className="h-20" /></div> : <DetailsFields v={v} onChange={setV} />}
        <DialogFooter><Button variant="ghost" disabled={!!busy} onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={!!busy} disabled={!v} onClick={save}>{busy ?? "Save details"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const fmtArea = (n: number | null) => (n ? `${Math.round(n).toLocaleString("en-IN")} sq ft` : null);

/** The project page's details card: photos, RERA, brochure, amenities and sizes with their floor plans. */
export function ProjectDetailsCard({ project, canEdit, onEdit }: { project: Project; canEdit: boolean; onEdit: () => void }) {
  const media = useProjectMedia(project.id);
  const [view, setView] = React.useState<{ items: StoredFile[]; i: number } | null>(null);
  const m = media.data;
  const photos = m?.photos ?? [];
  const brochure = m?.brochures[m.brochures.length - 1];
  const plans = new Map((m?.floor_plans ?? []).map((f) => [f.id, f]));
  const sizes = project.sizes ?? [];
  const empty = !project.rera_id && !project.video_url && !project.amenities?.length && !sizes.length && !photos.length && !brochure;
  const openFile = (f: StoredFile, set: StoredFile[] = [f]) => { if (f.mime_type.startsWith("image/")) setView({ items: set, i: Math.max(set.indexOf(f), 0) }); else window.open(f.url, "_blank", "noopener"); };

  if (media.isLoading) return <Skeleton className="mb-5 h-40" />;
  if (empty) {
    if (!canEdit) return null;
    return (
      <Card className="mb-5 flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg bg-primary-soft text-primary"><Sparkles className="size-4" /></span><div><p className="text-sm font-medium">Add the details buyers ask for</p><p className="text-xs text-fg-muted">Brochure, society photos, a video link, RERA No., amenities, sizes and floor plans.</p></div></div>
        <Button variant="secondary" onClick={onEdit}><Plus /> Add details</Button>
      </Card>
    );
  }
  const planImages = sizes.map((z) => (z.floor_plan_file_id ? plans.get(z.floor_plan_file_id) : undefined)).filter((f): f is StoredFile => !!f && f.mime_type.startsWith("image/"));
  return (
    <Card className="mb-5 overflow-hidden">
      <div className={cn("grid", photos.length > 0 && "md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]")}>
        {photos.length > 0 && (
          <div className="grid h-44 grid-cols-4 grid-rows-2 gap-1 p-1 sm:h-64">
            {photos.slice(0, 5).map((f, i) => (
              <button key={f.id} type="button" onClick={() => openFile(f, photos)} aria-label={`Open photo ${i + 1} of ${photos.length}`}
                className={cn("group relative overflow-hidden rounded-md bg-bg-subtle", i === 0 ? (photos.length === 1 ? "col-span-4 row-span-2" : "col-span-2 row-span-2") : photos.length === 2 ? "col-span-2 row-span-2" : photos.length === 3 ? "col-span-2" : "")}>
                <img src={f.url} alt="" className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.04]" />
                {i === 4 && photos.length > 5 && <span className="absolute inset-0 grid place-items-center bg-black/45 text-sm font-semibold text-white">+{photos.length - 5} more</span>}
              </button>
            ))}
          </div>
        )}
        <div className="min-w-0 space-y-4 p-5">
          <div className="flex items-start gap-2">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
              {project.rera_id && <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-medium"><BadgeCheck className="size-3.5 text-success" />RERA {project.rera_id}</span>}
              {brochure && <Button variant="soft" size="sm" onClick={() => openFile(brochure)}><Download /> Brochure</Button>}
              {project.video_url && <Button asChild variant="soft" size="sm"><a href={project.video_url} target="_blank" rel="noopener noreferrer"><Video /> Watch video</a></Button>}
            </div>
            {canEdit && <Button variant="ghost" size="sm" className="shrink-0" onClick={onEdit} aria-label="Edit details"><Pencil /> <span className="hidden sm:inline">Edit details</span></Button>}
          </div>
          {sizes.length > 0 && (
            <div>
              <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">Sizes</h2>
              <ul className="grid gap-2 sm:grid-cols-2">
                {sizes.map((z, i) => { const plan = z.floor_plan_file_id ? plans.get(z.floor_plan_file_id) : undefined; return (
                  <li key={`${z.label}-${i}`} className="flex items-center gap-3 rounded-xl border border-border bg-surface-2/60 px-3 py-2">
                    <Ruler className="size-4 shrink-0 text-fg-subtle" />
                    <div className="min-w-0 flex-1"><p className="text-sm font-semibold leading-snug">{z.label}</p>{fmtArea(z.area_sqft) && <p className="text-xs tabular-nums text-fg-muted">{fmtArea(z.area_sqft)}</p>}</div>
                    {plan && <Button variant="secondary" size="xs" onClick={() => openFile(plan, plan.mime_type.startsWith("image/") ? planImages : [plan])}><LayoutTemplate /> Floor plan</Button>}
                  </li>); })}
              </ul>
            </div>
          )}
          {project.amenities?.length > 0 && (
            <div>
              <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">Amenities</h2>
              <div className="flex flex-wrap gap-1.5">{project.amenities.map((a) => <span key={a} className="rounded-full bg-primary-soft px-2.5 py-0.5 text-xs font-medium text-primary">{a}</span>)}</div>
            </div>
          )}
        </div>
      </div>
      <Lightbox view={view} onClose={() => setView(null)} onMove={(i) => setView((x) => (x ? { ...x, i } : x))} />
    </Card>
  );
}

function Lightbox({ view, onClose, onMove }: { view: { items: StoredFile[]; i: number } | null; onClose: () => void; onMove: (i: number) => void }) {
  const n = view?.items.length ?? 0;
  const f = view?.items[view.i];
  const go = React.useCallback((d: number) => view && onMove((view.i + d + n) % n), [view, n, onMove]);
  React.useEffect(() => {
    if (!view || n < 2) return;
    const k = (e: KeyboardEvent) => { if (e.key === "ArrowRight") go(1); if (e.key === "ArrowLeft") go(-1); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [view, n, go]);
  return (
    <Dialog open={!!view} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="xl" title={f?.doc_kind === "floor_plan" ? "Floor plan" : "Society photos"} description={n > 1 ? `${(view?.i ?? 0) + 1} of ${n}` : undefined}>
        {f && (
          <div className="relative">
            <img src={f.url} alt={f.filename} className="mx-auto max-h-[64vh] w-auto rounded-lg object-contain" />
            {n > 1 && <>
              <Button variant="secondary" size="icon" aria-label="Previous" onClick={() => go(-1)} className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full"><ChevronLeft /></Button>
              <Button variant="secondary" size="icon" aria-label="Next" onClick={() => go(1)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full"><ChevronRight /></Button>
            </>}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
