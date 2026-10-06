"use client";
import { useQuery } from "@tanstack/react-query";
import { BarsChart, Card, CardBody, CardHeader, ErrorState, FunnelBars, LineTrend, Skeleton, Table, TBody, TD, TH, THead, TR } from "@crm/ui";
import { PageHeader, Reveal, Stat, shortDay } from "@/components/bits";
import { A, api } from "@/lib/api";

type Data = {
  active_users: { dau: number; wau: number; mau: number }; dau_series: { period: string; dau: number }[]; feature_usage: { feature: string; actions: number }[]; events: { name: string; count: number }[];
  integrations: { provider: string; connected: number }[]; avg_actions_per_active_day: number; funnel: { step: string; count: number }[];
  trial_engagement: { trial_workspaces: number; lead_created: number; deal_created: number; automation_created: number; ai_chat: number }; ai_consumption: { workspace: string; actions: number; tokens: number }[];
};
const label = (s: string) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

export default function Page() {
  const q = useQuery({ queryKey: ["analytics"], queryFn: () => api.get<Data>(`${A}/analytics`) });
  const d = q.data;
  if (q.isError) return <ErrorState kind="unavailable" onRetry={() => q.refetch()} />;
  const te = d?.trial_engagement;
  const pct = (n?: number) => (te && te.trial_workspaces ? `${Math.round(((n ?? 0) / te.trial_workspaces) * 100)}%` : "—");
  return (
    <>
      <PageHeader title="Product analytics" description="How customers use the product — last 30 days unless noted." />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[["DAU", d?.active_users.dau, "Active today"], ["WAU", d?.active_users.wau, "Last 7 days"], ["MAU", d?.active_users.mau, "Last 30 days"], ["Actions / active day", d?.avg_actions_per_active_day, "Per user"]].map(([l, v, h], i) => <Reveal key={l as string} delay={i * 0.03}><Stat label={l as string} value={v as number} hint={h as string} loading={!d} /></Reveal>)}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader title="Daily active users" /><CardBody>{!d ? <Skeleton className="h-[240px]" /> : <LineTrend data={d.dau_series} xKey="period" xFormat={shortDay} series={[{ key: "dau", label: "Active users" }]} />}</CardBody></Card>
        <Card><CardHeader title="Feature usage" description="Recorded actions by area" /><CardBody>{!d ? <Skeleton className="h-[240px]" /> : d.feature_usage.length ? <BarsChart horizontal data={d.feature_usage.map((f) => ({ ...f, feature: label(f.feature) }))} xKey="feature" series={[{ key: "actions", label: "Actions" }]} height={Math.max(200, d.feature_usage.length * 32)} /> : <p className="text-sm text-fg-muted">No activity recorded yet.</p>}</CardBody></Card>
        <Card><CardHeader title="Activation funnel" description="Workspaces reaching each milestone (all time)" /><CardBody>{!d ? <Skeleton className="h-[240px]" /> : <FunnelBars steps={d.funnel.map((f) => ({ label: label(f.step), value: f.count }))} />}</CardBody></Card>
        <Card><CardHeader title="Trial engagement" description={te ? `${te.trial_workspaces} trial / expired workspaces` : undefined} />
          <CardBody>{!te ? <Skeleton className="h-[200px]" /> : <ul className="space-y-3">{([["lead_created", "Created a lead"], ["deal_created", "Created a deal"], ["automation_created", "Built an automation"], ["ai_chat", "Used the AI assistant"]] as const).map(([k, l]) => (
            <li key={k}><div className="mb-1 flex justify-between text-sm"><span>{l}</span><span className="tabular text-fg-muted">{te[k]} · {pct(te[k])}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-bg-subtle"><div className="h-full rounded-full bg-primary" style={{ width: pct(te[k]) === "—" ? 0 : pct(te[k]) }} /></div></li>))}</ul>}</CardBody></Card>
        <Card><CardHeader title="Top AI consumers" description="This calendar month" />
          <div className="overflow-x-auto p-2">{!d ? <Skeleton className="m-3 h-32" /> : d.ai_consumption.length ? <Table><THead><TR><TH>Workspace</TH><TH className="text-right">Actions</TH><TH className="text-right">Tokens</TH></TR></THead><TBody>{d.ai_consumption.map((r) => <TR key={r.workspace}><TD>{r.workspace}</TD><TD className="tabular text-right">{r.actions}</TD><TD className="tabular text-right">{r.tokens.toLocaleString()}</TD></TR>)}</TBody></Table> : <p className="p-3 text-sm text-fg-muted">No AI usage this month.</p>}</div></Card>
        <Card><CardHeader title="Connected integrations" /><CardBody>{!d ? <Skeleton className="h-[200px]" /> : d.integrations.length ? <BarsChart horizontal data={d.integrations.map((i) => ({ ...i, provider: label(i.provider) }))} xKey="provider" series={[{ key: "connected", label: "Workspaces" }]} height={Math.max(160, d.integrations.length * 34)} /> : <p className="text-sm text-fg-muted">No integrations connected yet.</p>}</CardBody></Card>
      </div>
    </>
  );
}
