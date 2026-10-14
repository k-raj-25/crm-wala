"use client";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ChevronRight, ExternalLink, Flame, Hourglass, ListChecks, MapPin, MessageCircle, Phone, PhoneCall, RefreshCw, Sparkles, Sun, UserPlus } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Segmented, Skeleton, cn } from "@crm/ui";
import { useAiFeature, useAiStatus } from "@/lib/ai";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";

export type DayItem = { id: string; title: string; reason?: string; url: string; phone?: string | null; whatsapp?: string | null; maps?: string | null; time?: string | null; lead_id?: string | null; unit_id?: string | null; task_id?: string | null; hint?: string | null };
export type TeamRow = { user_id: string; name: string; new_leads: number; uncontacted: number; overdue_follow_ups: number; visits: number; visits_today: number; won: number; median_response_hours: number | null };
export type MyDayData = { sections: { key: string; title: string; items: DayItem[] }[]; counts: Record<string, number>; date: string; team?: TeamRow[] };

const ICON: Record<string, React.ElementType> = { visits: CalendarClock, follow_ups: PhoneCall, new: UserPlus, cooling: Flame, holds: Hourglass, tasks: ListChecks };
const TONE: Record<string, string> = { visits: "bg-info-soft text-info", follow_ups: "bg-primary-soft text-primary", new: "bg-success-soft text-success", cooling: "bg-warning-soft text-warning", holds: "bg-[#7c3aed]/10 text-[#7c3aed]", tasks: "bg-danger-soft text-danger" };
const time = (iso?: string | null) => iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }) : null;

export const useMyDay = (team = false, enabled = true) => useQuery({ queryKey: ["my-day", team], enabled, staleTime: 60_000, queryFn: () => api.get<MyDayData>("/api/v1/ai/my-day", team ? { team: "1" } : undefined) });

function ItemActions({ i, size = "xs" }: { i: DayItem; size?: "xs" | "sm" }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {i.phone && <Button asChild size={size} variant="secondary"><a href={`tel:${i.phone}`} aria-label={`Call ${i.title}`}><Phone /> Call</a></Button>}
      {i.whatsapp && <Button asChild size={size} variant="secondary"><a href={i.whatsapp} target="_blank" rel="noreferrer noopener"><MessageCircle /> WhatsApp</a></Button>}
      {i.maps && <Button asChild size={size} variant="secondary"><a href={i.maps} target="_blank" rel="noreferrer noopener"><MapPin /> Directions</a></Button>}
      <Button asChild size={size} variant="ghost"><Link href={i.url}><ExternalLink /> Open</Link></Button>
    </div>
  );
}

function TeamTable({ rows }: { rows: TeamRow[] }) {
  if (!rows.length) return <p className="py-6 text-center text-sm text-fg-muted">No team members yet.</p>;
  const cols: [keyof TeamRow, string][] = [["new_leads", "New leads"], ["uncontacted", "Not called"], ["overdue_follow_ups", "Overdue follow-ups"], ["visits", "Visits this week"], ["visits_today", "Visits today"], ["won", "Won"], ["median_response_hours", "First reply (median)"]];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead><tr className="border-b border-border text-left text-xs text-fg-subtle"><th className="px-3 py-2 font-medium">Agent</th>{cols.map(([k, l]) => <th key={k} className="px-3 py-2 text-right font-medium">{l}</th>)}</tr></thead>
        <tbody>{rows.map((r) => <tr key={r.user_id} className="border-b border-border last:border-0">
          <td className="px-3 py-2.5 font-medium">{r.name}</td>
          {cols.map(([k]) => { const v = r[k] as number | null; const bad = (k === "median_response_hours" && v != null && v > 4) || ((k === "uncontacted" || k === "overdue_follow_ups") && !!v);
            return <td key={k} className={cn("tabular px-3 py-2.5 text-right", bad && "font-semibold text-danger")}>{v == null ? "—" : k === "median_response_hours" ? `${v}h` : v}</td>; })}
        </tr>)}</tbody>
      </table>
    </div>
  );
}

