"use client";
import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Building2, Check, Download, FileText, ImageOff, LayoutTemplate, Minus, Plus, Scale, Search, Share2, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { ApiError, Button, Card, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Input, Skeleton, Spinner, Switch, cn, formatMoneyCompact, useDebounce, useToast } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { navigate } from "@/components/shell/pending-nav";
import { api } from "@/lib/api";
import { DEFAULT_PHOTOS, MAX_SOCIETIES, societyCompare, useSocietyCompare } from "@/lib/compare";
import type { CompareSociety } from "@/lib/compare";
import { where } from "@/lib/realestate";
import type { Project, ProjectMedia, StoredFile } from "@/lib/realestate";
import { CompareTabs } from "./compare-tabs";
import { ShareComparison, comparisonPdf } from "./share-dialog";

type SocietySize = { label: string; area_sqft: number | null; has_floor_plan: boolean };
export type SocietyComparison = {
  societies: { id: string; name: string; subtitle: string; sizes: SocietySize[]; chosen_sizes: string[] }[];
  rows: { group: "overview" | "layouts" | "amenities"; key: string; label: string; values: string[]; best: number[]; same: boolean }[];
};

const GROUPS: Record<string, string> = { layouts: "Layouts", amenities: "Amenities" };
const mb = (n: number) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const toastFull = (toast: ReturnType<typeof useToast>) => toast.error(`You can compare up to ${MAX_SOCIETIES} societies`, "Remove one to add another.");

/** The photos that go in the PDF: the ones the user ticked (still on the project), or the first few until they choose. */
const photoIds = (s: CompareSociety, m?: ProjectMedia) => {
  const all = (m?.photos ?? []).map((f) => f.id);
  return s.photos ? s.photos.filter((id) => all.includes(id)) : all.slice(0, DEFAULT_PHOTOS);
};

