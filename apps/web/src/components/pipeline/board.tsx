"use client";
import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, closestCorners, useDroppable, useSensor, useSensors, type DragEndEvent, type DragOverEvent, type DragStartEvent } from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CalendarDays, Flame, GripVertical, Plus, Search, Settings2, Trophy } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, Button, ConfirmDialog, EmptyState, ErrorState, Input, NativeSelect, Select, Skeleton, Tooltip, cn, formatMoney, formatMoneyCompact, useDebounce, useLocalStorage, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { celebrate } from "@/lib/confetti";
import { useAccess, useInvalidate, keys, usePipelines } from "@/lib/queries";
import type { Deal, Pipeline } from "@/lib/types";
import { MemberSelect } from "../forms/fields";
import { ScorePill } from "../list/cells";
import { PageContainer, PageHeader } from "../shell/page";
import { useUI } from "../shell/ui-context";

type Column = { stage: { id: string; name: string; kind: "open" | "won" | "lost"; color: string | null; probability: number }; count: number; total_value: number; weighted_value: number; deals: Deal[]; has_more: boolean };
type Board = { pipeline: Pipeline; columns: Column[] };
const PRIO_DOT: Record<string, string> = { urgent: "bg-danger", high: "bg-warning", medium: "bg-info", low: "bg-border-strong" };

function DealCard({ deal, overlay }: { deal: Deal; overlay?: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: deal.id, data: { type: "deal", stageId: deal.stage_id } });
  const overdue = deal.status === "open" && deal.expected_close_date && new Date(deal.expected_close_date + "T23:59:59") < new Date();
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} {...attributes} {...listeners}
      className={cn("group touch-manipulation cursor-grab rounded-xl border border-border bg-surface p-3.5 shadow-xs transition-shadow active:cursor-grabbing", isDragging && !overlay && "opacity-30", overlay && "rotate-2 cursor-grabbing shadow-lg ring-2 ring-primary/40", !isDragging && "hover:border-border-strong hover:shadow-md")}>
      <div className="flex items-start justify-between gap-2">
        <Link href={`/app/deals/${deal.id}`} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()} className="line-clamp-2 text-[13.5px] font-semibold leading-snug hover:text-primary">{deal.name}</Link>
        <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", PRIO_DOT[deal.priority])} title={`${deal.priority} priority`} />
      </div>
      <p className="mt-0.5 truncate text-xs text-fg-muted">{deal.company?.name ?? "No company"}</p>
      <p className="tabular mt-2.5 text-[15px] font-semibold tracking-tight">{formatMoney(deal.value, deal.currency)}</p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className={cn("flex items-center gap-1 text-xs", overdue ? "font-medium text-danger" : "text-fg-subtle")}>{deal.expected_close_date ? <><CalendarDays className="size-3.5" />{new Date(deal.expected_close_date + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</> : <span>No close date</span>}</span>
        <span className="flex items-center gap-2">{deal.lead_score > 0 && <Tooltip content={`Lead score ${deal.lead_score}`}><span><ScorePill score={deal.lead_score} /></span></Tooltip>}<Avatar name={deal.owner?.name} size={22} /></span>
      </div>
    </div>
  );
}

function ColumnView({ col, ids, deals, onAdd, canCreate }: { col: Column; ids: string[]; deals: Deal[]; onAdd: () => void; canCreate: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: `col:${col.stage.id}`, data: { type: "column", stageId: col.stage.id } });
  const tone = col.stage.kind === "won" ? "text-success" : col.stage.kind === "lost" ? "text-danger" : "text-fg";
  return (
    <section aria-label={col.stage.name} className="flex w-[300px] shrink-0 snap-start flex-col rounded-2xl bg-bg-subtle/70 sm:w-[308px]">
      <header className="flex items-center justify-between gap-2 px-4 pb-2 pt-3.5">
        <div className="min-w-0"><h2 className="flex items-center gap-2 text-[13px] font-semibold"><span className="size-2.5 rounded-full" style={{ background: col.stage.color ?? "var(--fg-subtle)" }} /><span className={cn("truncate", tone)}>{col.stage.name}</span><span className="rounded-full bg-surface px-1.5 text-xs font-medium text-fg-muted">{deals.length}{col.has_more ? "+" : ""}</span></h2>
          <p className="tabular mt-0.5 text-xs text-fg-muted"><Tooltip content={`${formatMoney(col.weighted_value)} weighted`}><span>{formatMoneyCompact(col.total_value)}</span></Tooltip></p></div>
        {canCreate && col.stage.kind === "open" && <Tooltip content="Add deal"><Button variant="ghost" size="icon-sm" onClick={onAdd} aria-label={`Add deal to ${col.stage.name}`}><Plus /></Button></Tooltip>}
      </header>
      <div ref={setNodeRef} className={cn("flex min-h-[120px] flex-1 flex-col gap-2.5 overflow-y-auto rounded-b-2xl p-2.5 pt-1 transition-colors", isOver && "bg-primary-soft/50")} style={{ maxHeight: "calc(100dvh - 330px)" }}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>{deals.map((d) => <DealCard key={d.id} deal={d} />)}</SortableContext>
        {deals.length === 0 && <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border-strong py-8 text-xs text-fg-subtle">{col.stage.kind === "won" ? "Drop here when you win 🎉" : col.stage.kind === "lost" ? "Drop here if lost" : "Drop deals here"}</div>}
      </div>
    </section>
  );
}