/** The full "My day" tab: a short briefing, then today's visits, follow-ups, new enquiries, holds and to-dos with one-tap actions. */
export function MyDay() {
  const on = useAiFeature("briefing"); const { can } = useAccess();
  const sp = useSearchParams(); const router = useRouter(); const path = usePathname();
  const canTeam = can("reports.read"); const team = canTeam && sp.get("team") === "1";
  const setTeam = (v: "me" | "team") => { const q = new URLSearchParams(sp.toString()); v === "team" ? q.set("team", "1") : q.delete("team"); router.replace(`${path}?${q.toString()}`, { scroll: false }); };
  const day = useMyDay(team, on);
  const intro = useQuery({ queryKey: ["my-day-intro", team], enabled: on, staleTime: 10 * 60_000, retry: false, queryFn: () => api.post<{ text: string }>("/api/v1/ai/my-day/intro", { team }) });
  const status = useAiStatus();
  if (!on && status.isLoading) return <Skeleton className="h-40 rounded-xl" />;
  if (!on) return <ErrorState kind="permission" title="My day is turned off" description="Ask a workspace admin to turn on the daily briefing in Settings → AI assistant." />;
  const sections = day.data?.sections.filter((s) => s.items.length) ?? [];
  return (
    <div className="space-y-4">
      <Card className="overflow-hidden border-primary/20 bg-gradient-to-br from-primary-soft/70 via-surface to-surface">
        <div className="flex flex-wrap items-start gap-4 p-5 sm:p-6">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary"><Sun className="size-5" /></span>
          <div className="min-w-0 flex-1">{intro.isLoading ? <div className="space-y-2"><Skeleton className="h-4 w-full max-w-lg" /><Skeleton className="h-4 w-2/3 max-w-md" /></div> : <p className="text-[15px] leading-relaxed">{intro.data?.text ?? "Here's what needs you today."}</p>}
            {day.data && <div className="mt-3 flex flex-wrap gap-1.5">{day.data.sections.map((s) => <span key={s.key} className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", s.items.length ? TONE[s.key] ?? "bg-bg-subtle text-fg-muted" : "bg-bg-subtle text-fg-subtle")}>{s.title}: {day.data!.counts[s.key] ?? s.items.length}</span>)}</div>}</div>
          <div className="flex items-center gap-2">
            {canTeam && <Segmented size="sm" value={team ? "team" : "me"} onChange={setTeam} options={[{ value: "me", label: "Me" }, { value: "team", label: "Team" }]} />}
            <Button size="icon-sm" variant="ghost" aria-label="Refresh" onClick={() => { day.refetch(); intro.refetch(); }}><RefreshCw className={cn(day.isFetching && "animate-spin")} /></Button>
          </div>
        </div>
      </Card>

      {team && day.data?.team && <Card><CardHeader title="Team this week" description="Red means someone needs a nudge: leads not called, overdue follow-ups, or first replies slower than 4 hours." /><CardBody className="pt-2"><TeamTable rows={day.data.team} /></CardBody></Card>}

      {day.isLoading ? <div className="grid gap-4 lg:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-48 rounded-xl" />)}</div>
        : day.isError ? <ErrorState kind="unavailable" description={(day.error as Error).message} onRetry={() => day.refetch()} />
        : !sections.length ? <Card><EmptyState icon={<Sparkles />} title="You're all clear today" description="No visits, follow-ups or new enquiries waiting. A good time to call warm leads and share new inventory." action={<Button asChild variant="secondary"><Link href="/app/leads">Open leads</Link></Button>} /></Card>
        : <div className="grid items-start gap-4 lg:grid-cols-2">{sections.map((s) => { const Icon = ICON[s.key] ?? ListChecks; return (
          <Card key={s.key}>
            <CardHeader title={<span className="flex items-center gap-2"><span className={cn("flex size-7 items-center justify-center rounded-lg", TONE[s.key])}><Icon className="size-4" /></span>{s.title}<span className="tabular text-sm font-normal text-fg-subtle">{s.items.length}</span></span>} />
            <CardBody className="pt-2"><ul className="divide-y divide-border">{s.items.map((i) => (
              <li key={i.id} className="space-y-2 py-3">
                <div className="flex gap-3">{i.time && <span className="tabular shrink-0 text-sm font-semibold text-info">{time(i.time)}</span>}
                  <div className="min-w-0 flex-1"><Link href={i.url} className="block truncate text-sm font-medium hover:text-primary">{i.title}</Link>
                    <p className="line-clamp-2 text-xs text-fg-muted">{[i.reason, i.hint].filter(Boolean).join(" · ")}</p></div></div>
                <ItemActions i={i} />
              </li>))}</ul></CardBody>
          </Card>); })}</div>}
    </div>
  );
}

/** Compact version for the home dashboard: counts and the first few things to do. */
export function MyDayCard() {
  const on = useAiFeature("briefing"); const day = useMyDay(false, on);
  if (!on) return null;
  const items = (day.data?.sections ?? []).flatMap((s) => s.items.map((i) => ({ ...i, key: s.key }))).slice(0, 4);
  const total = Object.values(day.data?.counts ?? {}).reduce((a, n) => a + n, 0);
  return (
    <Card className="h-full">
      <CardHeader title={<span className="flex items-center gap-2"><Sun className="size-4 text-primary" /> My day</span>} description={day.isLoading ? "Checking your day…" : total ? `${total} thing${total === 1 ? "" : "s"} to do today` : "Nothing urgent today"}
        actions={<Button asChild size="sm" variant="ghost"><Link href="/app/ai?tab=day">Open <ChevronRight /></Link></Button>} />
      <CardBody className="pt-2">
        {day.isLoading ? <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div> : day.isError ? <p className="py-4 text-sm text-fg-muted">Couldn't load your day.</p> : (<>
          <div className="mb-3 flex flex-wrap gap-1.5">{(day.data?.sections ?? []).filter((s) => s.items.length).map((s) => <span key={s.key} className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", TONE[s.key])}>{s.title}: {day.data!.counts[s.key]}</span>)}</div>
          {!items.length ? <p className="py-4 text-center text-sm text-fg-muted">You're all clear. A good time to call warm leads.</p> : <ul className="divide-y divide-border">{items.map((i) => { const Icon = ICON[i.key] ?? ListChecks; return (
            <li key={i.key + i.id} className="flex items-center gap-3 py-2.5">
              <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg", TONE[i.key])}><Icon className="size-3.5" /></span>
              <div className="min-w-0 flex-1"><Link href={i.url} className="block truncate text-sm font-medium hover:text-primary">{i.time && <span className="tabular mr-1.5 text-info">{time(i.time)}</span>}{i.title}</Link><p className="truncate text-xs text-fg-muted">{i.reason}</p></div>
              {i.phone && <a href={`tel:${i.phone}`} aria-label={`Call ${i.title}`} className="grid size-8 place-items-center rounded-md text-fg-muted hover:bg-surface-hover hover:text-fg"><Phone className="size-4" /></a>}
              {i.whatsapp && <a href={i.whatsapp} target="_blank" rel="noreferrer noopener" aria-label={`WhatsApp ${i.title}`} className="grid size-8 place-items-center rounded-md text-fg-muted hover:bg-surface-hover hover:text-success"><MessageCircle className="size-4" /></a>}
            </li>); })}</ul>}
        </>)}
      </CardBody>
    </Card>
  );
}
