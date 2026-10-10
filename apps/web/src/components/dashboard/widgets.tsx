"use client";
import { ArrowDownRight, ArrowUpRight, CalendarClock, CheckCircle2, ChevronRight, Flame, Handshake, Hourglass, Sparkles, Users } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, Card, CardBody, CardHeader, EmptyState, FunnelBars, cn, dayLabel, formatDate, formatMoney, formatMoneyCompact, timeAgo, useLocalStorage } from "@crm/ui";
import { ActivityIcon } from "../records/timeline";
import type { Activity } from "@/lib/types";

export type Focus = {
  follow_ups: { count: number; items: { type: string; id: string; title: string; due_at: string; url: string }[] };
  meetings: { count: number; items: { id: string; title: string; starts_at: string; url: string }[] };
  deals_attention: { count: number; items: { id: string; title: string; value: number; currency: string; reason: string; url: string }[] };
  overdue_tasks: { count: number; items: { id: string; title: string; due_at: string; url: string }[] };
  holds_expiring?: { count: number; items: { id: string; title: string; due_at: string; url: string }[] };
};

export function TodaysFocus({ focus, loading, name }: { focus?: Focus; loading?: boolean; name?: string }) {
  const [open, setOpen] = React.useState<string | null>(null);
  const tiles = focus ? [
    { key: "follow_ups", n: focus.follow_ups.count, label: focus.follow_ups.count === 1 ? "follow-up" : "follow-ups", icon: Users, tone: "text-primary bg-primary-soft", items: focus.follow_ups.items.map((i) => ({ id: i.id, title: i.title, meta: formatDate(i.due_at, "time"), url: i.url })) },
    { key: "meetings", n: focus.meetings.count, label: focus.meetings.count === 1 ? "site visit or meeting" : "site visits & meetings", icon: CalendarClock, tone: "text-info bg-info-soft", items: focus.meetings.items.map((i) => ({ id: i.id, title: i.title, meta: formatDate(i.starts_at, "time"), url: i.url })) },
    { key: "holds", n: focus.holds_expiring?.count ?? 0, label: (focus.holds_expiring?.count ?? 0) === 1 ? "hold ending soon" : "holds ending soon", icon: Hourglass, tone: "text-[#7c3aed] bg-[#7c3aed]/10", items: (focus.holds_expiring?.items ?? []).map((i) => ({ id: i.id, title: i.title, meta: `Ends ${formatDate(i.due_at, "datetime")}`, url: i.url })) },
    { key: "deals", n: focus.deals_attention.count, label: focus.deals_attention.count === 1 ? "deal needs attention" : "deals need attention", icon: Handshake, tone: "text-warning bg-warning-soft", items: focus.deals_attention.items.map((i) => ({ id: i.id, title: i.title, meta: i.reason, url: i.url })) },
    { key: "overdue", n: focus.overdue_tasks.count, label: focus.overdue_tasks.count === 1 ? "overdue task" : "overdue tasks", icon: Flame, tone: "text-danger bg-danger-soft", items: focus.overdue_tasks.items.map((i) => ({ id: i.id, title: i.title, meta: `Due ${formatDate(i.due_at)}`, url: i.url })) },
  ] : [];
  const total = tiles.reduce((a, t) => a + t.n, 0);
  const expanded = tiles.find((t) => t.key === open);
  return (
    <Card className="overflow-hidden border-primary/20 bg-gradient-to-br from-primary-soft/70 via-surface to-surface">
      <div className="p-5 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div><h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight"><Flame className="size-5 text-primary" /> Today's Focus</h2>
            <p className="mt-0.5 text-sm text-fg-muted">{loading ? "Checking what needs you…" : total === 0 ? `You're all clear${name ? `, ${name}` : ""}. A great time to follow up with past clients.` : "Start here — these are the things most likely to close a sale today."}</p></div>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {loading ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-[92px] rounded-xl" />) : tiles.map((t) => (
            <button key={t.key} onClick={() => setOpen(open === t.key ? null : t.key)} aria-expanded={open === t.key} disabled={!t.n}
              className={cn("group rounded-xl border bg-surface p-4 text-left shadow-xs transition-all disabled:opacity-60", open === t.key ? "border-primary ring-2 ring-primary/20" : "border-border enabled:hover:-translate-y-0.5 enabled:hover:shadow-md")}>
              <span className={cn("mb-3 flex size-8 items-center justify-center rounded-lg", t.tone)}><t.icon className="size-4" /></span>
              <p className="tabular text-3xl font-semibold leading-none tracking-tight">{t.n}</p><p className="mt-1.5 text-[13px] text-fg-muted">{t.label}</p>
            </button>
          ))}
        </div>
        {expanded && (
          <ul className="mt-4 animate-fade-in divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {expanded.items.map((i) => <li key={i.id}><Link href={i.url} className="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-surface-hover"><span className="min-w-0 truncate font-medium">{i.title}</span><span className="flex shrink-0 items-center gap-2 text-xs text-fg-muted">{i.meta}<ChevronRight className="size-4 text-fg-subtle" /></span></Link></li>)}
            {expanded.n > expanded.items.length && <li className="px-4 py-2.5 text-center text-xs text-fg-subtle">and {expanded.n - expanded.items.length} more</li>}
          </ul>
        )}
      </div>
    </Card>
  );
}

