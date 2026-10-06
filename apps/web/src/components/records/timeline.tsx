"use client";
import { useInfiniteQuery } from "@tanstack/react-query";
import { AtSign, CalendarClock, CheckCircle2, CheckSquare, FileText, Handshake, Mail, MoveRight, Phone, PlusCircle, Repeat, Settings2, StickyNote, Trophy, UserCheck, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Button, EmptyState, SkeletonRows, cn, dayLabel, formatDate, timeAgo } from "@crm/ui";
import { api } from "@/lib/api";
import type { Activity } from "@/lib/types";

const MAP: Record<string, [React.ElementType, string]> = {
  created: [PlusCircle, "bg-success-soft text-success"], updated: [Settings2, "bg-bg-subtle text-fg-muted"], stage_changed: [MoveRight, "bg-primary-soft text-primary"], status_changed: [Repeat, "bg-info-soft text-info"],
  note: [StickyNote, "bg-warning-soft text-warning"], email: [Mail, "bg-info-soft text-info"], call: [Phone, "bg-success-soft text-success"], meeting: [CalendarClock, "bg-primary-soft text-primary"],
  task: [CheckSquare, "bg-bg-subtle text-fg-muted"], task_completed: [CheckCircle2, "bg-success-soft text-success"], converted: [UserCheck, "bg-primary-soft text-primary"], file: [FileText, "bg-bg-subtle text-fg-muted"],
  assigned: [AtSign, "bg-info-soft text-info"], won: [Trophy, "bg-success-soft text-success"], lost: [XCircle, "bg-danger-soft text-danger"], system: [Settings2, "bg-bg-subtle text-fg-muted"],
};
export function ActivityIcon({ type, small }: { type: string; small?: boolean }) {
  const [I, tone] = MAP[type] ?? [Handshake, "bg-bg-subtle text-fg-muted"];
  return <span className={cn("flex shrink-0 items-center justify-center rounded-full", tone, small ? "mt-0.5 size-7" : "size-8")}><I className={small ? "size-3.5" : "size-4"} /></span>;
}

const groupByDay = (items: Activity[]) => {
  const g: { day: string; items: Activity[] }[] = [];
  for (const a of items) { const d = dayLabel(a.occurred_at); const last = g[g.length - 1]; if (last?.day === d) last.items.push(a); else g.push({ day: d, items: [a] }); }
  return g;
};

/** Elegant day-grouped timeline. With `entity` set it shows that record's history; without, the workspace feed. */
export function Timeline({ entity, id, types, userId, showRelated }: { entity?: string; id?: string; types?: string; userId?: string; showRelated?: boolean }) {
  const q = useInfiniteQuery({
    queryKey: ["timeline", entity, id, types, userId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.page<Activity>("/api/v1/timeline", { entity, id, types, user_id: userId, before: pageParam, limit: 25 }),
    getNextPageParam: (last) => (last.meta.has_more ? (last.meta.next_before as string) : undefined),
  });
  const items = q.data?.pages.flatMap((p) => p.data) ?? [];
  if (q.isLoading) return <SkeletonRows rows={5} />;
  if (!items.length) return <EmptyState compact icon={<CalendarClock />} title="No activity yet" description="Emails, calls, notes and stage changes will build a timeline here." />;
  return (
    <div>
      {groupByDay(items).map((g) => (
        <section key={g.day} className="mb-6">
          <h3 className="sticky top-14 z-[1] mb-3 bg-bg/90 py-1 text-xs font-semibold uppercase tracking-wider text-fg-subtle backdrop-blur">{g.day}</h3>
          <ol className="relative space-y-0">
            {g.items.map((a, i) => (
              <li key={a.id} className="relative flex gap-3.5 pb-5 last:pb-0">
                {i < g.items.length - 1 && <span className="absolute left-4 top-9 -ml-px h-[calc(100%-28px)] w-px bg-border" aria-hidden />}
                <ActivityIcon type={a.type} />
                <div className="min-w-0 flex-1 pt-0.5">
                  <div className="flex items-baseline justify-between gap-3"><p className="text-sm font-medium">{a.title}</p><time className="shrink-0 text-xs tabular text-fg-subtle" title={formatDate(a.occurred_at, "datetime")}>{formatDate(a.occurred_at, "time")}</time></div>
                  {a.body && <p className="mt-1 line-clamp-3 whitespace-pre-line rounded-lg bg-bg-subtle px-3 py-2 text-[13px] text-fg-muted">{a.body}</p>}
                  <p className="mt-1 text-xs text-fg-subtle">{a.user?.name ?? "System"} · {timeAgo(a.occurred_at)}{showRelated && a.related[0] && <> · <Link href={`/app/${a.related[0].type === "company" ? "companies" : a.related[0].type + "s"}/${a.related[0].id}`} className="text-primary hover:underline">{a.related[0].label}</Link></>}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ))}
      {q.hasNextPage && <div className="flex justify-center"><Button variant="secondary" size="sm" onClick={() => q.fetchNextPage()} loading={q.isFetchingNextPage}>Load older activity</Button></div>}
    </div>
  );
}
