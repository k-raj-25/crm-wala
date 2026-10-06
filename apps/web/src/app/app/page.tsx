"use client";
import { useQuery } from "@tanstack/react-query";
import { Eye, EyeOff, SlidersHorizontal } from "lucide-react";
import * as React from "react";
import { AreaTrend, BarsChart, Button, Card, CardBody, CardHeader, FunnelBars, LineTrend, Popover, PopoverContent, PopoverTrigger, Segmented, Switch, formatMoneyCompact, formatNumber, formatPercent } from "@crm/ui";
import { ActivityFeed, GettingStarted, Metric, NextBestActions, TodaysFocus, type Focus } from "@/components/dashboard/widgets";
import { PageContainer, PageHeader, Stagger, StaggerItem } from "@/components/shell/page";
import { useUI } from "@/components/shell/ui-context";
import { api } from "@/lib/api";
import { useAccess, useInvalidate, keys } from "@/lib/queries";
import type { Activity } from "@/lib/types";
import { Banknote, Gauge, Handshake, Target, TrendingUp, UserPlus, XCircle, ListChecks } from "lucide-react";

type Dash = {
  range: { from: string; to: string; bucket: string };
  metrics: Record<"revenue" | "pipeline_value" | "deals_won" | "deals_lost" | "conversion_rate" | "new_leads" | "active_deals" | "tasks_due_today", { value: number; delta?: number | null; weighted?: number }>;
  revenue_series: { period: string; revenue: number; deals: number }[];
  pipeline_by_stage: { stage: string; color: string; deals: number; value: number; weighted: number }[];
  lead_funnel: { status: string; count: number }[]; sales_funnel: { stage: string; count: number }[];
  deal_velocity: { period: string; avg_days: number; deals: number }[]; forecast: { period: string; best_case: number; weighted: number; commit: number; deals: number }[];
  activity_feed: Activity[]; focus: Focus;
};
const WIDGETS = [["focus", "Today's Focus"], ["metrics", "Key metrics"], ["revenue", "Revenue over time"], ["pipeline", "Pipeline value"], ["lead_funnel", "Lead conversion"], ["sales_funnel", "Sales funnel"], ["velocity", "Deal velocity"], ["forecast", "Revenue forecast"], ["activity", "Recent activity"], ["nba", "Next best actions"]] as const;
const fmtDay = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const fmtMonth = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { month: "short", year: "2-digit" });