export function PipelineBoard() {
  const qc = useQueryClient(); const toast = useToast(); const ui = useUI(); const { can } = useAccess(); const inv = useInvalidate();
  const pipelines = usePipelines();
  const [pid, setPid] = useLocalStorage<string | null>("pipeline-id", null);
  const [search, setSearch] = React.useState(""); const dsearch = useDebounce(search, 250); const [owner, setOwner] = React.useState<string | null>(null); const [priority, setPriority] = React.useState("");
  const current = pipelines.data?.find((p) => p.id === pid) ?? pipelines.data?.find((p) => p.is_default) ?? pipelines.data?.[0];
  const key = ["board", current?.id, dsearch, owner, priority];
  const board = useQuery({ queryKey: key, enabled: !!current, queryFn: () => api.get<Board>(`/api/v1/pipelines/${current!.id}/board`, { q: dsearch, owner_id: owner, priority }), refetchInterval: 60_000 });
  const [cols, setCols] = React.useState<Record<string, Deal[]>>({});
  const [active, setActive] = React.useState<Deal | null>(null);
  const [lost, setLost] = React.useState<{ dealId: string; stageId: string; position?: number } | null>(null);
  React.useEffect(() => { if (board.data && !active) setCols(Object.fromEntries(board.data.columns.map((c) => [c.stage.id, c.deals]))); }, [board.data, active]);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const findCol = (id: string) => (id.startsWith("col:") ? id.slice(4) : Object.keys(cols).find((c) => cols[c].some((d) => d.id === id)));

  const onStart = (e: DragStartEvent) => setActive(Object.values(cols).flat().find((d) => d.id === e.active.id) ?? null);
  const onOver = (e: DragOverEvent) => {
    const { active: a, over } = e; if (!over) return;
    const from = findCol(String(a.id)), to = findCol(String(over.id)); if (!from || !to || from === to) return;
    setCols((c) => {
      const item = c[from].find((d) => d.id === a.id)!; const target = c[to]; const overIdx = target.findIndex((d) => d.id === over.id);
      const idx = overIdx >= 0 ? overIdx : target.length;
      return { ...c, [from]: c[from].filter((d) => d.id !== a.id), [to]: [...target.slice(0, idx), { ...item, stage_id: to }, ...target.slice(idx)] };
    });
  };
  const persist = async (dealId: string, stageId: string, position?: number, lostReason?: string) => {
    try {
      const r = await api.post<Deal>(`/api/v1/deals/${dealId}/move`, { stage_id: stageId, position, lost_reason: lostReason });
      if (r.status === "won") { celebrate(); toast.success("Deal won 🎉", `${r.name} — ${formatMoney(r.value, r.currency)}`); } else if (r.status === "lost") toast.toast({ tone: "info", title: "Deal marked as lost", description: r.name });
      inv(["deals"], ["dashboard"], ["timeline"], ["record"]);
    } catch (e) { toast.error("Couldn't move deal", (e as Error).message); }
    qc.invalidateQueries({ queryKey: ["board"] });
  };
  const onEnd = (e: DragEndEvent) => {
    const { active: a, over } = e; const deal = active; setActive(null);
    if (!over || !deal) { qc.invalidateQueries({ queryKey: ["board"] }); return; }
    const to = findCol(String(over.id)); if (!to) return;
    let list = cols[to]; const oldIdx = list.findIndex((d) => d.id === a.id); const overIdx = list.findIndex((d) => d.id === over.id);
    if (oldIdx >= 0 && overIdx >= 0 && oldIdx !== overIdx) { const next = [...list]; const [m] = next.splice(oldIdx, 1); next.splice(overIdx, 0, m); list = next; setCols((c) => ({ ...c, [to]: next })); }
    const idx = list.findIndex((d) => d.id === a.id);
    const prev = list[idx - 1]?.position, next = list[idx + 1]?.position;
    const position = prev != null && next != null ? (Number(prev) + Number(next)) / 2 : prev != null ? Number(prev) + 1000 : next != null ? Number(next) - 1000 : 1000;
    const stage = board.data?.columns.find((c) => c.stage.id === to)?.stage;
    if (to === deal.stage.id && oldIdx === overIdx) return;
    if (stage?.kind === "lost" && deal.stage.id !== to) { setLost({ dealId: deal.id, stageId: to, position }); return; }
    persist(deal.id, to, position);
  };

  const totals = board.data?.columns.filter((c) => c.stage.kind === "open").reduce((a, c) => ({ v: a.v + c.total_value, w: a.w + c.weighted_value, n: a.n + c.count }), { v: 0, w: 0, n: 0 });
  const cur = current?.currency ?? "INR";
  return (
    <PageContainer wide className="!pb-4">
      <PageHeader title="Pipeline" description={totals ? `${totals.n} open deals · ${formatMoneyCompact(totals.v, cur)} total · ${formatMoneyCompact(totals.w, cur)} weighted` : " "}
        actions={<>
          {(pipelines.data?.length ?? 0) > 1 && <div className="w-48"><Select value={current?.id} onValueChange={setPid} options={pipelines.data!.map((p) => ({ value: p.id, label: p.name }))} /></div>}
          {can("pipelines.update") && <Button variant="secondary" asChild><Link href="/app/settings/pipelines"><Settings2 /> Stages</Link></Button>}
          {can("deals.create") && <Button onClick={() => ui.openCreate("deal", { stage_id: current?.stages.find((s) => s.kind === "open")?.id })}><Plus /> New deal</Button>}
        </>} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="w-full sm:w-64"><Input icon={<Search />} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search deals…" aria-label="Search deals" /></div>
        <div className="w-48"><MemberSelect value={owner} onChange={setOwner} noneLabel="All owners" size="sm" /></div>
        <NativeSelect className="h-8 w-36 text-[13px]" value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority"><option value="">All priorities</option>{["urgent", "high", "medium", "low"].map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}</NativeSelect>
      </div>
      {board.isError ? <ErrorState kind="unavailable" onRetry={() => board.refetch()} />
        : board.isLoading || !board.data ? <div className="flex gap-4 overflow-hidden">{[0, 1, 2, 3].map((i) => <div key={i} className="w-[300px] shrink-0 space-y-3 rounded-2xl bg-bg-subtle/70 p-3"><Skeleton className="h-6 w-28" />{[0, 1].map((j) => <Skeleton key={j} className="h-28" />)}</div>)}</div>
        : board.data.columns.every((c) => c.count === 0) && !dsearch && !owner && !priority ? <EmptyState icon={<Trophy />} title="No deals yet" description="Create your first deal and start tracking your sales pipeline." action={can("deals.create") ? <Button onClick={() => ui.openCreate("deal")}><Plus /> Create Deal</Button> : undefined} />
        : (
          <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={onStart} onDragOver={onOver} onDragEnd={onEnd} onDragCancel={() => { setActive(null); qc.invalidateQueries({ queryKey: ["board"] }); }}>
            <div className="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-4 sm:-mx-8 sm:px-8" role="region" aria-label="Pipeline board">
              {board.data.columns.map((c) => <ColumnView key={c.stage.id} col={c} deals={cols[c.stage.id] ?? c.deals} ids={(cols[c.stage.id] ?? c.deals).map((d) => d.id)} canCreate={can("deals.create")} onAdd={() => ui.openCreate("deal", { stage_id: c.stage.id })} />)}
            </div>
            <DragOverlay dropAnimation={{ duration: 180 }}>{active ? <DealCard deal={active} overlay /> : null}</DragOverlay>
          </DndContext>
        )}
      <ConfirmDialog open={!!lost} onOpenChange={(o) => { if (!o) { setLost(null); qc.invalidateQueries({ queryKey: ["board"] }); } }} title="Mark deal as lost?" description="Tell your team why — it makes win/loss reports far more useful." requireReason confirmLabel="Mark as lost" onConfirm={async ({ reason }) => { await persist(lost!.dealId, lost!.stageId, lost!.position, reason); setLost(null); }} />
    </PageContainer>
  );
}
export { GripVertical, Flame, Badge, keys, motion };
