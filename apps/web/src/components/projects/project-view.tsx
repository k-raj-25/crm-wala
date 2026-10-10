"use client";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { BarChart3, Building2, ChevronRight, Download, Layers, LayoutGrid, List, MapPin, MoreHorizontal, Plus, Rows3, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Badge, BarsChart, Button, Card, ConfirmDialog, DonutChart, DropdownContent, DropdownItem, DropdownMenu, DropdownTrigger, EmptyState, ErrorState, Input, NativeSelect, Segmented, Skeleton, Tooltip, cn, formatMoneyCompact, useTheme, useToast } from "@crm/ui";
import { PageContainer } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { AVAILABLE, PROJECT_KINDS, PROJECT_STAGES, STATUS, STATUS_ORDER, floorLabel, priceLine, where } from "@/lib/realestate";
import type { Building, Project, Summary, UnitMini, UnitStatus } from "@/lib/realestate";
import { AddFloorsDialog, AddTowerDialog, AddUnitDialog } from "./forms";
import { BuildingView, Legend, NO_SPOT, Sky, fitsSpot, isSpotting } from "./building";
import type { Spot } from "./building";
import { TowerArt } from "./tower-art";
import { UnitDrawer } from "./unit-drawer";

type View = "building" | "list" | "analytics";