export function SocietyComparePage({ openPicker }: { openPicker?: boolean }) {
  const list = useSocietyCompare();
  const toast = useToast();
  const [picker, setPicker] = React.useState(false);
  const [share, setShare] = React.useState(false);
  const [diffOnly, setDiffOnly] = React.useState(false);
  const [downloading, setDownloading] = React.useState(false);
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  React.useEffect(() => { if (mounted && openPicker && !list.length) setPicker(true); }, [mounted]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = list.map((s) => ({ project_id: s.id, sizes: s.sizes }));
  const q = useQuery({ queryKey: ["society-comparison", pick], enabled: list.length > 0, placeholderData: keepPreviousData, retry: false,
    queryFn: () => api.post<SocietyComparison>("/api/v1/comparisons/societies/preview", { societies: pick }) });
  const media = useQueries({ queries: list.map((s) => ({ queryKey: ["project", s.id, "media"], staleTime: 30 * 60_000, queryFn: () => api.get<ProjectMedia>(`/api/v1/projects/${s.id}/media`) })) });
  const mediaOf = (i: number) => media[i]?.data;

  React.useEffect(() => {
    const e = q.error;
    const gone = e instanceof ApiError && e.status === 404 ? (e.details as unknown as { missing?: string[] } | undefined)?.missing : undefined;
    if (Array.isArray(gone)) {
      const missing = new Set(gone);
      societyCompare.set(list.filter((s) => !missing.has(s.id)));
      toast.toast({ tone: "info", title: "A society in your list no longer exists, so we removed it" });
    }
  }, [q.error]); // eslint-disable-line react-hooks/exhaustive-deps

  const body = { societies: list.map((s, i) => ({ project_id: s.id, sizes: s.sizes, photo_ids: photoIds(s, mediaOf(i)), brochure: s.brochure && !!mediaOf(i)?.brochures.length })) };
  const download = async () => {
    setDownloading(true);
    try {
      const f = await comparisonPdf("societies", body);
      const url = URL.createObjectURL(f); const a = document.createElement("a"); a.href = url; a.download = f.name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { toast.error((e as Error).message); } finally { setDownloading(false); }
  };

  const d = q.data;
  const idx = list.map((s) => d?.societies.findIndex((x) => x.id === s.id) ?? -1);
  const rows = (d?.rows ?? []).map((r) => ({ ...r, cells: idx.map((i) => (i < 0 ? null : { v: r.values[i], best: r.best.includes(i) })) }));
  const visible = diffOnly && list.length > 1 ? rows.filter((r) => new Set(r.cells.map((c) => c?.v)).size > 1) : rows;
  const label = list.map((s) => s.name).join(", ");
  const attached = list.reduce((a, s, i) => a + photoIds(s, mediaOf(i)).length, 0);

  return (
    <PageContainer wide>
      <PageHeader title="Compare societies" tabs={<CompareTabs value="societies" />}
        description={list.length ? `${list.length} of ${MAX_SOCIETIES} societies, side by side. Pick the layouts, photos and brochure to send at the bottom.` : "Line societies up side by side and send your client one PDF with layouts, photos and brochures."}
        actions={mounted && list.length > 0 && <>
          <Button variant="secondary" onClick={() => setPicker(true)} disabled={list.length >= MAX_SOCIETIES}><Plus /> Add societies</Button>
          <Button variant="secondary" onClick={download} loading={downloading}><Download /> PDF</Button>
          <Button onClick={() => setShare(true)}><Share2 /> Share</Button>
        </>} />

      {!mounted ? <Skeleton className="h-96" />
        : !list.length ? (
          <Card>
            <EmptyState icon={<Building2 />} title="Pick societies to compare" description="Search your projects by name, builder or area, or open a project and tap Compare."
              action={<Button onClick={() => setPicker(true)}><Plus /> Search societies</Button>} secondary={<Button variant="secondary" asChild><Link href="/app/projects"><Building2 /> Browse projects</Link></Button>} />
          </Card>
        ) : q.isError && !d ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} />
        : (
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
              <label className="flex items-center gap-2.5 text-sm text-fg-muted"><Switch checked={diffOnly} onCheckedChange={setDiffOnly} aria-label="Only show differences" />Only show differences</label>
              <button type="button" onClick={() => societyCompare.clear()} className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-danger"><Trash2 className="size-4" /> Clear all</button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[calc(96px+var(--n)*170px)] table-fixed border-separate border-spacing-0 text-sm sm:min-w-[calc(150px+var(--n)*220px)]" style={{ ["--n" as string]: list.length }}>
                <thead>
                  <tr>
                    <th scope="col" className="sticky left-0 z-10 w-[96px] border-b border-border bg-surface-solid px-4 py-3 text-left align-bottom text-xs font-medium uppercase tracking-wide text-fg-subtle sm:w-[150px]">Society</th>
                    {list.map((s, i) => {
                      const meta = d?.societies.find((x) => x.id === s.id);
                      const cover = mediaOf(i)?.photos[0];
                      return (
                        <th key={s.id} scope="col" className="border-b border-l border-border p-2 text-left align-top font-normal sm:p-3">
                          <motion.div layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                            <div className="relative mb-2 aspect-[16/9] overflow-hidden rounded-lg bg-bg-subtle">
                              {cover ? <img src={cover.url} alt="" className="size-full object-cover" /> : media[i]?.isLoading ? <Skeleton className="size-full" /> : <span className="grid size-full place-items-center text-fg-subtle"><Building2 className="size-6" /></span>}
                              <button type="button" onClick={() => societyCompare.remove(s.id)} aria-label={`Remove ${s.name}`} className="absolute right-1.5 top-1.5 grid size-7 place-items-center rounded-full bg-black/50 text-white backdrop-blur hover:bg-black/70"><X className="size-4" /></button>
                            </div>
                            <Link href={`/app/projects/${s.id}`} className="block truncate text-base font-semibold tracking-tight hover:text-primary">{meta?.name ?? s.name}</Link>
                            <p className="truncate text-xs text-fg-muted">{meta?.subtitle || s.where}</p>
                          </motion.div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {!d ? Array.from({ length: 7 }).map((_, i) => <tr key={i}><td className="sticky left-0 bg-surface-solid px-4 py-3"><Skeleton className="h-4 w-20" /></td>{list.map((s) => <td key={s.id} className="border-l border-border px-4 py-3"><Skeleton className="h-4 w-24" /></td>)}</tr>)
                    : visible.map((r, ri) => {
                      const head = GROUPS[r.group] && visible[ri - 1]?.group !== r.group;
                      const yesNo = r.group === "amenities" && r.key !== "amenity_count";
                      return (
                        <React.Fragment key={r.key}>
                          {head && <GroupRow n={list.length} title={GROUPS[r.group]} hint={r.group === "layouts" ? "Untick a layout at the bottom to leave it out" : undefined} />}
                          <tr className={cn(ri % 2 === 1 && "[&>td]:bg-surface-2")}>
                            <th scope="row" className="sticky left-0 z-10 border-t border-border bg-surface-solid px-3 py-2.5 text-left text-[13px] font-normal text-fg-muted sm:px-4">{r.label}</th>
                            {r.cells.map((c, i) => (
                              <td key={list[i].id} className={cn("border-l border-t border-border px-3 py-2.5 align-top sm:px-4", c?.best && "font-semibold text-success", r.key === "price" && "text-[15px] font-semibold")}>
                                {!c ? <Skeleton className="h-4 w-20" />
                                  : yesNo ? (c.v === "Yes" ? <Check className="size-4 text-success" aria-label="Yes" /> : <Minus className="size-4 text-fg-subtle" aria-label="No" />)
                                  : <span className="inline-flex max-w-full items-start gap-1"><span className="min-w-0 [overflow-wrap:anywhere]">{c.v}</span>{c.best && <Check className="mt-0.5 size-3.5 shrink-0" aria-label="best" />}</span>}
                              </td>
                            ))}
                          </tr>
                        </React.Fragment>
                      );
                    })}
                  {d && !visible.length && <tr><td colSpan={list.length + 1} className="px-4 py-8 text-center text-sm text-fg-muted">These societies are the same on every detail we have.</td></tr>}

                  {d && <>
                    <GroupRow n={list.length} title="What to send" hint={`One PDF: the table above, then each society's ticked floor plans, photos and brochure${attached ? ` (${attached} photos so far)` : ""}`} primary />
                    <tr>
                      <th scope="row" className="sticky left-0 z-10 border-t border-border bg-surface-solid px-3 py-3 text-left align-top text-[13px] font-normal text-fg-muted sm:px-4">Layouts</th>
                      {list.map((s) => <td key={s.id} className="border-l border-t border-border p-3 align-top"><LayoutPicker s={s} meta={d.societies.find((x) => x.id === s.id)} /></td>)}
                    </tr>
                    <tr>
                      <th scope="row" className="sticky left-0 z-10 border-t border-border bg-surface-solid px-3 py-3 text-left align-top text-[13px] font-normal text-fg-muted sm:px-4">Photos</th>
                      {list.map((s, i) => <td key={s.id} className="border-l border-t border-border p-3 align-top"><PhotoPicker s={s} m={mediaOf(i)} loading={!!media[i]?.isLoading} /></td>)}
                    </tr>
                    <tr>
                      <th scope="row" className="sticky left-0 z-10 border-t border-border bg-surface-solid px-3 py-3 text-left align-top text-[13px] font-normal text-fg-muted sm:px-4">Brochure</th>
                      {list.map((s, i) => <td key={s.id} className="border-l border-t border-border p-3 align-top"><BrochurePicker s={s} m={mediaOf(i)} loading={!!media[i]?.isLoading} /></td>)}
                    </tr>
                  </>}
                </tbody>
              </table>
            </div>
            {list.length === 1 && <div className="border-t border-border bg-primary-soft/50 px-4 py-3 text-sm">Add at least one more society to see them side by side. <button type="button" onClick={() => setPicker(true)} className="font-medium text-primary hover:underline">Add societies</button></div>}
          </Card>
        )}

      <SocietyPicker open={picker} onOpenChange={setPicker} />
      <ShareComparison open={share} onOpenChange={setShare} kind="societies" body={body} label={label} />
    </PageContainer>
  );
}

function GroupRow({ n, title, hint, primary }: { n: number; title: string; hint?: string; primary?: boolean }) {
  return (
    <tr>
      <td colSpan={n + 1} className={cn("border-t border-border px-0 py-0", primary ? "bg-primary-soft/60" : "bg-bg-subtle/70")}>
        {/* sticky so the heading stays in view while the columns scroll sideways on a phone */}
        <div className="sticky left-0 flex w-max max-w-[calc(100vw-48px)] flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-2 sm:px-4">
          <span className={cn("text-xs font-semibold uppercase tracking-wide", primary ? "text-primary" : "text-fg-muted")}>{title}</span>
          {hint && <span className="text-xs text-fg-subtle">{hint}</span>}
        </div>
      </td>
    </tr>
  );
}

function LayoutPicker({ s, meta }: { s: CompareSociety; meta?: SocietyComparison["societies"][number] }) {
  if (!meta) return <Skeleton className="h-7 w-28" />;
  if (!meta.sizes.length) return <p className="text-xs text-fg-subtle">No sizes added to this project yet.</p>;
  const chosen = new Set(meta.chosen_sizes);
  const toggle = (label: string) => {
    const next = chosen.has(label) ? meta.chosen_sizes.filter((x) => x !== label) : meta.sizes.map((z) => z.label).filter((x) => chosen.has(x) || x === label);
    societyCompare.update(s.id, { sizes: next });
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {meta.sizes.map((z, i) => {
        const on = chosen.has(z.label);
        const twin = meta.sizes.filter((y) => y.label === z.label).length > 1;
        return (
          <button key={`${z.label}-${i}`} type="button" onClick={() => toggle(z.label)} aria-pressed={on} title={z.has_floor_plan ? "Floor plan goes in the PDF" : "No floor plan uploaded"}
            className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors", on ? "border-primary bg-primary-soft text-primary" : "border-border text-fg-muted hover:border-border-strong hover:text-fg")}>
            {on ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}{z.label}{twin && z.area_sqft ? <span className="font-normal opacity-75">{Math.round(z.area_sqft).toLocaleString("en-IN")}</span> : null}{z.has_floor_plan && <LayoutTemplate className="size-3 opacity-70" aria-label="has a floor plan" />}
          </button>
        );
      })}
    </div>
  );
}

function PhotoPicker({ s, m, loading }: { s: CompareSociety; m?: ProjectMedia; loading: boolean }) {
  if (loading || !m) return <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="aspect-[4/3]" />)}</div>;
  if (!m.photos.length) return <p className="flex items-center gap-1.5 text-xs text-fg-subtle"><ImageOff className="size-3.5" />No society photos yet.</p>;
  const on = new Set(photoIds(s, m));
  const toggle = (f: StoredFile) => societyCompare.update(s.id, { photos: m.photos.map((p) => p.id).filter((id) => (id === f.id ? !on.has(id) : on.has(id))) });
  return (
    <div>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
        {m.photos.map((f, i) => {
          const picked = on.has(f.id);
          return (
            <button key={f.id} type="button" onClick={() => toggle(f)} aria-pressed={picked} aria-label={`Photo ${i + 1}`}
              className={cn("relative aspect-[4/3] overflow-hidden rounded-md ring-2 ring-offset-1 ring-offset-surface transition", picked ? "ring-primary" : "ring-transparent opacity-60 hover:opacity-100")}>
              <img src={f.url} alt="" className="size-full object-cover" />
              <span className={cn("absolute right-1 top-1 grid size-5 place-items-center rounded-full border text-white", picked ? "border-primary bg-primary" : "border-white/80 bg-black/30")}>{picked && <Check className="size-3" />}</span>
            </button>
          );
        })}
      </div>
      <div className="mt-1.5 flex items-center justify-between text-xs text-fg-subtle">
        <span>{on.size} of {m.photos.length}</span>
        <button type="button" className="font-medium text-primary hover:underline" onClick={() => societyCompare.update(s.id, { photos: on.size === m.photos.length ? [] : m.photos.map((p) => p.id) })}>{on.size === m.photos.length ? "None" : "All"}</button>
      </div>
    </div>
  );
}

function BrochurePicker({ s, m, loading }: { s: CompareSociety; m?: ProjectMedia; loading: boolean }) {
  if (loading || !m) return <Skeleton className="h-6 w-32" />;
  const b = m.brochures[m.brochures.length - 1];
  if (!b) return <p className="flex items-center gap-1.5 text-xs text-fg-subtle"><FileText className="size-3.5" />No brochure uploaded.</p>;
  return (
    <label className="flex items-center gap-2.5 text-sm">
      <Switch checked={s.brochure} onCheckedChange={(v) => societyCompare.update(s.id, { brochure: v })} aria-label={`Include the ${s.name} brochure`} />
      <span className="min-w-0"><span className="block font-medium leading-tight">{s.brochure ? "Included" : "Not included"}</span><span className="block truncate text-xs text-fg-subtle">{mb(b.size_bytes)} PDF</span></span>
    </label>
  );
}

/** Search projects and tick the ones to compare. Ticks apply at once, so "Done" just closes. */
export function SocietyPicker({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const list = useSocietyCompare();
  const toast = useToast();
  const [q, setQ] = React.useState("");
  const dq = useDebounce(q, 200);
  const res = useQuery({ queryKey: ["compare-society-picker", dq], enabled: open, staleTime: 15_000, queryFn: () => api.page<Project>("/api/v1/projects", { q: dq, per_page: 40 }) });
  const rows = res.data?.data ?? [];
  const picked = new Set(list.map((s) => s.id));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" title="Add societies to compare" description={`Pick up to ${MAX_SOCIETIES}. Search by name, builder or area.`}>
        <div className="space-y-3">
          <Input autoFocus icon={<Search />} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Society, builder or area, e.g. Sector 67" aria-label="Search societies" />
          <ul className="max-h-[50vh] divide-y divide-border overflow-y-auto rounded-xl border border-border" aria-label="Societies">
            {res.isLoading && <li className="flex justify-center py-10"><Spinner /></li>}
            {!res.isLoading && !rows.length && <li className="px-4 py-10 text-center text-sm text-fg-muted">No societies match. Try another search.</li>}
            {rows.map((p) => {
              const on = picked.has(p.id);
              return (
                <li key={p.id}>
                  <button type="button" aria-pressed={on} onClick={() => { if (societyCompare.toggle({ id: p.id, name: p.name, where: where(p) }) === "full") toastFull(toast); }}
                    className={cn("flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface-hover", on && "bg-primary-soft/60")}>
                    <span className={cn("grid size-5 shrink-0 place-items-center rounded-md border", on ? "border-primary bg-primary text-primary-fg" : "border-border-strong")}>{on && <Check className="size-3.5" />}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{p.name}{p.developer && <span className="ml-2 font-normal text-fg-muted">by {p.developer}</span>}</span>
                      <span className="block truncate text-xs text-fg-subtle">{[where(p), (p.sizes ?? []).map((z) => z.label).join(", ")].filter(Boolean).join(" · ") || "No details yet"}</span>
                    </span>
                    <span className="hidden shrink-0 text-right sm:block">
                      {p.starting_price != null && <span className="block text-sm font-semibold tabular-nums">from {formatMoneyCompact(p.starting_price)}</span>}
                      <span className="text-[11px] font-medium text-success">{p.summary.available} available</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
        <DialogFooter className="items-center sm:justify-between">
          <span className="text-sm text-fg-muted">{list.length} of {MAX_SOCIETIES} picked</span>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** "Compare" on a project page: adds the society to the list, then offers the way to the comparison. */
export function SocietyCompareButton({ p }: { p: Project }) {
  const list = useSocietyCompare(); const toast = useToast(); const router = useRouter();
  const inList = list.some((s) => s.id === p.id);
  const toggle = () => { if (societyCompare.toggle({ id: p.id, name: p.name, where: where(p) }) === "full") toastFull(toast); };
  return (
    <>
      <Button variant={inList ? "soft" : "secondary"} onClick={toggle} aria-pressed={inList} aria-label={inList ? "In comparison" : "Compare society"}>{inList ? <Check /> : <Scale />} <span className="hidden sm:inline">{inList ? "In comparison" : "Compare society"}</span></Button>
      {inList && list.length > 1 && <Button variant="ghost" onClick={() => navigate(router, "/app/compare?tab=societies")}>Compare {list.length}</Button>}
    </>
  );
}
