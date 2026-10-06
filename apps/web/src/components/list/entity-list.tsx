"use client";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Bookmark, ChevronLeft, ChevronRight, Columns3, Download, FileUp, Filter, Plus, Search, Tag, Trash2, UserCog, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Badge, Button, Card, Checkbox, ConfirmDialog, DropdownCheckItem, DropdownContent, DropdownItem, DropdownLabel, DropdownMenu, DropdownSeparator, DropdownTrigger, EmptyState, ErrorState, Input, NativeSelect, Popover, PopoverContent, PopoverTrigger, Select, SkeletonRows, Table, TD, TH, THead, TR, cn, useDebounce, useLocalStorage, useMediaQuery, useToast, type Page } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess, useMe, useMembers, usePipelines, useTags } from "@/lib/queries";
import type { SavedView } from "@/lib/types";
import { MemberSelect, TagInput } from "../forms/fields";
import { PageContainer, PageHeader } from "../shell/page";
import { useUI } from "../shell/ui-context";
import type { EntityConfig, FilterDef, Row } from "./types";

const PER_PAGE = [25, 50, 100];

function useFilterOptions(def: Extract<FilterDef, { kind: "multi" }>) {
  const members = useMembers(); const tags = useTags(); const { data: me } = useMe(); const pipelines = usePipelines();
  if (def.options) return def.options;
  switch (def.from) {
    case "members": return [{ value: "me", label: "Me" }, ...(members.data ?? []).map((m) => ({ value: m.user_id, label: m.name })), { value: "none", label: "Unassigned" }];
    case "tags": return (tags.data ?? []).map((t) => ({ value: t.name, label: t.name }));
    case "statuses": return (me?.workspace?.lead_statuses ?? []).map((s) => ({ value: s.key, label: s.label }));
    case "stages": return (pipelines.data ?? []).flatMap((p) => p.stages.map((s) => ({ value: s.id, label: `${pipelines.data!.length > 1 ? p.name + " · " : ""}${s.name}` })));
    default: return [];
  }
}