export function ProjectView() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const toast = useToast();
  const { can } = useAccess();
  const canEdit = can("units.update");
  const [spot, setSpot] = React.useState<Spot>(NO_SPOT);
  const [unitId, setUnitId] = React.useState<string | null>(sp.get("unit"));
  const [dialog, setDialog] = React.useState<null | "tower" | "floors" | "unit" | "delete">(null);
  const [flash, setFlash] = React.useState<number | null>(null);
  const floorEls = React.useRef(new Map<number, HTMLElement>());

  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.get<Project>(`/api/v1/projects/${id}`) });
  const towers = project.data?.towers ?? [];
  const towerId = towers.find((t) => t.id === (sp.get("tower") ?? unitProbe.data?.tower_id))?.id ?? towers[0]?.id;
  const view = (["building", "list", "analytics"].includes(sp.get("view") ?? "") ? sp.get("view") : "building") as View;
  const building = useQuery({ queryKey: ["building", id, towerId], enabled: !!towerId, queryFn: () => api.get<Building>(`/api/v1/projects/${id}/towers/${towerId}/building`), refetchInterval: 60_000 });

  const unitProbe = useQuery({ queryKey: ["unit", sp.get("unit")], enabled: !!sp.get("unit") && !sp.get("tower"), queryFn: () => api.get<{ tower_id: string }>(`/api/v1/units/${sp.get("unit")}`) });
  const nav = (patch: Record<string, string | null>) => {
    const q = new URLSearchParams(sp.toString());
    Object.entries(patch).forEach(([k, v]) => (v == null ? q.delete(k) : q.set(k, v)));
    router.replace(`${path}?${q.toString()}`, { scroll: false });
  };
  const toggleStatus = (s: UnitStatus) => setSpot((x) => ({ ...x, statuses: x.statuses.includes(s) ? x.statuses.filter((v) => v !== s) : [...x.statuses, s] }));
  const pickFloor = (f: number) => {
    floorEls.current.get(f)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(f); setTimeout(() => setFlash(null), 1500);
  };
  const remove = async () => {
    try { await api.delete(`/api/v1/projects/${id}`); toast.success("Project deleted"); router.push("/app/projects"); } catch { toast.error("Couldn't delete the project"); }
  };

  if (project.isError) return <PageContainer wide><ErrorState kind="generic" title="We couldn't find that project" action={<Button asChild><Link href="/app/projects">Back to projects</Link></Button>} /></PageContainer>;
  const p = project.data;
  const b = building.data;
  const bhks = b ? [...new Set(b.floors.flatMap((f) => f.units.map((u) => u.bhk)).filter(Boolean) as string[])].sort() : [];
  const counts = b?.summary.counts ?? {};
  const tower = towers.find((t) => t.id === towerId);

  return (
    <PageContainer wide>
      {/* breadcrumb + title */}
      <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-1 text-[13px] text-fg-muted">
        <Link href="/app/projects" className="hover:text-fg">Projects</Link>
        {p?.city && <><ChevronRight className="size-3.5" /><span>{p.city}</span></>}
        {p?.sector && <><ChevronRight className="size-3.5" /><span>{p.sector}</span></>}
        {p && <><ChevronRight className="size-3.5" /><span className={cn(!tower && "font-medium text-primary")}>{p.name}</span></>}
        {tower && <><ChevronRight className="size-3.5" /><span className="font-medium text-primary">{tower.name}</span></>}
      </nav>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {p ? <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight sm:text-[28px]">{p.name}<Badge tone={p.stage === "ready" ? "success" : p.stage === "under_construction" ? "warning" : "info"}>{PROJECT_STAGES.find((s) => s[0] === p.stage)?.[1]}</Badge></h1> : <Skeleton className="h-9 w-72" />}
          {p && <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px] text-fg-muted"><span className="inline-flex items-center gap-1"><MapPin className="size-4" />{where(p) || "No address yet"}</span>{p.developer && <span>by {p.developer}</span>}<span>{PROJECT_KINDS.find((k) => k[0] === p.kind)?.[1]}</span>{p.rera_id && <span className="text-xs">RERA {p.rera_id}</span>}</p>}
        </div>
        {canEdit && p && (
          <div className="flex items-center gap-2">
            {towerId && <Button variant="secondary" onClick={() => setDialog("unit")}><Plus /> Add flat</Button>}
            <Button onClick={() => setDialog("tower")}><Building2 /> Add tower</Button>
            <DropdownMenu>
              <DropdownTrigger asChild><Button variant="secondary" size="icon" aria-label="More actions"><MoreHorizontal /></Button></DropdownTrigger>
              <DropdownContent>
                {towerId && <DropdownItem icon={<Layers />} onSelect={() => setDialog("floors")}>Add floors to this tower</DropdownItem>}
                {towerId && <DropdownItem icon={<Download />} onSelect={() => window.open(`/api/v1/units/export?tower_id=${towerId}`)}>Download flats (CSV)</DropdownItem>}
                {can("projects.delete") && <DropdownItem danger icon={<Trash2 />} onSelect={() => setDialog("delete")}>Delete project</DropdownItem>}
              </DropdownContent>
            </DropdownMenu>
          </div>
        )}
      </div>

      {p && towers.length > 1 && (
        <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Towers">
          {towers.map((t) => (
            <button key={t.id} role="tab" aria-selected={t.id === towerId} onClick={() => { setSpot(NO_SPOT); nav({ tower: t.id }); }}
              className={cn("relative h-10 rounded-full border px-4 text-sm font-medium transition-colors", t.id === towerId ? "border-primary bg-primary-soft text-primary" : "border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg")}>
              {t.name}<span className="ml-2 text-xs opacity-70">{t.summary.available} free</span>
            </button>
          ))}
        </div>
      )}

      {project.isLoading || (towerId && building.isLoading) ? <div className="grid gap-5 lg:grid-cols-[260px_1fr_300px]"><Skeleton className="h-96" /><Skeleton className="h-[560px]" /><Skeleton className="h-96" /></div>
        : !towers.length ? <Card><EmptyState icon={<Building2 />} title="No towers yet" description="Add a tower and we'll draw the whole building, floor by floor, so you can see every flat at a glance." action={canEdit ? <Button onClick={() => setDialog("tower")}><Plus /> Add the first tower</Button> : undefined} /></Card>
        : building.isError || !b ? <ErrorState kind="unavailable" onRetry={() => building.refetch()} />
        : (
          <div className="grid items-start gap-5 lg:grid-cols-[250px_minmax(0,1fr)_290px]">
            {/* left: the tower as a picture */}
            <div className="order-2 space-y-4 lg:order-1 lg:sticky lg:top-6">
              <Card className="overflow-hidden">
                <div className="relative"><TowerArt data={b} spot={spot} onPickFloor={view === "building" ? pickFloor : undefined} />
                  <span className="absolute left-3 top-3 rounded-full bg-surface/90 px-2.5 py-1 text-xs font-semibold shadow-sm backdrop-blur">{b.tower.name}</span></div>
                <div className="grid grid-cols-3 divide-x divide-border border-t border-border text-center">
                  {[[b.summary.floors, "Floors"], [b.summary.units_per_floor, "Per floor"], [b.summary.total, "Flats"]].map(([n, l]) => <div key={String(l)} className="py-3"><div className="text-lg font-semibold tabular-nums">{n}</div><div className="text-xs text-fg-muted">{l}</div></div>)}
                </div>
              </Card>
              <p className="hidden px-1 text-xs text-fg-subtle lg:block">Tip: tap a floor in the picture to jump to it.</p>
            </div>

            {/* centre: the building */}
            <div className="order-1 min-w-0 space-y-4 lg:order-2">
              <Card className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Segmented value={view} onChange={(v) => nav({ view: v === "building" ? null : v })} options={[{ value: "building", label: "Building", icon: <LayoutGrid /> }, { value: "list", label: "List", icon: <List /> }, { value: "analytics", label: "Analytics", icon: <BarChart3 /> }]} />
                  {view !== "analytics" && (
                    <div className="flex w-full items-center gap-2 sm:w-auto">
                      {bhks.length > 1 && <NativeSelect aria-label="Filter by size" value={spot.bhk ?? ""} onChange={(e) => setSpot({ ...spot, bhk: e.target.value || null })} className="!w-auto min-w-[110px]"><option value="">All sizes</option>{bhks.map((x) => <option key={x} value={x}>{x}</option>)}</NativeSelect>}
                      <div className="min-w-0 flex-1 sm:w-56 sm:flex-none"><Input icon={<Search />} value={spot.q} onChange={(e) => setSpot({ ...spot, q: e.target.value })} placeholder="Find a flat, e.g. 801" aria-label="Find a flat" /></div>
                    </div>
                  )}
                </div>
                {view !== "analytics" && (
                  <div className="mt-3 space-y-3">
                    <Legend counts={counts} active={spot.statuses} onToggle={toggleStatus} />
                    {isSpotting(spot) && <SpotBar b={b} spot={spot} onClear={() => setSpot(NO_SPOT)} />}
                  </div>
                )}
              </Card>

              {view === "building" && (
                <Sky className="rounded-2xl border border-border px-2 pb-0 pt-5 sm:px-6">
                  <BuildingView data={b} spot={spot} onOpen={setUnitId} flashFloor={flash} registerFloor={(f, el) => { if (el) floorEls.current.set(f, el); else floorEls.current.delete(f); }} />
                </Sky>
              )}
              {view === "list" && <UnitTable b={b} spot={spot} onOpen={setUnitId} />}
              {view === "analytics" && p && <Analytics project={p} b={b} />}
            </div>

            {/* right: numbers */}
            <div className="order-3 space-y-4 lg:sticky lg:top-6">
              <Card className="p-4">
                <h2 className="mb-3 text-sm font-semibold">Flats by status</h2>
                <div className="grid grid-cols-2 gap-2">
                  {STATUS_ORDER.filter((s) => (counts[s] ?? 0) > 0).map((s) => <StatusTile key={s} s={s} n={counts[s] ?? 0} active={spot.statuses.includes(s)} onClick={() => { toggleStatus(s); if (view === "analytics") nav({ view: null }); }} />)}
                </div>
              </Card>
              <SummaryCard b={b} tower={tower?.name} />
              {canEdit && (
                <Card className="p-4">
                  <h2 className="mb-3 text-sm font-semibold">Quick actions</h2>
                  <div className="grid gap-2">
                    <Button onClick={() => setDialog("unit")}><Plus /> Add a flat</Button>
                    <Button variant="secondary" onClick={() => setDialog("floors")}><Layers /> Add floors</Button>
                    <Button variant="secondary" onClick={() => router.push(`/app/leads?project_id=${id}`)}><Rows3 /> Enquiries for this project</Button>
                  </div>
                </Card>
              )}
            </div>
          </div>
        )}

      <UnitDrawer unitId={unitId} onClose={() => setUnitId(null)} canEdit={canEdit} />
      {p && <AddTowerDialog open={dialog === "tower"} onOpenChange={(o) => !o && setDialog(null)} projectId={p.id} projectKind={p.kind} onCreated={(tid) => { setSpot(NO_SPOT); nav({ tower: tid, view: null }); }} />}
      {p && tower && towerId && <AddFloorsDialog open={dialog === "floors"} onOpenChange={(o) => !o && setDialog(null)} projectId={p.id} towerId={towerId} perFloor={b?.summary.units_per_floor ?? 4} />}
      {tower && towerId && <AddUnitDialog open={dialog === "unit"} onOpenChange={(o) => !o && setDialog(null)} towerId={towerId} floors={tower.floors} hasGround={tower.has_ground} />}
      <ConfirmDialog open={dialog === "delete"} onOpenChange={(o) => !o && setDialog(null)} title={`Delete ${p?.name ?? "this project"}?`} description="All its towers and flats will be removed from your inventory. Clients and deals stay, but they will no longer be linked to these flats." confirmLabel="Delete project" typeToConfirm={p?.name} onConfirm={remove} />
    </PageContainer>
  );
}

