"use client";
import { DndContext, DragOverlay, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, CheckCircle2, Columns3, List, Plus } from "lucide-react";
import * as React from "react";
import { Avatar, Badge, Button, Card, EmptyState, ErrorState, Input, Segmented, SkeletonRows, cn, formatDate, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/constants";
import { useAccess } from "@/lib/queries";
import type { Task } from "@/lib/types";
import { CalendarView } from "../calendar/calendar";
import { MemberSelect } from "../forms/fields";
import { TaskRow, useToggleTask } from "../records/related";
import { PageContainer, PageHeader } from "../shell/page";
import { useUI } from "../shell/ui-context";

type V = "list" | "board" | "calendar";
const SECTIONS = [["overdue", "Overdue", "text-danger"], ["today", "Due today", "text-primary"], ["upcoming", "Upcoming", "text-fg"], ["no_date", "No due date", "text-fg-muted"]] as const;
const COLS = [["todo", "To do"], ["in_progress", "In progress"], ["completed", "Completed"]] as const;

function QuickAdd() {
  const qc = useQueryClient(); const toast = useToast(); const [title, setTitle] = React.useState("");
  const add = useMutation({ mutationFn: (t: string) => api.post("/api/v1/tasks", { title: t, due_at: new Date(new Date().setHours(17, 0, 0, 0)).toISOString() }), onSuccess: () => { setTitle(""); qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["tasks-summary-badge"] }); toast.success("Task added for today"); }, onError: (e) => toast.error("Couldn't add task", (e as Error).message) });
  return <form onSubmit={(e) => { e.preventDefault(); if (title.trim()) add.mutate(title.trim()); }} className="flex gap-2"><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Quick add a task for today… press Enter" aria-label="Quick add task" icon={<Plus />} /><Button type="submit" disabled={!title.trim()} loading={add.isPending}>Add</Button></form>;
}

function BoardCard({ t, overlay }: { t: Task; overlay?: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: t.id });
  const overdue = t.status !== "completed" && t.due_at && new Date(t.due_at) < new Date();
  return <div ref={setNodeRef} {...attributes} {...listeners} className={cn("cursor-grab touch-manipulation rounded-xl border border-border bg-surface p-3.5 shadow-xs active:cursor-grabbing", isDragging && !overlay && "opacity-30", overlay && "rotate-2 shadow-lg ring-2 ring-primary/40")}>
    <p className={cn("text-[13.5px] font-medium", t.status === "completed" && "text-fg-subtle line-through")}>{t.title}</p>
    {t.related[0] && <p className="mt-0.5 truncate text-xs text-fg-subtle">{t.related[0].label}</p>}
    <div className="mt-3 flex items-center justify-between"><span className={cn("text-xs", overdue ? "font-medium text-danger" : "text-fg-subtle")}>{t.due_at ? formatDate(t.due_at, "datetime") : "No date"}</span><span className="flex items-center gap-2">{t.priority !== "medium" && <Badge tone={t.priority === "urgent" ? "danger" : t.priority === "high" ? "warning" : "neutral"}>{label(t.priority)}</Badge>}{t.assignee && <Avatar name={t.assignee.name} size={22} />}</span></div></div>;
}
function BoardCol({ id, title, tasks }: { id: string; title: string; tasks: Task[] }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return <section aria-label={title} className="w-[300px] shrink-0 rounded-2xl bg-bg-subtle/70"><h2 className="flex items-center justify-between px-4 pb-2 pt-3.5 text-[13px] font-semibold">{title}<span className="rounded-full bg-surface px-2 text-xs font-medium text-fg-muted">{tasks.length}</span></h2>
    <div ref={setNodeRef} className={cn("min-h-[140px] space-y-2.5 rounded-b-2xl p-2.5 pt-1 transition-colors", isOver && "bg-primary-soft/50")}>{tasks.map((t) => <BoardCard key={t.id} t={t} />)}{!tasks.length && <p className="rounded-xl border border-dashed border-border-strong py-8 text-center text-xs text-fg-subtle">Drop tasks here</p>}</div></section>;
}