export function Metric({ label, value, delta, deltaSuffix = "%", sub, invert, loading, href, icon: Icon }: { label: string; value: React.ReactNode; delta?: number | null; deltaSuffix?: string; sub?: string; invert?: boolean; loading?: boolean; href?: string; icon?: React.ElementType }) {
  const good = delta == null ? null : invert ? delta <= 0 : delta >= 0;
  const body = (
    <Card hover={!!href} className="h-full p-4 sm:p-5">
      <div className="flex items-center justify-between"><p className="text-[13px] font-medium text-fg-muted">{label}</p>{Icon && <Icon className="size-4 text-fg-subtle" />}</div>
      {loading ? <div className="skeleton mt-3 h-8 w-24" /> : <p className="tabular mt-2 text-[28px] font-semibold leading-none tracking-tight">{value}</p>}
      <div className="mt-2.5 flex items-center gap-2 text-xs">
        {delta != null && !loading && <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-medium", good ? "bg-success-soft text-success" : "bg-danger-soft text-danger")}>{delta >= 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}{Math.abs(delta)}{deltaSuffix}</span>}
        {sub && <span className="text-fg-subtle">{sub}</span>}
      </div>
    </Card>
  );
  return href ? <Link href={href} className="block">{body}</Link> : body;
}

export function ActivityFeed({ items, loading }: { items?: Activity[]; loading?: boolean }) {
  return (
    <Card className="h-full">
      <CardHeader title="Recent activity" description="What your team has been up to" actions={<Link href="/app/activities" className="text-[13px] font-medium text-primary hover:underline">View all</Link>} />
      <CardBody className="pt-3">
        {loading ? <div className="space-y-4">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-10" />)}</div> : !items?.length ? <EmptyState compact icon={<Sparkles />} title="No activity yet" description="Create a lead or log a call and it'll show up here." /> : (
          <ul className="space-y-1">
            {items.map((a) => {
              const rel = a.related[0];
              const href = rel ? `/app/${rel.type === "company" ? "companies" : rel.type + "s"}/${rel.id}` : undefined;
              return (
                <li key={a.id} className="group flex gap-3 rounded-lg p-2 transition-colors hover:bg-surface-hover">
                  <ActivityIcon type={a.type} small />
                  <div className="min-w-0 flex-1"><p className="text-[13.5px] leading-snug"><span className="font-medium">{a.user?.name ?? "System"}</span> <span className="text-fg-muted">·</span> {href ? <Link href={href} className="hover:text-primary">{a.title}</Link> : a.title}</p>
                    <p className="mt-0.5 truncate text-xs text-fg-subtle">{rel?.label ? `${rel.label} · ` : ""}{timeAgo(a.occurred_at)}</p></div>
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

export function NextBestActions({ items, loading }: { items?: { kind: string; title: string; reason: string; url: string; cta: string }[]; loading?: boolean }) {
  return (
    <Card className="h-full">
      <CardHeader title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Next best actions</span>} description="AI-picked, based on your pipeline" />
      <CardBody className="pt-3">
        {loading ? <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-14" />)}</div> : !items?.length ? <p className="py-6 text-center text-sm text-fg-muted">Nothing urgent — your pipeline is in good shape. 🎉</p> : (
          <ul className="space-y-2">{items.slice(0, 5).map((a, i) => (
            <li key={i}><Link href={a.url} className="flex items-center gap-3 rounded-lg border border-border p-3 transition-colors hover:border-primary/40 hover:bg-primary-soft/40">
              <span className="min-w-0 flex-1"><span className="block truncate text-[13.5px] font-medium">{a.title}</span><span className="mt-0.5 line-clamp-2 block text-xs text-fg-muted">{a.reason}</span></span><span className="shrink-0 text-xs font-medium text-primary">{a.cta} →</span></Link></li>
          ))}</ul>
        )}
      </CardBody>
    </Card>
  );
}

export function GettingStarted({ steps }: { steps: { done: boolean; title: string; description: string; href: string; cta: string }[] }) {
  const done = steps.filter((s) => s.done).length;
  const [hidden, setHidden] = useLocalStorage("getting-started-hidden", false);
  if (done === steps.length || hidden) return null;
  return (
    <Card>
      <CardHeader title="Get started in 5 minutes" description={`${done} of ${steps.length} done — from your first project to your first sale`} actions={<button onClick={() => setHidden(true)} className="text-xs font-medium text-fg-subtle hover:text-fg">Hide</button>} />
      <CardBody className="pt-4">
        <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-bg-subtle"><div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${(done / steps.length) * 100}%` }} /></div>
        <ol className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
          {steps.map((s, i) => (
            <li key={s.title}><Link href={s.href} className={cn("flex h-full gap-3 rounded-lg border p-3.5 transition-colors", s.done ? "border-success/30 bg-success-soft/40" : "border-border hover:border-primary/40 hover:bg-primary-soft/40")}>
              <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold", s.done ? "bg-success text-white" : "bg-bg-subtle text-fg-muted")}>{s.done ? <CheckCircle2 className="size-4" /> : i + 1}</span>
              <span><span className="block text-[13.5px] font-semibold">{s.title}</span><span className="mt-0.5 block text-xs text-fg-muted">{s.description}</span>{!s.done && <span className="mt-1.5 block text-xs font-medium text-primary">{s.cta} →</span>}</span></Link></li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}
export { Avatar, Badge, FunnelBars, dayLabel, formatMoney, formatMoneyCompact };
