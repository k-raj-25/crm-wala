"use client";
import { useQuery } from "@tanstack/react-query";
import { addDays, addMonths, endOfMonth, endOfWeek, format, isSameDay, isSameMonth, isToday, startOfDay, startOfMonth, startOfWeek } from "date-fns";
import { Calendar as CalIcon, CheckSquare, ChevronLeft, ChevronRight, Phone, Repeat, Flag, Video } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Button, Dialog, DialogContent, ErrorState, Segmented, cn, formatDate } from "@crm/ui";
import { api } from "@/lib/api";
import type { CalendarEvent } from "@/lib/types";
import { useToggleTask } from "../records/related";
import { useUI } from "../shell/ui-context";

export type View = "day" | "week" | "month";
const KIND: Record<CalendarEvent["kind"], { label: string; color: string; icon: React.ElementType }> = {
  meeting: { label: "Meeting", color: "var(--series-1)", icon: Video }, call: { label: "Call", color: "var(--series-3)", icon: Phone }, task: { label: "Task", color: "var(--series-7)", icon: CheckSquare },
  follow_up: { label: "Follow-up", color: "var(--series-2)", icon: Repeat }, deadline: { label: "Deadline", color: "var(--series-8)", icon: Flag },
};
const HOUR = 56;
const href = (e: CalendarEvent) => ({ lead: `/app/leads/${e.entity.id}`, task: "/app/tasks", meeting: "/app/calendar", call: "/app/calendar" } as Record<string, string>)[e.entity.type];

export function range(view: View, date: Date) {
  if (view === "day") return [startOfDay(date), addDays(startOfDay(date), 1)] as const;
  if (view === "week") { const s = startOfWeek(date, { weekStartsOn: 1 }); return [s, addDays(endOfWeek(date, { weekStartsOn: 1 }), 0)] as const; }
  const s = startOfWeek(startOfMonth(date), { weekStartsOn: 1 }); return [s, endOfWeek(endOfMonth(date), { weekStartsOn: 1 })] as const;
}

function Chip({ e, onClick, compact }: { e: CalendarEvent; onClick: () => void; compact?: boolean }) {
  const k = KIND[e.kind]; const done = e.status === "completed";
  return <button onClick={(ev) => { ev.stopPropagation(); onClick(); }} className={cn("flex w-full items-center gap-1.5 truncate rounded-md px-1.5 py-0.5 text-left text-xs font-medium transition-colors hover:brightness-95", done && "line-through opacity-60")} style={{ background: `color-mix(in srgb, ${k.color} 15%, transparent)`, color: `color-mix(in srgb, ${k.color} 70%, var(--fg))` }} title={e.title}>
    <span className="size-1.5 shrink-0 rounded-full" style={{ background: k.color }} />{!compact && <span className="tabular shrink-0 opacity-70">{format(new Date(e.start), "h:mma").toLowerCase()}</span>}<span className="truncate">{e.title}</span></button>;
}

function layout(events: CalendarEvent[]) {
  const sorted = [...events].sort((a, b) => a.start.localeCompare(b.start));
  const lanes: number[] = []; const out: (CalendarEvent & { lane: number; lanes: number })[] = [];
  for (const e of sorted) {
    const s = new Date(e.start).getTime(); let i = lanes.findIndex((end) => end <= s); if (i === -1) { i = lanes.length; lanes.push(0); }
    lanes[i] = Math.max(new Date(e.end).getTime(), s + 30 * 60000); out.push({ ...e, lane: i, lanes: 0 });
  }
  const n = lanes.length || 1; return out.map((e) => ({ ...e, lanes: n }));
}