export function TasksPage() {
  const ui = useUI(); const { can } = useAccess(); const qc = useQueryClient(); const toast = useToast(); const toggle = useToggleTask();
  const [view, setView] = React.useState<V>("list"); const [who, setWho] = React.useState<"mine" | "all">("mine"); const [assignee, setAssignee] = React.useState<string | null>(null);
  const params = who === "mine" ? { assignee_id: "me" } : assignee ? { assignee_id: assignee } : {};
  const summary = useQuery({ queryKey: ["tasks-summary", who], queryFn: () => api.get<Record<string, number>>("/api/v1/tasks/summary", { mine: who === "mine" ? "true" : undefined }) });
  const lists = useQuery({
    queryKey: ["tasks", "grouped", who, assignee], enabled: view === "list", placeholderData: keepPreviousData,
    queryFn: async () => { const [overdue, today, upcoming, no_date, done] = await Promise.all([...["overdue", "today", "upcoming", "no_date"].map((v) => api.page<Task>("/api/v1/tasks", { ...params, view: v, per_page: 50, sort: "due_at" })), api.page<Task>("/api/v1/tasks", { ...params, status: "completed", per_page: 10, sort: "-due_at" })]); return { overdue: overdue.data, today: today.data, upcoming: upcoming.data, no_date: no_date.data, done: done.data }; },
  });
  const board = useQuery({ queryKey: ["tasks", "board", who, assignee], enabled: view === "board", queryFn: () => api.page<Task>("/api/v1/tasks", { ...params, per_page: 100, sort: "due_at" }), placeholderData: keepPreviousData });
  const [active, setActive] = React.useState<Task | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const move = async (e: DragEndEvent) => {
    const t = active; setActive(null); const status = e.over?.id as Task["status"] | undefined; if (!t || !status || status === t.status) return;
    qc.setQueryData(["tasks", "board", who, assignee], (d: { data: Task[]; meta: unknown } | undefined) => d && { ...d, data: d.data.map((x) => (x.id === t.id ? { ...x, status } : x)) });
    try { await api.patch(`/api/v1/tasks/${t.id}`, { status }); qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["tasks-summary"] }); qc.invalidateQueries({ queryKey: ["tasks-summary-badge"] }); if (status === "completed") toast.success("Task completed"); } catch (err) { toast.error("Couldn't move task", (err as Error).message); qc.invalidateQueries({ queryKey: ["tasks"] }); }
  };
  const total = lists.data ? Object.values(lists.data).reduce((a, l) => a + l.length, 0) : 0;
  return (
    <PageContainer wide>
      <PageHeader title="Tasks" description="Follow-ups and to-dos, sorted by what's due."
        actions={<>
          <Segmented size="sm" value={who} onChange={setWho} options={[{ value: "mine", label: "Mine" }, { value: "all", label: "Everyone" }]} />
          {who === "all" && <div className="w-44"><MemberSelect value={assignee} onChange={setAssignee} noneLabel="All assignees" size="sm" /></div>}
          <Segmented size="sm" value={view} onChange={setView} options={[{ value: "list", label: "List", icon: <List /> }, { value: "board", label: "Board", icon: <Columns3 /> }, { value: "calendar", label: "Calendar", icon: <CalendarDays /> }]} />
          {can("tasks.create") && <Button onClick={() => ui.openCreate("task")}><Plus /> New task</Button>}
        </>} />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[["overdue", "Overdue", "text-danger"], ["today", "Due today", "text-primary"], ["upcoming", "Upcoming", "text-fg"], ["completed", "Completed", "text-success"]].map(([k, l, c]) => <Card key={k} className="p-4"><p className="text-xs font-medium text-fg-muted">{l}</p><p className={cn("tabular mt-1 text-2xl font-semibold", c)}>{summary.data?.[k] ?? "–"}</p></Card>)}
      </div>
      {view === "list" && (
        <div className="space-y-5">
          {can("tasks.create") && <QuickAdd />}
          {lists.isLoading ? <SkeletonRows rows={6} /> : lists.isError ? <ErrorState compact onRetry={() => lists.refetch()} kind="unavailable" /> : total === 0 ? <EmptyState icon={<CheckCircle2 />} title="No tasks yet" description="Add a task above — or create follow-ups from any lead, contact or deal." /> : (
            <>
              {SECTIONS.map(([k, l, c]) => lists.data![k].length ? <section key={k}><h2 className={cn("mb-2 flex items-center gap-2 text-sm font-semibold", c)}>{l}<span className="rounded-full bg-bg-subtle px-2 text-xs font-medium text-fg-muted">{lists.data![k].length}</span></h2><Card><ul className="divide-y divide-border p-1">{lists.data![k].map((t) => <TaskRow key={t.id} t={t} onToggle={(x) => toggle.mutate(x)} />)}</ul></Card></section> : null)}
              {lists.data!.done.length > 0 && <details><summary className="cursor-pointer text-sm font-semibold text-fg-muted">Recently completed ({lists.data!.done.length})</summary><Card className="mt-2"><ul className="divide-y divide-border p-1">{lists.data!.done.map((t) => <TaskRow key={t.id} t={t} onToggle={(x) => toggle.mutate(x)} />)}</ul></Card></details>}
            </>)}
        </div>)}
      {view === "board" && (board.isLoading ? <SkeletonRows rows={6} /> : (
        <DndContext sensors={sensors} onDragStart={(e) => setActive(board.data?.data.find((t) => t.id === e.active.id) ?? null)} onDragEnd={move} onDragCancel={() => setActive(null)}>
          <div className="-mx-4 flex gap-4 overflow-x-auto px-4 pb-4 sm:-mx-8 sm:px-8">{COLS.map(([k, l]) => <BoardCol key={k} id={k} title={l} tasks={(board.data?.data ?? []).filter((t) => t.status === k)} />)}</div>
          <DragOverlay>{active ? <BoardCard t={active} overlay /> : null}</DragOverlay>
        </DndContext>))}
      {view === "calendar" && <CalendarView mine={who === "mine"} taskOnly defaultView="month" />}
    </PageContainer>
  );
}