function SpotBar({ b, spot, onClear }: { b: Building; spot: Spot; onClear: () => void }) {
  const n = b.floors.reduce((a, f) => a + f.units.filter((u) => fitsSpot(u, spot)).length, 0);
  return (
    <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between gap-3 rounded-lg bg-primary-soft px-3 py-2 text-[13px]" role="status">
      <span><b>{n}</b> {n === 1 ? "flat matches" : "flats match"} — they're lit up on the building{n === 0 && ". Try removing a filter."}</span>
      <button type="button" onClick={onClear} className="font-medium text-primary hover:underline">Clear</button>
    </motion.div>
  );
}

function StatusTile({ s, n, active, onClick }: { s: UnitStatus; n: number; active: boolean; onClick: () => void }) {
  const { resolved } = useTheme();
  const m = STATUS[s]; const Icon = m.icon; const bg = resolved === "dark" ? m.bgDark : m.bg;
  return (
    <button type="button" onClick={onClick} aria-pressed={active} title={m.hint} className={cn("rounded-xl border p-3 text-left transition-all hover:-translate-y-px hover:shadow-sm", active ? "border-transparent" : "border-border bg-surface")} style={active ? { background: bg, color: m.ink } : undefined}>
      <div className="flex items-center justify-between"><span className="text-2xl font-semibold tabular-nums leading-none">{n}</span><span className="grid size-6 place-items-center rounded-md" style={{ background: bg, color: m.ink }}><Icon className="size-3.5" /></span></div>
      <div className={cn("mt-1.5 text-xs", active ? "opacity-90" : "text-fg-muted")}>{m.label}</div>
    </button>
  );
}

