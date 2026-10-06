"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AreaTrend, BarsChart, Card, CardBody, CardHeader, DonutChart, ErrorState, LineTrend, Segmented, Skeleton } from "@crm/ui";
import { PageHeader, Reveal, Stat, inr, shortDay } from "@/components/bits";
import { A, api } from "@/lib/api";

type Dash = {
  metrics: Record<string, number>;
  charts: {
    user_growth: { period: string; users: number; workspaces: number; total_users: number }[]; revenue: { period: string; revenue: number }[];
    trial_conversion: { period: string; trials: number; converted: number; rate: number }[]; subscriptions: { period: string; new: number; cancelled: number }[];
    plan_distribution: { plan: string; workspaces: number }[];
  };
};
const RANGES = [{ value: "7", label: "7d" }, { value: "30", label: "30d" }, { value: "90", label: "90d" }] as const;
const monthLabel = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { month: "short" });

export default function Page() {
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const from = new Date(Date.now() - +days * 864e5).toISOString().slice(0, 10);
  const q = useQuery({ queryKey: ["dash", days], queryFn: () => api.get<Dash>(`${A}/dashboard`, { from }) });
  const m = q.data?.metrics;
  const c = q.data?.charts;
  const pct = (v?: number) => (v === undefined ? "—" : `${v}%`);

  return (
    <>
      <PageHeader title="Platform overview" description="Growth, revenue and health across every workspace." actions={<Segmented size="sm" value={days} onChange={setDays} options={[...RANGES]} />} />
      {q.isError ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} /> : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {[
              ["MRR", m && inr(m.mrr), "Monthly recurring revenue"], ["ARR", m && inr(m.arr), "MRR × 12"], ["Total users", m?.total_users.toLocaleString(), m && `${m.new_users} new in range`], ["Workspaces", m?.total_workspaces.toLocaleString(), m && `${m.active_workspaces} active in 30d`],
              ["On trial", m?.trial_workspaces.toLocaleString(), "Currently in trial"], ["Paying", m?.paid_workspaces.toLocaleString(), "Active subscriptions"], ["Trial → paid", pct(m?.trial_conversion_rate), "Finished trials that converted"], ["Churn (30d)", pct(m?.churn_rate), m && `${m.cancelled_subscriptions} cancelled / cancelling`],
            ].map(([label, value, hint], i) => <Reveal key={label as string} delay={i * 0.03}><Stat label={label as string} value={value} hint={hint} loading={q.isLoading} tone={label === "Churn (30d)" && (m?.churn_rate ?? 0) > 8 ? "danger" : undefined} /></Reveal>)}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader title="Signups" description="New users and workspaces per day" />
              <CardBody>{!c ? <Skeleton className="h-[240px]" /> : <LineTrend data={c.user_growth} xKey="period" xFormat={shortDay} series={[{ key: "users", label: "Users" }, { key: "workspaces", label: "Workspaces", color: "var(--series-2)" }]} />}</CardBody></Card>
            <Card><CardHeader title="Revenue" description="Net of refunds, per day" />
              <CardBody>{!c ? <Skeleton className="h-[240px]" /> : <AreaTrend data={c.revenue} xKey="period" xFormat={shortDay} series={[{ key: "revenue", label: "Revenue" }]} format={(v) => inr(v)} />}</CardBody></Card>
            <Card><CardHeader title="Trial conversion" description="Workspaces created per month vs. those that became paying" />
              <CardBody>{!c ? <Skeleton className="h-[240px]" /> : <BarsChart data={c.trial_conversion} xKey="period" xFormat={monthLabel} series={[{ key: "trials", label: "Trials started" }, { key: "converted", label: "Converted", color: "var(--series-2)" }]} />}</CardBody></Card>
            <Card><CardHeader title="Subscriptions" description="New vs. cancelled per day" />
              <CardBody>{!c ? <Skeleton className="h-[240px]" /> : <BarsChart stacked data={c.subscriptions} xKey="period" xFormat={shortDay} series={[{ key: "new", label: "New" }, { key: "cancelled", label: "Cancelled", color: "var(--series-5)" }]} />}</CardBody></Card>
          </div>
          <Card><CardHeader title="Plan distribution" description="Workspaces by plan (excluding demo)" />
            <CardBody>{!c ? <Skeleton className="h-[200px]" /> : c.plan_distribution.length === 0 ? <p className="text-sm text-fg-muted">No workspaces yet.</p> :
              <div className="grid items-center gap-6 sm:grid-cols-[220px_1fr]"><DonutChart data={c.plan_distribution.map((p) => ({ name: p.plan, value: p.workspaces }))} center={<span className="text-xs text-fg-muted">workspaces</span>} />
                <ul className="grid gap-2 text-sm sm:grid-cols-2">{c.plan_distribution.map((p) => <li key={p.plan} className="flex justify-between rounded-lg bg-bg-subtle px-3 py-2"><span className="capitalize">{p.plan.replace(/_/g, " ")}</span><span className="tabular font-medium">{p.workspaces}</span></li>)}</ul></div>}</CardBody></Card>
        </div>
      )}
    </>
  );
}
