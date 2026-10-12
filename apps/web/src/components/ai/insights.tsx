"use client";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Brain, Building2, GraduationCap, RefreshCw, TrendingDown, Wand2, Wrench, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, BarsChart, Button, Card, CardBody, CardHeader, ErrorState, Skeleton, cn, formatMoneyCompact } from "@crm/ui";
import { Markdown } from "@/components/markdown";
import { type AiProposal, useAiFeature } from "@/lib/ai";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { ProposalList } from "./proposal-card";
import type { TeamRow } from "./my-day";

type Insight = { kind: string; title: string; reason: string; url: string; cta: string };
const SLOW = 5 * 60_000;

function Refresh({ q }: { q: { refetch: () => unknown; isFetching: boolean } }) {
  return <Button size="sm" variant="ghost" onClick={() => q.refetch()} disabled={q.isFetching}><RefreshCw className={cn(q.isFetching && "animate-spin")} /> Refresh</Button>;
}
const Loading = () => <div className="space-y-2.5"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-4 w-2/3" /><Skeleton className="mt-4 h-32" /></div>;
const Failed = ({ e }: { e: unknown }) => <p className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{(e as Error)?.message ?? "Couldn't load this right now."}</p>;
const title = (Icon: React.ElementType, t: string, cls = "text-primary") => <span className="flex items-center gap-2"><Icon className={cn("size-4", cls)} /> {t}</span>;