function SummaryCard({ b, tower }: { b: Building; tower?: string }) {
  const s: Summary = b.summary;
  const rows: [string, React.ReactNode][] = [
    ["Total floors", s.floors], ["Total flats", s.total], ["Available to sell or rent", <b key="a" className="text-success">{s.available}</b>], ["Sold or rented", s.closed],
    ["Held or booked", (s.counts.on_hold ?? 0) + (s.counts.booked ?? 0)], ["Listed for sale", s.counts.for_sale ?? 0], ["Value for sale", formatMoneyCompact(s.for_sale_value ?? 0)],
  ];
  return (
    <Card className="p-4">
      <h2 className="mb-1 text-sm font-semibold">{tower ?? "Tower"} summary</h2>
      <dl className="divide-y divide-border text-sm">{rows.map(([k, v]) => <div key={k} className="flex items-center justify-between py-2"><dt className="text-fg-muted">{k}</dt><dd className="font-medium tabular-nums">{v}</dd></div>)}</dl>
      <div className="mt-3"><div className="mb-1 flex justify-between text-xs text-fg-muted"><span>Taken</span><span>{s.occupancy_pct}%</span></div><div className="h-2 overflow-hidden rounded-full bg-bg-subtle"><motion.div className="h-full rounded-full bg-primary" initial={{ width: 0 }} animate={{ width: `${s.occupancy_pct}%` }} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }} /></div></div>
    </Card>
  );
}

