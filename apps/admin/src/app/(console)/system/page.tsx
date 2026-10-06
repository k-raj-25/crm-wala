"use client";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { Badge, Button, Card, CardHeader, ErrorState, Skeleton, Table, TBody, TD, TH, THead, TR, formatDate, timeAgo } from "@crm/ui";
import { PageHeader, StatusBadge } from "@/components/bits";
import { A, api } from "@/lib/api";

type Row = Record<string, string | number | null | undefined>;
type Sys = {
  checks: Record<string, { ok: boolean; pending?: number | null; backend?: string; provider?: string; error?: string }>; time: string;
  jobs: { recent: Row[]; failed: Row[] }; email: { last_24h: Record<string, number>; failures: Row[] }; webhooks: { last_7d: Record<string, number>; recent: Row[]; failures: Row[] };
  api_errors: { last_24h: number; recent: Row[] }; integration_errors: { workspace_id: string; provider: string; status: string; error: string | null; updated_at: string }[]; auth_events: Row[];
};
const NAMES: Record<string, string> = { database: "Database", redis: "Redis", job_queue: "Job queue", storage: "File storage", billing_provider: "Billing provider", email_provider: "Email provider", ai_provider: "AI provider" };

function Empty({ text }: { text: string }) { return <p className="px-5 py-6 text-sm text-fg-muted">{text}</p>; }