function TimeGrid({ days, events, onEvent, onSlot }: { days: Date[]; events: CalendarEvent[]; onEvent: (e: CalendarEvent) => void; onSlot: (d: Date) => void }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [now, setNow] = React.useState(new Date());
  React.useEffect(() => { ref.current?.scrollTo({ top: HOUR * 7.5 }); const t = setInterval(() => setNow(new Date()), 60000); return () => clearInterval(t); }, []);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="grid border-b border-border" style={{ gridTemplateColumns: `56px repeat(${days.length}, 1fr)` }}>
        <div />{days.map((d) => <div key={d.toISOString()} className="border-l border-border py-2 text-center"><p className="text-xs font-medium uppercase text-fg-subtle">{format(d, "EEE")}</p><p className={cn("mx-auto mt-0.5 flex size-8 items-center justify-center rounded-full text-lg font-semibold", isToday(d) && "bg-primary text-primary-fg")}>{format(d, "d")}</p></div>)}
      </div>
      <div ref={ref} className="min-h-0 flex-1 overflow-y-auto" style={{ maxHeight: "calc(100dvh - 330px)" }}>
        <div className="relative grid" style={{ gridTemplateColumns: `56px repeat(${days.length}, 1fr)`, height: HOUR * 24 }}>
          <div>{Array.from({ length: 24 }).map((_, h) => <div key={h} className="relative" style={{ height: HOUR }}><span className="absolute -top-2 right-2 text-[11px] text-fg-subtle">{h === 0 ? "" : format(new Date(2020, 0, 1, h), "h a")}</span></div>)}</div>
          {days.map((d) => {
            const evs = layout(events.filter((e) => isSameDay(new Date(e.start), d)));
            return (
              <div key={d.toISOString()} className="relative border-l border-border" onClick={(ev) => { const r = (ev.currentTarget as HTMLElement).getBoundingClientRect(); const mins = Math.floor(((ev.clientY - r.top) / HOUR) * 60 / 30) * 30; const dt = new Date(d); dt.setHours(0, mins, 0, 0); onSlot(dt); }}>
                {Array.from({ length: 24 }).map((_, h) => <div key={h} className="border-b border-border/60" style={{ height: HOUR }} />)}
                {isToday(d) && <div className="pointer-events-none absolute inset-x-0 z-10 border-t-2 border-danger" style={{ top: (now.getHours() + now.getMinutes() / 60) * HOUR }}><span className="absolute -left-1 -top-[5px] size-2 rounded-full bg-danger" /></div>}
                {evs.map((e) => {
                  const s = new Date(e.start); const top = (s.getHours() + s.getMinutes() / 60) * HOUR; const dur = Math.max((new Date(e.end).getTime() - s.getTime()) / 3600000, 0.5); const k = KIND[e.kind];
                  return <button key={e.id} onClick={(ev) => { ev.stopPropagation(); onEvent(e); }} className={cn("absolute z-[5] overflow-hidden rounded-md border-l-[3px] px-2 py-1 text-left text-xs transition-shadow hover:z-20 hover:shadow-md", e.status === "completed" && "opacity-60")} style={{ top, height: dur * HOUR - 2, left: `calc(${(e.lane / e.lanes) * 100}% + 2px)`, width: `calc(${100 / e.lanes}% - 4px)`, borderColor: k.color, background: `color-mix(in srgb, ${k.color} 14%, var(--surface))`, color: "var(--fg)" }}>
                    <p className="truncate font-semibold">{e.title}</p><p className="tabular truncate text-fg-muted">{format(s, "h:mm a")}</p></button>;
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function MonthGrid({ date, events, onEvent, onDay }: { date: Date; events: CalendarEvent[]; onEvent: (e: CalendarEvent) => void; onDay: (d: Date) => void }) {
  const [s, e] = range("month", date); const days: Date[] = []; for (let d = s; d <= e; d = addDays(d, 1)) days.push(d);
  return (
    <div>
      <div className="grid grid-cols-7 border-b border-border">{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="px-2 py-2 text-xs font-medium uppercase text-fg-subtle">{d}</div>)}</div>
      <div className="grid grid-cols-7">
        {days.map((d) => {
          const evs = events.filter((x) => isSameDay(new Date(x.start), d));
          return (
            <div key={d.toISOString()} onClick={() => onDay(d)} className={cn("min-h-[104px] cursor-pointer border-b border-r border-border p-1.5 transition-colors hover:bg-surface-hover/60 [&:nth-child(7n)]:border-r-0", !isSameMonth(d, date) && "bg-bg-subtle/40")}>
              <p className={cn("mb-1 flex size-6 items-center justify-center rounded-full text-xs font-medium", isToday(d) ? "bg-primary text-primary-fg" : isSameMonth(d, date) ? "text-fg" : "text-fg-subtle")}>{format(d, "d")}</p>
              <div className="space-y-0.5">{evs.slice(0, 3).map((x) => <Chip key={x.id} e={x} onClick={() => onEvent(x)} compact />)}{evs.length > 3 && <p className="px-1.5 text-[11px] font-medium text-fg-muted">+{evs.length - 3} more</p>}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EventDialog({ e, onClose }: { e: CalendarEvent | null; onClose: () => void }) {
  const toggle = useToggleTask();
  if (!e) return null; const k = KIND[e.kind];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm" title={e.title} description={`${k.label} · ${formatDate(e.start, "long")}`}>
        <div className="space-y-3 text-sm">
          <p className="flex items-center gap-2"><span className="flex size-8 items-center justify-center rounded-lg" style={{ background: `color-mix(in srgb, ${k.color} 15%, transparent)`, color: k.color }}><k.icon className="size-4" /></span>{formatDate(e.start, "time")}{e.kind === "meeting" && ` – ${formatDate(e.end, "time")}`}</p>
          {e.location && <p className="text-fg-muted">{/^https?:/.test(e.location) ? <a className="text-primary hover:underline" href={e.location} target="_blank" rel="noreferrer">Join meeting</a> : e.location}</p>}
          <p className="text-fg-muted">Status: <span className="font-medium capitalize text-fg">{e.status.replace("_", " ")}</span></p>
          <div className="flex gap-2 pt-2">
            {e.entity.type === "task" && <Button size="sm" onClick={() => { toggle.mutate({ id: e.id, status: e.status } as never, { onSuccess: onClose }); }}>{e.status === "completed" ? "Reopen task" : "Mark complete"}</Button>}
            {href(e) && <Button size="sm" variant="secondary" asChild><Link href={href(e)}>Open</Link></Button>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function CalendarView({ mine, kinds, defaultView = "month", taskOnly }: { mine?: boolean; kinds?: Set<string>; defaultView?: View; taskOnly?: boolean }) {
  const ui = useUI(); const [view, setView] = React.useState<View>(defaultView); const [date, setDate] = React.useState(new Date()); const [sel, setSel] = React.useState<CalendarEvent | null>(null);
  const [from, to] = range(view, date);
  const q = useQuery({ queryKey: ["calendar", view, from.toISOString().slice(0, 10), mine], queryFn: () => api.get<CalendarEvent[]>("/api/v1/calendar", { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10), mine: mine ? "true" : undefined }), placeholderData: (p) => p });
  const events = (q.data ?? []).filter((e) => (!kinds || kinds.has(e.kind)) && (!taskOnly || ["task", "follow_up", "deadline"].includes(e.kind)));
  const step = (n: number) => setDate((d) => (view === "month" ? addMonths(d, n) : addDays(d, n * (view === "week" ? 7 : 1))));
  const title = view === "month" ? format(date, "MMMM yyyy") : view === "week" ? `${format(from, "d MMM")} – ${format(to, "d MMM yyyy")}` : format(date, "EEEE, d MMMM yyyy");
  const days = view === "day" ? [date] : Array.from({ length: 7 }, (_, i) => addDays(from, i));
  const create = (d: Date) => ui.openCreate("meeting", { starts_at: d.toISOString() });
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-3">
        <div className="flex items-center gap-2"><Button variant="secondary" size="sm" onClick={() => setDate(new Date())}>Today</Button><Button variant="ghost" size="icon-sm" onClick={() => step(-1)} aria-label="Previous"><ChevronLeft /></Button><Button variant="ghost" size="icon-sm" onClick={() => step(1)} aria-label="Next"><ChevronRight /></Button><h2 className="ml-1 text-base font-semibold tracking-tight">{title}</h2></div>
        <Segmented size="sm" value={view} onChange={setView} options={[{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]} />
      </div>
      {q.isError ? <ErrorState compact kind="unavailable" onRetry={() => q.refetch()} /> : view === "month" ? <MonthGrid date={date} events={events} onEvent={setSel} onDay={(d) => { setDate(d); setView("day"); }} /> : <TimeGrid days={days} events={events} onEvent={setSel} onSlot={create} />}
      <EventDialog e={sel} onClose={() => setSel(null)} />
    </div>
  );
}
export const KINDS = KIND;
export { CalIcon };