function UnitTable({ b, spot, onOpen }: { b: Building; spot: Spot; onOpen: (id: string) => void }) {
  const { resolved } = useTheme();
  const [sort, setSort] = React.useState<{ k: "number" | "floor" | "price" | "area"; dir: 1 | -1 }>({ k: "floor", dir: -1 });
  const rows = b.floors.flatMap((f) => f.units).filter((u) => !isSpotting(spot) || fitsSpot(u, spot));
  const val = (u: UnitMini) => (sort.k === "number" ? u.number : sort.k === "floor" ? u.floor * 100 + (u.position ?? 0) * -0.01 : sort.k === "area" ? (u.area_sqft ?? 0) : (u.sale_price ?? u.monthly_rent ?? 0));
  rows.sort((a, c) => (val(a) < val(c) ? -1 : val(a) > val(c) ? 1 : 0) * sort.dir);
  const th = (k: typeof sort.k, label: string, right?: boolean) => <th scope="col" className={cn("px-4 py-2.5 font-medium", right && "text-right")}><button type="button" onClick={() => setSort({ k, dir: sort.k === k ? (sort.dir === 1 ? -1 : 1) : 1 })} className="inline-flex items-center gap-1 hover:text-fg">{label}{sort.k === k && <span aria-hidden>{sort.dir === 1 ? "↑" : "↓"}</span>}</button></th>;
  if (!rows.length) return <Card><EmptyState compact icon={<Search />} title="No flats match" description="Clear the filters to see every flat again." /></Card>;
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-border bg-surface-2 text-xs uppercase tracking-wide text-fg-muted"><tr>{th("number", "Flat")}{th("floor", "Floor")}<th scope="col" className="px-4 py-2.5 font-medium">Size</th>{th("area", "Area", true)}<th scope="col" className="px-4 py-2.5 font-medium">Facing</th>{th("price", "Price", true)}<th scope="col" className="px-4 py-2.5 font-medium">Status</th></tr></thead>
          <tbody className="divide-y divide-border">
            {rows.map((u) => {
              const m = STATUS[u.status]; const Icon = m.icon;
              return (
                <tr key={u.id} onClick={() => onOpen(u.id)} className="cursor-pointer transition-colors hover:bg-surface-hover">
                  <td className="px-4 py-2.5 font-semibold tabular-nums"><button className="outline-none focus-visible:underline" onClick={(e) => { e.stopPropagation(); onOpen(u.id); }}>{u.number}</button></td>
                  <td className="px-4 py-2.5 text-fg-muted">{floorLabel(u.floor)}</td><td className="px-4 py-2.5">{u.bhk ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{u.area_sqft ? `${Math.round(u.area_sqft).toLocaleString("en-IN")} sq ft` : "—"}</td><td className="px-4 py-2.5 text-fg-muted">{u.facing ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right font-medium tabular-nums">{priceLine(u)}</td>
                  <td className="px-4 py-2.5"><span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold" style={{ background: resolved === "dark" ? m.bgDark : m.bg, color: m.ink }}><Icon className="size-3" />{m.label}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-border px-4 py-2 text-xs text-fg-muted">{rows.length} flat{rows.length === 1 ? "" : "s"}</p>
    </Card>
  );
}

function Analytics({ project, b }: { project: Project; b: Building }) {
  const { resolved } = useTheme();
  const sum = useQuery({ queryKey: ["project", project.id, "analytics"], queryFn: () => api.get<{ by_bhk: Record<string, Partial<Record<UnitStatus, number>>>; avg_price_per_sqft: number | null; sold_value: number }>(`/api/v1/projects/${project.id}/units-summary`) });
  const col = (s: UnitStatus) => (resolved === "dark" ? STATUS[s].bgDark : STATUS[s].bg);
  const series = STATUS_ORDER.map((s) => ({ key: s, label: STATUS[s].label, color: col(s) }));
  const rows = Object.entries(sum.data?.by_bhk ?? {}).map(([bhk, c]) => ({ bhk, ...c })).sort((a, c) => a.bhk.localeCompare(c.bhk));
  const donut = STATUS_ORDER.filter((s) => (project.summary.counts[s] ?? 0) > 0).map((s) => ({ name: STATUS[s].label, value: project.summary.counts[s] ?? 0, color: col(s) }));
  const tiles: [string, string, string][] = [
    ["Taken", `${project.summary.occupancy_pct}%`, "of all flats in the project"], ["Available", String(project.summary.available), "vacant or listed"],
    ["Sold value", formatMoneyCompact(sum.data?.sold_value ?? 0), "completed sales"], ["Average rate", sum.data?.avg_price_per_sqft ? `₹${Math.round(sum.data.avg_price_per_sqft).toLocaleString("en-IN")}` : "—", "per sq ft"],
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{tiles.map(([k, v, h]) => <Card key={k} className="p-4"><p className="text-xs text-fg-muted">{k}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{v}</p><p className="text-xs text-fg-subtle">{h}</p></Card>)}</div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="p-5"><h3 className="mb-3 text-sm font-semibold">Whole project, by status</h3><DonutChart data={donut} center={<div className="text-center"><div className="text-2xl font-semibold">{project.summary.total}</div><div className="text-xs text-fg-muted">flats</div></div>} /></Card>
        <Card className="p-5"><h3 className="mb-1 text-sm font-semibold">By size</h3><p className="mb-3 text-xs text-fg-muted">Which sizes are moving, which are sitting.</p>
          {sum.isLoading ? <Skeleton className="h-56" /> : <><BarsChart data={rows} xKey="bhk" series={series.filter((s) => rows.some((r) => (r as Record<string, unknown>)[s.key]))} stacked height={230} /></>}</Card>
      </div>
      <Card className="p-5"><h3 className="mb-3 text-sm font-semibold">Floor by floor ({b.tower.name})</h3>
        <div className="space-y-1.5">{b.floors.map((f) => { const free = f.units.filter((u) => AVAILABLE.includes(u.status)).length; const n = f.units.length || 1; return (
          <Tooltip key={f.floor} content={`${floorLabel(f.floor)}: ${free} of ${f.units.length} available`}><div className="flex items-center gap-3"><span className="w-16 shrink-0 text-xs text-fg-muted">{floorLabel(f.floor)}</span><div className="h-3 flex-1 overflow-hidden rounded-full bg-bg-subtle"><div className="h-full rounded-full bg-primary/80" style={{ width: `${(free / n) * 100}%` }} /></div><span className="w-10 text-right text-xs tabular-nums text-fg-muted">{free}/{f.units.length}</span></div></Tooltip>); })}</div>
      </Card>
    </div>
  );
}