function FilterField({ def, params, set }: { def: FilterDef; params: URLSearchParams; set: (k: string, v: string | null) => void }) {
  if (def.kind === "multi") return <MultiFilter def={def} value={(params.get(def.param) ?? "").split(",").filter(Boolean)} onChange={(v) => set(def.param, v.length ? v.join(",") : null)} />;
  if (def.kind === "select") return <div><label className="mb-1.5 block text-xs font-medium text-fg-muted">{def.label}</label><NativeSelect value={params.get(def.param) ?? ""} onChange={(e) => set(def.param, e.target.value || null)}><option value="">Any</option>{def.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</NativeSelect></div>;
  if (def.kind === "range") return <div><label className="mb-1.5 block text-xs font-medium text-fg-muted">{def.label}</label><div className="flex items-center gap-2"><Input type="number" placeholder="Min" value={params.get(def.param + "_min") ?? ""} onChange={(e) => set(def.param + "_min", e.target.value || null)} /><span className="text-fg-subtle">–</span><Input type="number" placeholder="Max" value={params.get(def.param + "_max") ?? ""} onChange={(e) => set(def.param + "_max", e.target.value || null)} /></div></div>;
  return <div><label className="mb-1.5 block text-xs font-medium text-fg-muted">{def.label}</label><div className="flex items-center gap-2"><Input type="date" value={params.get(def.param + "_from") ?? ""} onChange={(e) => set(def.param + "_from", e.target.value || null)} /><span className="text-fg-subtle">–</span><Input type="date" value={params.get(def.param + "_to") ?? ""} onChange={(e) => set(def.param + "_to", e.target.value || null)} /></div></div>;
}

function MultiFilter({ def, value, onChange }: { def: Extract<FilterDef, { kind: "multi" }>; value: string[]; onChange: (v: string[]) => void }) {
  const opts = useFilterOptions(def);
  return (
    <div><label className="mb-1.5 block text-xs font-medium text-fg-muted">{def.label}</label>
      <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto">{opts.length === 0 && <span className="text-xs text-fg-subtle">No options yet</span>}{opts.map((o) => { const on = value.includes(o.value); return <button key={o.value} type="button" aria-pressed={on} onClick={() => onChange(on ? value.filter((x) => x !== o.value) : [...value, o.value])} className={cn("rounded-full border px-2.5 py-1 text-xs font-medium transition-colors", on ? "border-primary bg-primary-soft text-primary" : "border-border text-fg-muted hover:bg-surface-hover")}>{o.label}</button>; })}</div></div>
  );
}

export function EntityList({ cfg }: { cfg: EntityConfig }) {
  const router = useRouter(); const pathname = usePathname(); const sp = useSearchParams(); const qc = useQueryClient(); const toast = useToast(); const ui = useUI();
  const { can } = useAccess(); const { data: me } = useMe(); const isMobile = useMediaQuery("(max-width: 767px)");
  const params = React.useMemo(() => new URLSearchParams(sp.toString()), [sp]);
  const [search, setSearch] = React.useState(params.get("q") ?? "");
  const dsearch = useDebounce(search, 250);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [vis, setVis] = useLocalStorage<string[] | null>(`cols-${cfg.key}`, null);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const visible = cfg.columns.filter((c) => (vis ? vis.includes(c.key) : c.defaultVisible !== false));

  const push = React.useCallback((next: URLSearchParams) => { router.replace(`${pathname}${next.toString() ? "?" + next.toString() : ""}`, { scroll: false }); setSelected(new Set()); }, [router, pathname]);
  const setParam = (k: string, v: string | null) => { const n = new URLSearchParams(params.toString()); v ? n.set(k, v) : n.delete(k); if (k !== "page") n.delete("page"); push(n); };
  React.useEffect(() => { if ((params.get("q") ?? "") !== dsearch) setParam("q", dsearch || null); }, [dsearch]); // eslint-disable-line react-hooks/exhaustive-deps

  const page = Number(params.get("page") ?? 1), perPage = Number(params.get("per_page") ?? 25), sort = params.get("sort") ?? cfg.defaultSort;
  const apiParams = Object.fromEntries([...params.entries()].filter(([k]) => !["page", "per_page", "sort", "view"].includes(k)));
  const key = [cfg.key, { ...apiParams, page, perPage, sort }];
  const list = useQuery({ queryKey: key, queryFn: () => api.page<Row>(cfg.endpoint, { ...apiParams, page, per_page: perPage, sort }), placeholderData: keepPreviousData });
  const views = useQuery({ queryKey: ["views", cfg.entityType], queryFn: () => api.get<SavedView[]>("/api/v1/views", { entity_type: cfg.entityType }) });
  const rows = list.data?.data ?? []; const meta = list.data?.meta;

  const filterKeys = new Set(cfg.filters.flatMap((f) => (f.kind === "range" ? [f.param + "_min", f.param + "_max"] : f.kind === "date" ? [f.param + "_from", f.param + "_to"] : [f.param])));
  const specialKeys = ["follow_up", "stale_days", "closing", "status", "owner_id"];
  const activeFilters = [...params.entries()].filter(([k, v]) => (filterKeys.has(k) || specialKeys.includes(k)) && v);
  const activeViewId = params.get("view");
  const applyView = (id: string, p: Record<string, string>, sortOverride?: string | null) => { const n = new URLSearchParams(); for (const [k, v] of Object.entries(p)) n.set(k === "owner_id" && v === "me" ? k : k, v); n.set("view", id); if (sortOverride) n.set("sort", sortOverride); setSearch(p.q ?? ""); push(n); };

  const update = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Record<string, unknown> }) => api.patch<Row>(`${cfg.endpoint}/${id}`, patch),
    onMutate: async ({ id, patch }) => { await qc.cancelQueries({ queryKey: [cfg.key] }); const prev = qc.getQueriesData<Page<Row>>({ queryKey: [cfg.key] }); qc.setQueriesData<Page<Row>>({ queryKey: [cfg.key] }, (d) => d && { ...d, data: d.data.map((r) => (r.id === id ? { ...r, ...patch } : r)) }); return { prev }; },
    onError: (e, _v, ctx) => { ctx?.prev.forEach(([k, d]) => qc.setQueryData(k, d)); toast.error("Couldn't save change", (e as Error).message); },
    onSettled: () => qc.invalidateQueries({ queryKey: [cfg.key] }),
  });
  const bulk = useMutation({
    mutationFn: (b: { action: string; value?: unknown }) => api.post<{ affected: number }>(`${cfg.endpoint}/bulk`, { ids: [...selected], ...b }),
    onSuccess: (r, b) => { toast.success(b.action === "delete" ? `${r.affected} deleted` : `${r.affected} updated`); setSelected(new Set()); qc.invalidateQueries({ queryKey: [cfg.key] }); qc.invalidateQueries({ queryKey: ["tags"] }); },
    onError: (e) => toast.error("Bulk action failed", (e as Error).message),
  });

  const canEdit = can(`${cfg.key}.update`);
  const ctx = { update: (id: string, patch: Record<string, unknown>) => update.mutate({ id, patch }), canEdit };
  const allOn = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const toggleAll = () => setSelected(allOn ? new Set() : new Set(rows.map((r) => r.id)));
  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const doExport = async () => { const r = await api.raw("GET", `${cfg.endpoint}/export${api.qs({ ...apiParams, sort })}`); if (!r.ok) return toast.error("Export failed"); const u = URL.createObjectURL(await r.blob()); const a = document.createElement("a"); a.href = u; a.download = `${cfg.key}.csv`; a.click(); URL.revokeObjectURL(u); };
  const saveView = async () => { const name = window.prompt("Name this view (e.g. “My hot leads”)"); if (!name?.trim()) return; const v = await api.post<SavedView>("/api/v1/views", { entity_type: cfg.entityType, name: name.trim(), filters: { ...apiParams, ...(search ? { q: search } : {}) }, sort }); qc.invalidateQueries({ queryKey: ["views", cfg.entityType] }); toast.success("View saved"); applyView(v.id, v.filters, v.sort); };
  const hasFilters = activeFilters.length > 0 || !!params.get("q");
  const sortDir = (s?: string) => (!s ? null : sort === s ? "asc" : sort === `-${s}` ? "desc" : null);
  const toggleSort = (s: string) => setParam("sort", sort === s ? `-${s}` : sort === `-${s}` ? null : s);

  const defaultViews = cfg.defaultViews.map((v) => ({ ...v, params: Object.fromEntries(Object.entries(v.params).map(([k, val]) => [k, val.startsWith("date:") ? new Date(Date.now() - Number(val.slice(5)) * 864e5).toISOString().slice(0, 10) : val])) }));
  const saved = views.data ?? [];

  return (
    <PageContainer wide>
      <PageHeader title={cfg.title} description={meta ? `${meta.total.toLocaleString("en-IN")} ${meta.total === 1 ? cfg.singular : cfg.title.toLowerCase()}` : " "}
        actions={<>
          {can("data.import") && <Button variant="secondary" asChild><Link href={`/app/settings/data?import=${cfg.importAs}`}><FileUp /> Import</Link></Button>}
          {can("data.export") && <Button variant="secondary" onClick={doExport}><Download /> Export</Button>}
          {can(`${cfg.key}.create`) && <Button onClick={() => ui.openCreate(cfg.createKind)}><Plus /> New {cfg.singular}</Button>}
        </>}
        tabs={
          <div className="hide-scrollbar -mx-1 flex items-center gap-1 overflow-x-auto px-1">
            {[...defaultViews.map((v) => ({ ...v, saved: false, sort: null as string | null })), ...saved.map((v) => ({ id: v.id, name: v.name, params: v.filters as Record<string, string>, saved: true, sort: v.sort }))].map((v) => {
              const active = activeViewId ? activeViewId === v.id : v.id === "all" && !hasFilters;
              return <button key={v.id} onClick={() => applyView(v.id, v.params, v.sort)} className={cn("flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors", active ? "bg-fg text-bg" : "text-fg-muted hover:bg-surface-hover hover:text-fg")}>{v.saved && <Bookmark className="size-3" />}{v.name}</button>;
            })}
          </div>} />

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <div className="min-w-[200px] flex-1 sm:max-w-sm"><Input icon={<Search />} value={search} onChange={(e) => setSearch(e.target.value)} placeholder={cfg.searchPlaceholder} aria-label={`Search ${cfg.title}`} /></div>
          <Popover>
            <PopoverTrigger asChild><Button variant="secondary" size="md"><Filter /> Filters{activeFilters.length > 0 && <Badge tone="primary">{activeFilters.length}</Badge>}</Button></PopoverTrigger>
            <PopoverContent align="start" className="w-[340px] max-w-[calc(100vw-24px)] space-y-4">
              {cfg.filters.map((f) => <FilterField key={f.param} def={f} params={params} set={setParam} />)}
              <div className="flex justify-between border-t border-border pt-3"><Button variant="ghost" size="sm" onClick={() => { setSearch(""); push(new URLSearchParams()); }}>Clear all</Button><Button variant="soft" size="sm" onClick={saveView}><Bookmark /> Save as view</Button></div>
            </PopoverContent>
          </Popover>
          <DropdownMenu>
            <DropdownTrigger asChild><Button variant="ghost" size="icon" aria-label="Customize columns"><Columns3 /></Button></DropdownTrigger>
            <DropdownContent><DropdownLabel>Columns</DropdownLabel>{cfg.columns.map((c, i) => <DropdownCheckItem key={c.key} checked={visible.some((v) => v.key === c.key)} disabled={i === 0} onSelect={(e) => e.preventDefault()} onCheckedChange={(on) => setVis((cur) => { const base = cur ?? cfg.columns.filter((x) => x.defaultVisible !== false).map((x) => x.key); return on ? [...base, c.key] : base.filter((k) => k !== c.key); })}>{c.label}</DropdownCheckItem>)}</DropdownContent>
          </DropdownMenu>
          {hasFilters && <Button variant="ghost" size="sm" onClick={saveView}><Bookmark /> Save view</Button>}
        </div>
        {activeFilters.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-2 px-3 py-2">
            {activeFilters.map(([k, v]) => <span key={k} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface py-0.5 pl-2.5 pr-1 text-xs"><span className="text-fg-subtle">{k.replace(/_/g, " ")}:</span><span className="font-medium">{v === "me" ? "me" : v.length > 24 ? v.slice(0, 24) + "…" : v}</span><button aria-label={`Remove ${k} filter`} onClick={() => setParam(k, null)} className="rounded-full p-0.5 hover:bg-bg-subtle"><X className="size-3" /></button></span>)}
          </div>
        )}

        <div className="relative">
          {list.isLoading ? <div className="p-6"><SkeletonRows rows={8} /></div>
            : list.isError ? <ErrorState compact kind={(list.error as { status?: number }).status === 0 ? "network" : (list.error as { status?: number }).status === 403 ? "permission" : "unavailable"} onRetry={() => list.refetch()} />
            : rows.length === 0 ? (hasFilters ? <EmptyState compact title={`No ${cfg.title.toLowerCase()} match`} description="Try changing or clearing your filters." action={<Button variant="secondary" onClick={() => { setSearch(""); push(new URLSearchParams()); }}>Clear filters</Button>} /> : <EmptyState icon={<Plus />} title={cfg.empty.title} description={cfg.empty.description} action={can(`${cfg.key}.create`) ? <Button onClick={() => ui.openCreate(cfg.createKind)}><Plus /> Create {cfg.singular}</Button> : undefined} secondary={can("data.import") ? <Button variant="secondary" asChild><Link href={`/app/settings/data?import=${cfg.importAs}`}><FileUp /> Import CSV</Link></Button> : undefined} />)
            : isMobile ? (
              <ul className="divide-y divide-border">{rows.map((r) => { const m = cfg.mobile(r); return <li key={r.id}><Link href={cfg.href(r)} className="flex items-center gap-3 px-4 py-3.5 active:bg-surface-hover"><div className="min-w-0 flex-1"><div className="truncate font-medium">{m.title}</div>{m.subtitle && <div className="truncate text-[13px] text-fg-muted">{m.subtitle}</div>}</div>{m.meta}<ChevronRight className="size-4 shrink-0 text-fg-subtle" /></Link></li>; })}</ul>
            ) : (
              <div className={cn("overflow-x-auto transition-opacity", list.isFetching && "opacity-60")}>
                <Table>
                  <THead><TR className="border-b-0"><TH className="w-10 pl-4"><Checkbox checked={allOn ? true : selected.size ? "indeterminate" : false} onCheckedChange={toggleAll} aria-label="Select all" /></TH>
                    {visible.map((c) => <TH key={c.key} sortable={!!c.sort} sortDir={sortDir(c.sort)} onSort={() => toggleSort(c.sort!)} className={c.align === "right" ? "text-right" : undefined}>{c.label}</TH>)}</TR></THead>
                  <tbody>{rows.map((r) => (
                    <TR key={r.id} className={cn("group cursor-pointer hover:bg-surface-hover", selected.has(r.id) && "bg-primary-soft/40")} onClick={(e) => { if ((e.target as HTMLElement).closest("button,a,input,[role=checkbox],[role=combobox],[role=menuitem]")) return; router.push(cfg.href(r)); }}>
                      <TD className="pl-4"><Checkbox checked={selected.has(r.id)} onCheckedChange={() => toggle(r.id)} aria-label="Select row" /></TD>
                      {visible.map((c) => <TD key={c.key} className={cn(c.align === "right" && "text-right", c.className)}>{c.render(r, ctx)}</TD>)}
                    </TR>))}</tbody>
                </Table>
              </div>
            )}
        </div>

        {meta && meta.total > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-[13px] text-fg-muted">
            <div className="flex items-center gap-2">Rows<NativeSelect className="h-8 w-[72px] text-[13px]" value={perPage} onChange={(e) => setParam("per_page", e.target.value === "25" ? null : e.target.value)} aria-label="Rows per page">{PER_PAGE.map((n) => <option key={n}>{n}</option>)}</NativeSelect></div>
            <span className="tabular">{(page - 1) * perPage + 1}–{Math.min(page * perPage, meta.total)} of {meta.total.toLocaleString("en-IN")}</span>
            <div className="flex gap-1"><Button variant="secondary" size="icon-sm" disabled={page <= 1} onClick={() => setParam("page", String(page - 1))} aria-label="Previous page"><ChevronLeft /></Button><Button variant="secondary" size="icon-sm" disabled={page >= meta.pages} onClick={() => setParam("page", String(page + 1))} aria-label="Next page"><ChevronRight /></Button></div>
          </div>
        )}
      </Card>

      <AnimatePresence>
        {selected.size > 0 && (
          <motion.div initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 80, opacity: 0 }} transition={{ type: "spring", stiffness: 420, damping: 36 }} className="fixed inset-x-0 bottom-24 z-40 flex justify-center px-4 md:bottom-6">
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-fg px-3 py-2.5 text-bg shadow-lg">
              <span className="px-2 text-sm font-medium">{selected.size} selected</span>
              {cfg.bulk.includes("assign") && can(`${cfg.key}.update`) && (
                <Popover><PopoverTrigger asChild><Button size="sm" variant="ghost" className="text-bg hover:bg-white/10 hover:text-bg"><UserCog /> Assign</Button></PopoverTrigger><PopoverContent className="w-64"><MemberSelect value={null} noneLabel="Unassign" onChange={(v) => bulk.mutate({ action: "assign", value: v })} /></PopoverContent></Popover>)}
              {cfg.bulk.includes("tags") && can(`${cfg.key}.update`) && <BulkTags onAdd={(t) => bulk.mutate({ action: "add_tags", value: t })} />}
              {cfg.bulk.includes("status") && can(`${cfg.key}.update`) && (
                <DropdownMenu><DropdownTrigger asChild><Button size="sm" variant="ghost" className="text-bg hover:bg-white/10 hover:text-bg">Status</Button></DropdownTrigger><DropdownContent align="center" side="top">{(me?.workspace?.lead_statuses ?? []).filter((s) => s.key !== "converted").map((s) => <DropdownItem key={s.key} onSelect={() => bulk.mutate({ action: "set", value: { status: s.key } })}>{s.label}</DropdownItem>)}</DropdownContent></DropdownMenu>)}
              {can(`${cfg.key}.delete`) && <Button size="sm" variant="ghost" className="text-red-300 hover:bg-white/10 hover:text-red-200" onClick={() => setConfirmDelete(true)}><Trash2 /> Delete</Button>}
              <Button size="icon-sm" variant="ghost" className="text-bg hover:bg-white/10 hover:text-bg" onClick={() => setSelected(new Set())} aria-label="Clear selection"><X /></Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <ConfirmDialog open={confirmDelete} onOpenChange={setConfirmDelete} title={`Delete ${selected.size} ${selected.size === 1 ? cfg.singular : cfg.title.toLowerCase()}?`} description="They'll be removed from your workspace. This is recorded in the audit log." confirmLabel="Delete" onConfirm={() => bulk.mutateAsync({ action: "delete" })} />
    </PageContainer>
  );
}

function BulkTags({ onAdd }: { onAdd: (t: string[]) => void }) {
  const [v, setV] = React.useState<string[]>([]);
  return <Popover><PopoverTrigger asChild><Button size="sm" variant="ghost" className="text-bg hover:bg-white/10 hover:text-bg"><Tag /> Tag</Button></PopoverTrigger><PopoverContent className="w-72 space-y-3 text-fg"><TagInput value={v} onChange={setV} placeholder="Add tags…" /><Button size="sm" className="w-full" disabled={!v.length} onClick={() => { onAdd(v); setV([]); }}>Apply tags</Button></PopoverContent></Popover>;
}
export { DropdownSeparator, Select };