function AiInsights() {
  const { can } = useAccess();
  const reports = can("reports.read");
  const loss = useQuery({ queryKey: ["ai-loss", 180], enabled: reports, staleTime: SLOW, retry: false, queryFn: () => api.get<{ text: string; reasons: { label: string; value: number }[]; total: number; days: number }>("/api/v1/ai/loss-analysis", { days: 180 }) });
  const inv = useQuery({ queryKey: ["ai-inventory-advice"], enabled: can("units.read"), staleTime: SLOW, retry: false, queryFn: () => api.get<{ text: string; slow: { id: string; label: string; days: number; price: string | null; url?: string }[] }>("/api/v1/ai/inventory-advice") });
  const coach = useQuery({ queryKey: ["ai-coaching", 7], enabled: reports, staleTime: SLOW, retry: false, queryFn: () => api.get<{ text: string; team: TeamRow[]; days: number }>("/api/v1/ai/coaching", { days: 7 }) });
  const fixes = useQuery({ queryKey: ["ai-data-fixes"], enabled: can("leads.update"), staleTime: SLOW, retry: false, queryFn: () => api.get<AiProposal[]>("/api/v1/ai/data-fixes") });
  return (<>
    {reports && <Card><CardHeader title={title(XCircle, "Why we lose deals", "text-danger")} description={loss.data ? `${loss.data.total} lost in the last ${loss.data.days} days` : "Last 6 months"} actions={<Refresh q={loss} />} />
      <CardBody className="space-y-4 pt-3">{loss.isLoading ? <Loading /> : loss.isError ? <Failed e={loss.error} /> : loss.data && <>
        <Markdown>{loss.data.text}</Markdown>
        {loss.data.reasons.length > 0 && <BarsChart horizontal data={loss.data.reasons} xKey="label" series={[{ key: "value", label: "Lost" }]} height={Math.max(160, loss.data.reasons.length * 32)} />}</>}</CardBody></Card>}
    {can("units.read") && <Card><CardHeader title={title(Building2, "What to push this month")} description="Demand vs what you have in stock" actions={<Refresh q={inv} />} />
      <CardBody className="space-y-4 pt-3">{inv.isLoading ? <Loading /> : inv.isError ? <Failed e={inv.error} /> : inv.data && <>
        <Markdown>{inv.data.text}</Markdown>
        {inv.data.slow.length > 0 && <div><p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-fg-subtle">Slowest to sell</p><ul className="divide-y divide-border rounded-xl border border-border">{inv.data.slow.map((s) => <li key={s.id}><Link href={s.url ?? "#"} className="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-surface-hover"><span className="min-w-0 truncate font-medium">{s.label}</span><span className="shrink-0 text-xs text-fg-muted">{s.price && s.price !== "—" ? `${s.price} · ` : ""}{s.days} days</span></Link></li>)}</ul></div>}</>}</CardBody></Card>}
    {reports && <Card className="lg:col-span-2"><CardHeader title={title(GraduationCap, "Weekly coaching")} description="What to praise and what to fix for each agent, last 7 days" actions={<Refresh q={coach} />} />
      <CardBody className="grid gap-5 pt-3 lg:grid-cols-2">{coach.isLoading ? <><Loading /><Skeleton className="h-40" /></> : coach.isError ? <Failed e={coach.error} /> : coach.data && <>
        <Markdown>{coach.data.text}</Markdown>
        <div className="overflow-x-auto"><table className="w-full text-[13px]"><thead><tr className="border-b border-border text-left text-xs text-fg-subtle"><th className="px-2 py-1.5 font-medium">Agent</th><th className="px-2 py-1.5 text-right font-medium">New</th><th className="px-2 py-1.5 text-right font-medium">Not called</th><th className="px-2 py-1.5 text-right font-medium">Visits</th><th className="px-2 py-1.5 text-right font-medium">Won</th><th className="px-2 py-1.5 text-right font-medium">First reply</th></tr></thead>
          <tbody>{coach.data.team.map((r) => <tr key={r.user_id} className="border-b border-border last:border-0"><td className="px-2 py-1.5 font-medium">{r.name}</td><td className="tabular px-2 py-1.5 text-right">{r.new_leads}</td><td className={cn("tabular px-2 py-1.5 text-right", r.uncontacted > 0 && "font-semibold text-danger")}>{r.uncontacted}</td><td className="tabular px-2 py-1.5 text-right">{r.visits}</td><td className="tabular px-2 py-1.5 text-right">{r.won}</td><td className={cn("tabular px-2 py-1.5 text-right", (r.median_response_hours ?? 0) > 4 && "font-semibold text-danger")}>{r.median_response_hours == null ? "—" : `${r.median_response_hours}h`}</td></tr>)}</tbody></table></div></>}</CardBody></Card>}
    {can("leads.update") && <Card className="lg:col-span-2"><CardHeader title={title(Wrench, "One-click fixes")} description="Tidy phone numbers and fill requirements written in notes. Check each change, then approve." actions={<Refresh q={fixes} />} />
      <CardBody className="pt-3">{fixes.isLoading ? <Loading /> : fixes.isError ? <Failed e={fixes.error} /> : !fixes.data?.length ? <p className="py-6 text-center text-sm text-fg-muted">Nothing to fix right now.</p> : <ProposalList items={fixes.data} />}</CardBody></Card>}
  </>);
}

export function Insights() {
  const { has } = useAccess(); const ai = useAiFeature("insights");
  const nba = useQuery({ queryKey: ["nba"], enabled: has("ai_insights"), queryFn: () => api.get<Insight[]>("/api/v1/ai/next-best-actions") });
  const churn = useQuery({ queryKey: ["churn"], enabled: has("ai_insights"), queryFn: () => api.get<{ company_id: string; name: string; revenue: number; days_inactive: number; risk: number; reason: string; url: string }[]>("/api/v1/ai/churn-risk") });
  const clean = useQuery({ queryKey: ["cleanup"], enabled: has("ai_insights"), queryFn: () => api.get<{ kind: string; count: number; title: string; detail: string; url: string }[]>("/api/v1/ai/data-cleanup") });
  const diag = useQuery({ queryKey: ["diag"], enabled: has("ai_insights"), queryFn: () => api.get<{ direction: string; days: number; findings: { severity: string; title: string; detail: string }[] }>("/api/v1/ai/pipeline-diagnosis") });
  if (!has("ai_insights")) return <ErrorState kind="permission" title="AI insights are on Growth and above" description="Next-best-actions, churn-risk detection, pipeline diagnosis and data cleanup suggestions." action={<Button asChild><Link href="/app/billing">Compare plans</Link></Button>} />;
  const sev = { high: "danger", medium: "warning", low: "success" } as const;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader title={title(Wand2, "Next best actions")} description="What to do next, in priority order" /><CardBody className="pt-3">{nba.isLoading ? <Skeleton className="h-40" /> : !nba.data?.length ? <p className="py-6 text-center text-sm text-fg-muted">Nothing urgent. 🎉</p> : <ul className="space-y-2">{nba.data.map((a, i) => <li key={i}><Link href={a.url} className="flex items-center gap-3 rounded-lg border border-border p-3 hover:border-primary/40 hover:bg-primary-soft/40"><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{a.title}</span><span className="block text-xs text-fg-muted">{a.reason}</span></span><span className="text-xs font-medium text-primary">{a.cta} →</span></Link></li>)}</ul>}</CardBody></Card>
      <Card><CardHeader title={title(TrendingDown, "Pipeline diagnosis")} description={diag.data ? `Last ${diag.data.days} days vs the period before, looking ${diag.data.direction}` : undefined} /><CardBody className="pt-3">{diag.isLoading ? <Skeleton className="h-40" /> : <ul className="space-y-3">{diag.data?.findings.map((f, i) => <li key={i} className="flex gap-3"><Badge tone={sev[f.severity as keyof typeof sev] ?? "neutral"}>{f.severity}</Badge><div><p className="text-sm font-medium">{f.title}</p><p className="text-[13px] text-fg-muted">{f.detail}</p></div></li>)}</ul>}</CardBody></Card>
      {ai && <AiInsights />}
      <Card><CardHeader title={title(AlertTriangle, "Churn risk", "text-warning")} description="Customers going quiet" /><CardBody className="pt-3">{churn.isLoading ? <Skeleton className="h-32" /> : !churn.data?.length ? <p className="py-6 text-center text-sm text-fg-muted">No customers at risk right now.</p> : <ul className="divide-y divide-border">{churn.data.map((c) => <li key={c.company_id}><Link href={c.url} className="flex items-center gap-3 py-3 hover:text-primary"><Avatar name={c.name} size={32} square /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{c.name}</span><span className="block text-xs text-fg-muted">{c.reason}</span></span><span className="text-right"><span className="tabular block text-sm font-semibold">{formatMoneyCompact(c.revenue)}</span><Badge tone={c.risk > 70 ? "danger" : "warning"}>{c.risk}% risk</Badge></span></Link></li>)}</ul>}</CardBody></Card>
      <Card><CardHeader title={title(Brain, "Data cleanup")} description="Keep your CRM tidy" /><CardBody className="pt-3">{clean.isLoading ? <Skeleton className="h-32" /> : !clean.data?.length ? <p className="py-6 text-center text-sm text-fg-muted">Your data looks clean. ✨</p> : <ul className="divide-y divide-border">{clean.data.map((c) => <li key={c.kind}><Link href={c.url} className="flex items-center justify-between gap-3 py-3 hover:text-primary"><span><span className="block text-sm font-medium">{c.title}</span><span className="block text-xs text-fg-muted">{c.detail}</span></span><Badge tone="warning">{c.count}</Badge></Link></li>)}</ul>}</CardBody></Card>
    </div>
  );
}
