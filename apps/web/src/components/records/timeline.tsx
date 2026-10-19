"use client";
import { useInfiniteQuery } from "@tanstack/react-query";
import { AtSign, CalendarClock, CheckCircle2, CheckSquare, FileText, Handshake, Mail, MessageCircle, MoveRight, Phone, PlusCircle, Repeat, Settings2, StickyNote, Trophy, UserCheck, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Button, EmptyState, SkeletonRows, cn, dayLabel, formatDate, timeAgo } from "@crm/ui";
import { api } from "@/lib/api";
import type { Activity } from "@/lib/types";

const MAP: Record<string, [React.ElementType, string]> = {
  created: [PlusCircle, "bg-success-soft text-success"], updated: [Settings2, "bg-bg-subtle text-fg-muted"], stage_changed: [MoveRight, "bg-primary-soft text-primary"], status_changed: [Repeat, "bg-info-soft text-info"],
  note: [StickyNote, "bg-warning-soft text-warning"], email: [Mail, "bg-info-soft text-info"], call: [Phone, "bg-success-soft text-success"], meeting: [CalendarClock, "bg-primary-soft text-primary"],
  task: [CheckSquare, "bg-bg-subtle text-fg-muted"], task_completed: [CheckCircle2, "bg-success-soft text-success"], converted: [UserCheck, "bg-primary-soft text-primary"], file: [FileText, "bg-bg-subtle text-fg-muted"],
  assigned: [AtSign, "bg-info-soft text-info"], won: [Trophy, "bg-success-soft text-success"], lost: [XCircle, "bg-danger-soft text-danger"], system: [Settings2, "bg-bg-subtle text-fg-muted"],
  whatsapp: [MessageCircle, "bg-success-soft text-success"],
};
export function ActivityIcon({ type, small }: { type: string; small?: boolean }) {
  const [I, tone] = MAP[type] ?? [Handshake, "bg-bg-subtle text-fg-muted"];
  return <span className={cn("flex shrink-0 items-center justify-center rounded-full", tone, small ? "mt-0.5 size-7" : "size-8")}><I className={small ? "size-3.5" : "size-4"} /></span>;
}

const groupByDay = (items: Activity[]) => {
  const g: { day: string; at: string; items: Activity[] }[] = [];
  for (const a of items) { const d = dayLabel(a.occurred_at); const last = g[g.length - 1]; if (last?.day === d) last.items.push(a); else g.push({ day: d, at: a.occurred_at, items: [a] }); }
  return g;
};

/** "Today", "Yesterday" and weekdays get the date beside them; dated labels already carry it. */
const dayNote = (label: string, at: string) => (/\d/.test(label) ? null : new Date(at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }));

const Stage = ({ children, to }: { children: React.ReactNode; to?: boolean }) => (
  <span className={cn("inline-flex items-center rounded-full border px-2 py-px text-xs font-medium", to ? "border-primary/25 bg-primary-soft text-primary" : "border-border bg-surface-2 text-fg-muted")}>{children}</span>
);

/** Stage moves and new deals show their stages as pills; everything else is the plain title. */
function Title({ a }: { a: Activity }) {
  let m: RegExpMatchArray | null;
  if ((m = a.title.match(/^Moved from (.+) to (.+)$/))) return <>Moved <Stage>{m[1]}</Stage><MoveRight className="size-3.5 text-fg-subtle" aria-label="to" /><Stage to>{m[2]}</Stage></>;
  if ((m = a.title.match(/^Moved to (.+)$/))) return <>Moved to <Stage to>{m[1]}</Stage></>;
  if ((m = a.title.match(/^Deal created in (.+)$/))) return <>Deal created in <Stage>{m[1]}</Stage></>;
  return <>{a.title}</>;
}

/** Day-grouped timeline on one continuous rail. With `entity` set it shows that record's history; without, the workspace feed. */
export function Timeline({ entity, id, types, userId, showRelated }: { entity?: string; id?: string; types?: string; userId?: string; showRelated?: boolean }) {
  const q = useInfiniteQuery({
    queryKey: ["timeline", entity, id, types, userId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.page<Activity>("/api/v1/timeline", { entity, id, types, user_id: userId, before: pageParam, limit: 25 }),
    getNextPageParam: (last) => (last.meta.has_more ? (last.meta.next_before as string) : undefined),
  });
  const items = q.data?.pages.flatMap((p) => p.data) ?? [];
  if (q.isLoading) return <SkeletonRows rows={5} />;
  if (!items.length) return <EmptyState compact icon={<CalendarClock />} title="No activity yet" description="Emails, WhatsApp messages, calls, notes and stage changes will build a timeline here." />;
  return (
    <div className="relative">
      <span className="absolute bottom-6 left-[15.5px] top-4 w-px bg-gradient-to-b from-border-strong via-border to-transparent" aria-hidden />
      {groupByDay(items).map((g) => {
        const note = dayNote(g.day, g.at);
        return (
          <section key={g.day} className="relative pb-4">
            <h3 className="sticky top-[72px] z-[2] flex py-2">
              <span className="glass-pop inline-flex items-center gap-1.5 rounded-full border border-border py-1 pl-[7px] pr-3 text-xs font-semibold text-fg shadow-sm">
                <span className="mx-[3px] size-2.5 rounded-full bg-primary ring-[3px] ring-primary-soft" aria-hidden />
                {g.day}{note && <span className="font-normal text-fg-subtle">{note}</span>}
              </span>
            </h3>
            <ol className="space-y-2.5 pt-1">
              {g.items.map((a) => {
                const tone = a.type === "won" ? "border-success/30 bg-success-soft" : a.type === "lost" ? "border-danger/25 bg-danger-soft" : "border-border bg-surface hover:border-border-strong";
                return (
                  <li key={a.id} className="relative flex gap-3">
                    <span className="relative z-[1] mt-1.5 shrink-0 self-start rounded-full bg-surface-solid"><ActivityIcon type={a.type} /></span>
                    <div className={cn("min-w-0 flex-1 rounded-xl border px-3.5 py-2.5 shadow-sm transition-colors", tone)}>
                      <div className="flex items-start justify-between gap-3">
                        <p className="flex min-w-0 flex-wrap items-center gap-1.5 text-sm font-medium leading-6"><Title a={a} /></p>
                        <time className="mt-1 shrink-0 text-xs tabular text-fg-subtle" dateTime={a.occurred_at} title={formatDate(a.occurred_at, "datetime")}>{formatDate(a.occurred_at, "time")}</time>
                      </div>
                      {a.body && <p className="mt-1.5 line-clamp-3 whitespace-pre-line border-l-2 border-border-strong pl-3 text-[13px] text-fg-muted">{a.body}</p>}
                      <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-fg-subtle">
                        {a.user ? <Avatar name={a.user.name} src={a.user.avatar_url} size={18} /> : <Settings2 className="size-3.5" aria-hidden />}
                        <span className="font-medium text-fg-muted">{a.user?.name ?? "System"}</span>
                        <span aria-hidden>·</span><span>{timeAgo(a.occurred_at)}</span>
                        {showRelated && a.related[0] && <><span aria-hidden>·</span><Link href={`/app/${a.related[0].type === "company" ? "companies" : a.related[0].type + "s"}/${a.related[0].id}`} className="truncate text-primary hover:underline">{a.related[0].label}</Link></>}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}
      {q.hasNextPage && <div className="relative flex justify-center pt-2"><Button variant="secondary" size="sm" onClick={() => q.fetchNextPage()} loading={q.isFetchingNextPage}>Load older activity</Button></div>}
    </div>
  );
}
