"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChevronDown, Eye, MailCheck, Radar, ShieldCheck, Snowflake, Undo2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, Card, CardBody, CardHeader, EmptyState, ErrorState, Segmented, Skeleton, Switch, cn, formatDate, timeAgo, useToast } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";

type Person = { id: string; name: string; avatar_url: string | null } | null;
type Back = {
  lost: { id: string; name: string; status: string; lost_reason: string | null; marked_at: string; marked_by: Person; owner: Person };
  back: { type: "lead" | "contact"; id: string; name: string; source: string | null; created_at: string; owner: Person };
  matched_on: "phone" | "email"; gap_days: number; backdoor: boolean;
};
type Reveal = { user: NonNullable<Person>; reveals: number; clients: number; not_their_clients: number; team_usual: number | null; times_usual: number | null; flagged: boolean };
type Visit = {
  user: NonNullable<Person>; visits: number; cold: number; cold_rate: number; team_cold_rate: number | null; flagged: boolean;
  examples: { visit_id: string; title: string; visited_at: string; who: { type: "lead" | "contact"; id: string; name: string }; why: string }[];
};
type RadarData = {
  range: { from: string; to: string; days: number }; visit_range: { from: string; to: string; cold_days: number };
  lost_came_back: Back[]; reveals: Reveal[]; visits: Visit[];
  summary: { lost_came_back: number; via_backdoor: number; reveal_flags: number; visit_flags: number };
  settings: { weekly_report: boolean; last_sent_at: string | null };
};

const PERIODS = [{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "3 months" }];
const pct = (n: number | null | undefined) => `${Math.round((n ?? 0) * 100)}%`;
const href = (type: "lead" | "contact", id: string) => `/app/${type === "lead" ? "leads" : "contacts"}/${id}`;
const source = (s: string | null) => (s ? s.replace(/_/g, " ") : "a new enquiry");

function Tile({ icon: I, label, value, hint, alert }: { icon: React.ElementType; label: string; value: number; hint: string; alert: boolean }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-3">
        <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-full", alert ? "bg-danger-soft text-danger" : "bg-success-soft text-success")}><I className="size-4" /></span>
        <div className="min-w-0"><div className="text-2xl font-semibold tabular-nums">{value}</div><div className="truncate text-xs text-fg-muted">{label}</div></div>
      </div>
      <p className="mt-2 text-xs text-fg-subtle">{hint}</p>
    </Card>
  );
}

function Who({ p, fallback = "Someone" }: { p: Person; fallback?: string }) {
  return <span className="inline-flex items-center gap-1.5 font-medium"><Avatar name={p?.name ?? fallback} src={p?.avatar_url} size={18} />{p?.name ?? fallback}</span>;
}