export default function Page() {
  const q = useQuery({ queryKey: ["system"], queryFn: () => api.get<Sys>(`${A}/system`), refetchInterval: 30_000, staleTime: 0 });
  const s = q.data;
  if (q.isError) return <ErrorState kind="unavailable" onRetry={() => q.refetch()} />;
  const allOk = s && Object.values(s.checks).every((c) => c.ok);
  return (
    <>
      <PageHeader title="System health" description={s ? `Last checked ${timeAgo(s.time)} · refreshes every 30s` : "Checking…"}
        actions={<><Badge tone={allOk ? "success" : "danger"} dot>{s ? (allOk ? "All systems operational" : "Degraded") : "…"}</Badge><Button variant="secondary" size="sm" onClick={() => q.refetch()} loading={q.isFetching}><RefreshCw /> Refresh</Button></>} />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {!s ? Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-20" />) : Object.entries(s.checks).map(([k, c]) => (
          <Card key={k} className="flex items-center gap-3 p-4">
            {c.ok ? <CheckCircle2 className="size-5 shrink-0 text-success" /> : <XCircle className="size-5 shrink-0 text-danger" />}
            <div className="min-w-0"><p className="text-sm font-medium">{NAMES[k] ?? k}</p><p className="truncate text-xs text-fg-muted">{c.error ?? c.provider ?? c.backend ?? (k === "job_queue" ? `${c.pending ?? 0} pending` : c.ok ? "OK" : "Down")}</p></div>
          </Card>))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card><CardHeader title="Background jobs" description="Most recent runs" />
          <div className="mt-2 overflow-x-auto">{!s ? <Skeleton className="m-4 h-32" /> : !s.jobs.recent.length ? <Empty text="No jobs have run yet." /> : <Table><THead><TR><TH>Job</TH><TH>Status</TH><TH>When</TH><TH className="text-right">Duration</TH></TR></THead><TBody>{s.jobs.recent.slice(0, 8).map((j) => <TR key={String(j.id)}><TD className="font-mono text-xs">{j.name}</TD><TD><StatusBadge status={String(j.status) === "success" ? "succeeded" : String(j.status)} /></TD><TD className="text-fg-muted">{timeAgo(String(j.created_at))}</TD><TD className="tabular text-right text-fg-muted">{j.duration_ms != null ? `${j.duration_ms} ms` : "—"}</TD></TR>)}</TBody></Table>}</div>
          {s && s.jobs.failed.length > 0 && <div className="border-t border-border p-4"><p className="mb-2 text-sm font-medium text-danger">{s.jobs.failed.length} failed</p><ul className="space-y-1 text-xs text-fg-muted">{s.jobs.failed.slice(0, 5).map((j) => <li key={String(j.id)}><span className="font-mono">{j.name}</span> · {formatDate(String(j.created_at), "datetime")} · {String(j.error ?? "").slice(0, 120)}</li>)}</ul></div>}</Card>
        <Card><CardHeader title="Email delivery" description="Last 24 hours" />
          <div className="p-5 pt-3">{!s ? <Skeleton className="h-24" /> : <>
            <div className="flex flex-wrap gap-2">{Object.entries(s.email.last_24h).map(([k, v]) => <Badge key={k} tone={k === "failed" ? "danger" : k === "sent" ? "success" : "neutral"}>{k}: {v}</Badge>)}{!Object.keys(s.email.last_24h).length && <span className="text-sm text-fg-muted">No emails sent.</span>}</div>
            {s.email.failures.length > 0 && <ul className="mt-4 space-y-1.5 text-xs text-fg-muted">{s.email.failures.map((e) => <li key={String(e.id)} className="truncate"><span className="text-danger">failed</span> → {String(e.to_address ?? "")} · {String(e.error ?? "").slice(0, 100)}</li>)}</ul>}</>}</div></Card>
        <Card><CardHeader title="Payment webhooks" description="Last 7 days" />
          <div className="p-5 pt-3">{!s ? <Skeleton className="h-24" /> : <>
            <div className="mb-3 flex flex-wrap gap-2">{Object.entries(s.webhooks.last_7d).map(([k, v]) => <Badge key={k} tone={k === "failed" ? "danger" : k === "processed" ? "success" : "neutral"}>{k}: {v}</Badge>)}{!Object.keys(s.webhooks.last_7d).length && <span className="text-sm text-fg-muted">No webhooks received.</span>}</div>
            <ul className="space-y-1.5 text-xs text-fg-muted">{s.webhooks.recent.slice(0, 6).map((w) => <li key={String(w.id)} className="flex justify-between gap-3"><span className="truncate font-mono">{String(w.provider)} · {String(w.event_type ?? w.type ?? "")}</span><StatusBadge status={String(w.status)} /></li>)}</ul></>}</div></Card>
        <Card><CardHeader title="API errors" description={s ? `${s.api_errors.last_24h} in the last 24 hours` : undefined} />
          <div className="mt-2 overflow-x-auto">{!s ? <Skeleton className="m-4 h-32" /> : !s.api_errors.recent.length ? <Empty text="No server errors recorded. 🎉" /> : <Table><THead><TR><TH>When</TH><TH>Route</TH><TH>Error</TH></TR></THead><TBody>{s.api_errors.recent.slice(0, 8).map((e) => <TR key={String(e.id)}><TD className="whitespace-nowrap text-fg-muted">{timeAgo(String(e.created_at))}</TD><TD className="font-mono text-xs">{String(e.method ?? "")} {String(e.path ?? "")}</TD><TD className="max-w-[240px] truncate text-xs text-danger" title={String(e.message ?? "")}>{String(e.message ?? e.error_type ?? "")}</TD></TR>)}</TBody></Table>}</div></Card>
        <Card><CardHeader title="Integration errors" description="Workspaces whose connections need attention" />
          <div className="mt-2">{!s ? <Skeleton className="m-4 h-24" /> : !s.integration_errors.length ? <Empty text="All integrations healthy." /> : <ul className="divide-y divide-border">{s.integration_errors.map((i, n) => <li key={n} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm"><div className="min-w-0"><p className="font-medium capitalize">{i.provider.replace(/_/g, " ")}</p><p className="truncate text-xs text-fg-muted">{i.error ?? "Needs re-authorisation"}</p></div><StatusBadge status={i.status} /></li>)}</ul>}</div></Card>
        <Card><CardHeader title="Security signals" description="Failed logins, lockouts, token-reuse" />
          <div className="mt-2 overflow-x-auto">{!s ? <Skeleton className="m-4 h-24" /> : !s.auth_events.length ? <Empty text="No suspicious authentication events." /> : <Table><THead><TR><TH>When</TH><TH>Event</TH><TH>Account</TH><TH>IP</TH></TR></THead><TBody>{s.auth_events.map((e) => <TR key={String(e.id)}><TD className="whitespace-nowrap text-fg-muted">{timeAgo(String(e.created_at))}</TD><TD><Badge tone={e.event === "login_failed" ? "warning" : "danger"}>{String(e.event).replace(/_/g, " ")}</Badge></TD><TD className="max-w-[180px] truncate text-xs">{String(e.email ?? "")}</TD><TD className="font-mono text-xs text-fg-muted">{String(e.ip ?? "")}</TD></TR>)}</TBody></Table>}</div></Card>
      </div>
    </>
  );
}