export default function Home() {
  const { me, can, has } = useAccess();
  const ui = useUI(); const inv = useInvalidate();
  const [days, setDays] = React.useState("30");
  const [scope, setScope] = React.useState<"all" | "mine">("all");
  const enabled = new Set(me?.user.preferences.dashboard_widgets ?? WIDGETS.map(([k]) => k));
  const canReports = can("reports.read");
  const q = useQuery({ queryKey: ["dashboard", days, scope], enabled: canReports, queryFn: () => api.get<Dash>("/api/v1/dashboard", { days, scope: scope === "mine" ? "mine" : undefined }), refetchInterval: 120_000 });
  const nba = useQuery({ queryKey: ["nba"], enabled: has("ai_insights") && can("ai.use"), queryFn: () => api.get<{ kind: string; title: string; reason: string; url: string; cta: string }[]>("/api/v1/ai/next-best-actions") });
  const counts = useQuery({ queryKey: ["onboard-counts"], enabled: canReports, queryFn: async () => ({ leads: (await api.page("/api/v1/leads", { per_page: 1 })).meta.total, deals: (await api.page("/api/v1/deals", { per_page: 1 })).meta.total, won: (await api.page("/api/v1/deals", { per_page: 1, status: "won" })).meta.total, converted: (await api.page("/api/v1/leads", { per_page: 1, status: "converted" })).meta.total, team: (await api.get<unknown[]>("/api/v1/team/members")).length }), staleTime: 60_000 });
  const toggle = async (k: string) => { const next = new Set(enabled); next.has(k) ? next.delete(k) : next.add(k); await api.patch("/api/v1/me/preferences", { dashboard_widgets: [...next] }); inv(keys.me); };
  const d = q.data; const m = d?.metrics; const cur = me?.workspace?.currency ?? "INR";
  const hour = new Date().getHours();
  const first = me?.user.name.split(" ")[0];
  const loading = q.isLoading;
  const show = (k: string) => enabled.has(k);
  const steps = counts.data ? [
    { done: counts.data.leads > 0, title: "Create your first lead", description: "Add someone you'd like to sell to.", href: "/app/leads", cta: "Add a lead" },
    { done: counts.data.converted > 0, title: "Convert a lead", description: "Turn a qualified lead into a contact.", href: "/app/leads", cta: "Open leads" },
    { done: counts.data.deals > 0, title: "Create a deal", description: "Track the opportunity and its value.", href: "/app/pipeline", cta: "Open pipeline" },
    { done: counts.data.won > 0, title: "Close a deal", description: "Drag it to Won and watch revenue update.", href: "/app/pipeline", cta: "Go to pipeline" },
    { done: counts.data.team > 1, title: "Invite your team", description: "Sell together with shared context.", href: "/app/settings/team", cta: "Invite people" },
  ] : [];

  if (!canReports) return <PageContainer><PageHeader title={`Good ${hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening"}, ${first}`} description="Use the sidebar to get started." /></PageContainer>;
  return (
    <PageContainer wide>
      <PageHeader title={<>Good {hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening"}, {first} 👋</>} description={new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" }) + " — here's what needs your attention."}
        actions={<>
          <Segmented size="sm" value={scope} onChange={setScope} options={[{ value: "all", label: "Team" }, { value: "mine", label: "Me" }]} />
          <Segmented size="sm" value={days} onChange={setDays} options={[{ value: "7", label: "7d" }, { value: "30", label: "30d" }, { value: "90", label: "90d" }]} />
          <Popover><PopoverTrigger asChild><Button variant="secondary" size="sm"><SlidersHorizontal /> Customize</Button></PopoverTrigger>
            <PopoverContent align="end" className="w-64"><p className="mb-3 text-sm font-semibold">Dashboard widgets</p><ul className="space-y-2.5">{WIDGETS.map(([k, l]) => <li key={k} className="flex items-center justify-between text-sm"><span className="flex items-center gap-2 text-fg-muted">{enabled.has(k) ? <Eye className="size-4" /> : <EyeOff className="size-4" />}{l}</span><Switch checked={enabled.has(k)} onCheckedChange={() => toggle(k)} aria-label={`Show ${l}`} /></li>)}</ul></PopoverContent></Popover>
        </>} />
      <Stagger className="space-y-5">
        {steps.length > 0 && <StaggerItem><GettingStarted steps={steps} /></StaggerItem>}
        {show("focus") && <StaggerItem><TodaysFocus focus={d?.focus} loading={loading} name={first} /></StaggerItem>}
        {show("metrics") && (
          <StaggerItem><div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <Metric icon={Banknote} label="Revenue" loading={loading} value={formatMoneyCompact(m?.revenue.value, cur)} delta={m?.revenue.delta} sub={`last ${days} days`} />
            <Metric icon={TrendingUp} label="Pipeline value" loading={loading} value={formatMoneyCompact(m?.pipeline_value.value, cur)} sub={`${formatMoneyCompact(m?.pipeline_value.weighted, cur)} weighted`} href="/app/pipeline" />
            <Metric icon={Handshake} label="Deals won" loading={loading} value={formatNumber(m?.deals_won.value)} delta={m?.deals_won.delta} sub={`last ${days} days`} />
            <Metric icon={XCircle} label="Deals lost" loading={loading} value={formatNumber(m?.deals_lost.value)} delta={m?.deals_lost.delta} invert sub={`last ${days} days`} />
            <Metric icon={Gauge} label="Conversion rate" loading={loading} value={formatPercent(m?.conversion_rate.value)} delta={m?.conversion_rate.delta} deltaSuffix=" pts" sub="won ÷ closed" />
            <Metric icon={UserPlus} label="New leads" loading={loading} value={formatNumber(m?.new_leads.value)} delta={m?.new_leads.delta} sub={`last ${days} days`} href="/app/leads" />
            <Metric icon={Target} label="Active deals" loading={loading} value={formatNumber(m?.active_deals.value)} href="/app/deals" sub="open right now" />
            <Metric icon={ListChecks} label="Tasks due today" loading={loading} value={formatNumber(m?.tasks_due_today.value)} href="/app/tasks" sub="across the team" />
          </div></StaggerItem>)}
        <div className="grid gap-4 xl:grid-cols-3">
          {show("revenue") && <StaggerItem className="xl:col-span-2"><Card className="h-full"><CardHeader title="Revenue over time" description="Closed-won deal value" /><CardBody>{loading ? <div className="skeleton h-[260px]" /> : <AreaTrend data={d!.revenue_series} xKey="period" series={[{ key: "revenue", label: "Revenue" }]} format={(v) => formatMoneyCompact(v, cur)} xFormat={d!.range.bucket === "month" ? fmtMonth : fmtDay} height={260} />}</CardBody></Card></StaggerItem>}
          {show("pipeline") && <StaggerItem><Card className="h-full"><CardHeader title="Pipeline value" description="Open deals by stage" /><CardBody>{loading ? <div className="skeleton h-[260px]" /> : d!.pipeline_by_stage.every((s) => !s.deals) ? <p className="py-20 text-center text-sm text-fg-muted">No open deals yet</p> : <BarsChart horizontal data={d!.pipeline_by_stage} xKey="stage" series={[{ key: "value", label: "Value" }, { key: "weighted", label: "Weighted" }]} format={(v) => formatMoneyCompact(v, cur)} height={260} />}</CardBody></Card></StaggerItem>}
          {show("lead_funnel") && <StaggerItem><Card className="h-full"><CardHeader title="Lead conversion" description="New leads by status" /><CardBody>{loading ? <div className="skeleton h-[220px]" /> : <FunnelBars steps={d!.lead_funnel.filter((s) => s.status !== "lost" && s.status !== "unqualified").map((s) => ({ label: s.status.replace(/^\w/, (c) => c.toUpperCase()), value: s.count }))} />}</CardBody></Card></StaggerItem>}
          {show("sales_funnel") && <StaggerItem><Card className="h-full"><CardHeader title="Sales funnel" description="Deals reaching each stage" /><CardBody>{loading ? <div className="skeleton h-[220px]" /> : <FunnelBars steps={d!.sales_funnel.map((s) => ({ label: s.stage, value: s.count }))} />}</CardBody></Card></StaggerItem>}
          {show("velocity") && <StaggerItem><Card className="h-full"><CardHeader title="Deal velocity" description="Average days to close" /><CardBody>{loading ? <div className="skeleton h-[220px]" /> : d!.deal_velocity.length < 2 ? <p className="py-16 text-center text-sm text-fg-muted">Close a few deals to see how fast you sell</p> : <LineTrend data={d!.deal_velocity} xKey="period" series={[{ key: "avg_days", label: "Avg days" }]} format={(v) => `${v}d`} xFormat={fmtMonth} height={220} />}</CardBody></Card></StaggerItem>}
          {show("forecast") && <StaggerItem className="xl:col-span-2"><Card className="h-full"><CardHeader title="Revenue forecast" description="Next 6 months, from expected close dates" /><CardBody>{loading ? <div className="skeleton h-[240px]" /> : <BarsChart data={d!.forecast} xKey="period" series={[{ key: "commit", label: "Commit (≥70%)" }, { key: "weighted", label: "Weighted" }, { key: "best_case", label: "Best case" }]} format={(v) => formatMoneyCompact(v, cur)} xFormat={fmtMonth} height={240} />}</CardBody></Card></StaggerItem>}
          {show("nba") && has("ai_insights") && <StaggerItem><NextBestActions items={nba.data} loading={nba.isLoading} /></StaggerItem>}
          {show("activity") && <StaggerItem className={has("ai_insights") && show("nba") ? "xl:col-span-2" : "xl:col-span-1"}><ActivityFeed items={d?.activity_feed} loading={loading} /></StaggerItem>}
        </div>
      </Stagger>
    </PageContainer>
  );
}