function CameBack({ rows }: { rows: Back[] }) {
  return (
    <Card>
      <CardHeader title="Lost leads that came back" description="Marked lost or not interested, then turned up again as a new lead or client with the same phone or email." />
      {!rows.length ? <EmptyState compact icon={<ShieldCheck />} title="No lost leads came back" description="Nobody marked lost has returned as a new enquiry in this period." /> : (
        <ul className="divide-y divide-border">
          {rows.map((x) => (
            <li key={`${x.lost.id}-${x.back.id}`} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:gap-4">
              <div className="min-w-0 flex-1 text-sm">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Link href={href("lead", x.lost.id)} className="font-semibold hover:underline">{x.lost.name}</Link>
                  <span className="text-fg-muted">marked {x.lost.status === "lost" ? "lost" : "not interested"} by</span><Who p={x.lost.marked_by} />
                  <span className="text-fg-muted">on {formatDate(x.lost.marked_at)}</span>
                </div>
                {x.lost.lost_reason && <p className="mt-1 text-xs text-fg-muted">Reason given: “{x.lost.lost_reason}”</p>}
              </div>
              <ArrowRight className="hidden size-4 shrink-0 text-fg-subtle sm:block" />
              <div className="min-w-0 flex-1 text-sm">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-fg-muted">Back {x.gap_days ? `${x.gap_days} days later` : "the same day"} as</span>
                  <Link href={href(x.back.type, x.back.id)} className="font-semibold hover:underline">{x.back.name}</Link>
                  <span className="text-fg-muted">via {source(x.back.source)}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
                  {x.backdoor && <Badge tone="danger">Via {source(x.back.source)}</Badge>}
                  <span>Same {x.matched_on === "phone" ? "phone number" : "email"}</span>
                  {x.back.owner && <span>· now with {x.back.owner.name}</span>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Reveals({ rows }: { rows: Reveal[] }) {
  return (
    <Card>
      <CardHeader title="Phone numbers revealed" description="Each time someone revealed a client's hidden number, against the team's usual count." />
      {!rows.length ? <EmptyState compact icon={<Eye />} title="No numbers revealed" description="Nobody revealed a hidden phone number in this period." /> : (
        <ul className="divide-y divide-border">
          {rows.map((x) => (
            <li key={x.user.id} className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5", x.flagged && "bg-danger-soft/30")}>
              <div className="flex min-w-40 flex-1 items-center gap-3"><Avatar name={x.user.name} src={x.user.avatar_url} size={32} /><span className="font-medium">{x.user.name}</span>{x.flagged && <Badge tone="danger">{x.times_usual ? `${x.times_usual}× the team` : "Far above the team"}</Badge>}</div>
              <div className="flex gap-6 text-sm tabular-nums">
                <div><div className="font-semibold">{x.reveals}</div><div className="text-xs text-fg-muted">reveals</div></div>
                <div><div className={cn("font-semibold", x.not_their_clients > 0 && "text-warning")}>{x.not_their_clients}</div><div className="text-xs text-fg-muted">not their clients</div></div>
                <div><div className="font-semibold">{x.team_usual ?? "—"}</div><div className="text-xs text-fg-muted">team usual</div></div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Visits({ rows, range }: { rows: Visit[]; range: RadarData["visit_range"] }) {
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <Card>
      <CardHeader title="Leads gone cold after site visits" description={`A visited lead is cold when nobody followed up within ${range.cold_days} days of the visit, or it was marked lost. Visits from ${formatDate(range.from)} to ${formatDate(range.to)}.`} />
      {!rows.length ? <EmptyState compact icon={<Snowflake />} title="No site visits to judge yet" description={`Visits count here once ${range.cold_days} days have passed.`} /> : (
        <ul className="divide-y divide-border">
          {rows.map((x) => (
            <li key={x.user.id} className={cn(x.flagged && "bg-danger-soft/30")}>
              <button type="button" onClick={() => setOpen(open === x.user.id ? null : x.user.id)} disabled={!x.examples.length} aria-expanded={open === x.user.id}
                className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5 text-left transition-colors enabled:hover:bg-surface-hover">
                <div className="flex min-w-40 flex-1 items-center gap-3"><Avatar name={x.user.name} src={x.user.avatar_url} size={32} /><span className="font-medium">{x.user.name}</span>{x.flagged && <Badge tone="danger">Goes cold far more often</Badge>}</div>
                <div className="flex items-center gap-6 text-sm tabular-nums">
                  <div><div className="font-semibold">{x.cold} of {x.visits}</div><div className="text-xs text-fg-muted">went cold</div></div>
                  <div><div className={cn("font-semibold", x.flagged && "text-danger")}>{pct(x.cold_rate)}</div><div className="text-xs text-fg-muted">vs {x.team_cold_rate == null ? "—" : pct(x.team_cold_rate)} team</div></div>
                  <ChevronDown className={cn("size-4 text-fg-subtle transition-transform", open === x.user.id && "rotate-180", !x.examples.length && "invisible")} />
                </div>
              </button>
              {open === x.user.id && (
                <ul className="space-y-1.5 px-5 pb-4 sm:pl-[68px]">
                  {x.examples.map((e) => (
                    <li key={e.visit_id} className="flex flex-wrap items-center gap-x-2 text-sm">
                      <Link href={href(e.who.type, e.who.id)} className="font-medium hover:underline">{e.who.name}</Link>
                      <span className="text-fg-muted">visited {formatDate(e.visited_at)} · {e.why}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function WeeklyReport({ s }: { s: RadarData["settings"] }) {
  const { can } = useAccess(); const qc = useQueryClient(); const toast = useToast();
  const [busy, setBusy] = React.useState(false);
  const save = async (on: boolean) => {
    setBusy(true);
    try { await api.put("/api/v1/radar/settings", { weekly_report: on }); qc.invalidateQueries({ queryKey: ["radar"] }); toast.success(on ? "Weekly report on" : "Weekly report off"); }
    catch (e) { toast.error("Couldn't save", (e as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <Card className="mb-6">
      <CardBody className="flex flex-wrap items-center gap-4">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary"><MailCheck className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <div className="font-medium">Weekly report every Monday morning</div>
          <p className="text-sm text-fg-muted">Owners and admins get a summary of the last 7 days as a notification and an email.{s.last_sent_at ? ` Last sent ${timeAgo(s.last_sent_at)}.` : ""}</p>
        </div>
        <Switch checked={s.weekly_report} onCheckedChange={save} disabled={busy || !can("settings.manage")} aria-label="Weekly report" />
      </CardBody>
    </Card>
  );
}

export default function RadarPage() {
  const { can } = useAccess();
  const [days, setDays] = React.useState("7");
  const q = useQuery({ queryKey: ["radar", days], enabled: can("audit.read"), queryFn: () => api.get<RadarData>("/api/v1/radar", { days }) });
  const d = q.data;
  return (
    <PageContainer>
      <PageHeader title="Lead leakage radar" description="Signs that leads are quietly leaving with someone on the team. Only owners and admins see this page."
        actions={<Segmented size="sm" value={days} onChange={setDays} options={PERIODS} />} />
      {!can("audit.read") ? <Card><EmptyState icon={<Radar />} title="Only the owner and admins can see the radar" description="Ask your workspace owner if you need access." /></Card>
        : q.isError ? <ErrorState onRetry={() => q.refetch()} />
        : !d ? <div className="space-y-4"><Skeleton className="h-20" /><div className="grid gap-4 sm:grid-cols-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div><Skeleton className="h-64" /></div>
        : (
          <>
            <WeeklyReport s={d.settings} />
            <div className="mb-6 grid gap-4 sm:grid-cols-3">
              <Tile icon={Undo2} label="Lost leads came back" value={d.summary.lost_came_back} alert={d.summary.lost_came_back > 0}
                hint={d.summary.via_backdoor ? `${d.summary.via_backdoor} through a broker, walk-in or referral` : "Matched by phone number or email"} />
              <Tile icon={Eye} label="Reps revealing far more numbers" value={d.summary.reveal_flags} alert={d.summary.reveal_flags > 0} hint="At least twice the team's usual count" />
              <Tile icon={Snowflake} label="Reps whose visited leads go cold" value={d.summary.visit_flags} alert={d.summary.visit_flags > 0} hint="Far more often than the rest of the team" />
            </div>
            <div className="space-y-6">
              <CameBack rows={d.lost_came_back} />
              <Reveals rows={d.reveals} />
              <Visits rows={d.visits} range={d.visit_range} />
            </div>
            <p className="mt-6 text-xs text-fg-subtle">The radar points at things worth a look, not proof. A lead can come back for good reasons, and some roles reveal numbers more than others.</p>
          </>
        )}
    </PageContainer>
  );
}
