"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { animate, motion, useReducedMotion } from "framer-motion";
import { BarChart3, Bookmark, Building2, CalendarClock, Download, FileText, Filter, Gauge, Handshake, IndianRupee, Lock, Magnet, Sparkles, Table2, Target, TrendingUp, Trash2, UserPlus, Users, Zap } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { AreaTrend, Avatar, BarsChart, Button, Card, CardBody, CardHeader, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Field, FunnelBars, Input, LineTrend, NativeSelect, Segmented, Skeleton, cn, formatMoney, formatMoneyCompact, formatNumber, formatPercent, useTheme, useToast } from "@crm/ui";
import { MemberSelect } from "@/components/forms/fields";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess, usePipelines } from "@/lib/queries";
import { STATUS } from "@/lib/realestate";
import type { UnitStatus } from "@/lib/realestate";

type Col = { key: string; label: string; type: "text" | "date" | "number" | "currency" | "percent" };
type Row = Record<string, unknown>;
type Report = { title: string; type: string; columns: Col[]; rows: Row[]; range: { from: string; to: string }; chart: { type: "area" | "bar" | "line"; x: string; stacked?: boolean; series: { key: string; label: string }[] }; summary: { label: string; value: number; format: "currency" | "number" | "percent" }[]; breakdown?: { title: string; rows: { label: string; value: number; avg_score?: number; format?: string }[] } };
type Saved = { id: string; name: string; report_type: string; params: Record<string, string>; schedule: string | null; recipients: string[] };

/** One tile per report: a plain-English question, an icon and a colour (series colours, so it follows the theme). */
const META: Record<string, { label: string; ask: string; icon: LucideIcon; tone: number }> = {
  revenue: { label: "Revenue", ask: "How much have we earned?", icon: IndianRupee, tone: 3 },
  sales: { label: "Sales by agent", ask: "Who is closing deals?", icon: Handshake, tone: 1 },
  forecast: { label: "Forecast", ask: "What will we earn next?", icon: TrendingUp, tone: 7 },
  pipeline: { label: "Deals in progress", ask: "Where are our deals stuck?", icon: Filter, tone: 4 },
  leads: { label: "New leads", ask: "Where do leads come from?", icon: Magnet, tone: 2 },
  conversion: { label: "Conversion", ask: "How many leads become clients?", icon: Target, tone: 5 },
  customer_acquisition: { label: "New clients", ask: "How fast are we adding clients?", icon: UserPlus, tone: 6 },
  team_performance: { label: "Team", ask: "How is each agent doing?", icon: Users, tone: 1 },
  deal_velocity: { label: "Closing speed", ask: "How long does a deal take?", icon: Gauge, tone: 2 },
  activity: { label: "Activity", ask: "How much work is happening?", icon: Zap, tone: 4 },
  inventory: { label: "Inventory", ask: "How many flats are left?", icon: Building2, tone: 3 },
};
const GROUPS: { title: string; keys: string[] }[] = [
  { title: "Money", keys: ["revenue", "sales", "forecast", "pipeline"] },
  { title: "Leads & clients", keys: ["leads", "conversion", "customer_acquisition"] },
  { title: "Team & property", keys: ["team_performance", "deal_velocity", "activity", "inventory"] },
];
const ADVANCED = new Set(["team_performance", "deal_velocity", "forecast", "customer_acquisition", "activity", "conversion"]);
const RANGES = [{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "3 months" }, { value: "365", label: "12 months" }, { value: "custom", label: "Custom" }];
const tint = (n: number, pct = 14) => `color-mix(in oklab, var(--series-${n}) ${pct}%, transparent)`;
const fmtDate = (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(v).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : v;

function CountUp({ to, fmt }: { to: number; fmt: (n: number) => string }) {
  const reduce = useReducedMotion();
  const [v, setV] = React.useState(reduce ? to : 0);
  React.useEffect(() => { if (reduce) { setV(to); return; } const c = animate(0, to, { duration: 0.9, ease: [0.16, 1, 0.3, 1], onUpdate: setV }); return () => c.stop(); }, [to, reduce]);
  return <>{fmt(v)}</>;
}

export default function ReportsPage() {
  const { can, has } = useAccess(); const toast = useToast(); const qc = useQueryClient(); const pipelines = usePipelines(); const { resolved } = useTheme();
  const [type, setType] = React.useState("revenue"); const [days, setDays] = React.useState("30"); const [from, setFrom] = React.useState(""); const [to, setTo] = React.useState("");
  const [owner, setOwner] = React.useState<string | null>(null); const [pipeline, setPipeline] = React.useState(""); const [tableView, setTableView] = React.useState(false); const [saveOpen, setSaveOpen] = React.useState(false);
  const locked = ADVANCED.has(type) && !has("advanced_reports");
  const params = { ...(days === "custom" ? { from, to } : { days }), owner_id: owner, pipeline_id: pipeline || undefined };
  const q = useQuery({ queryKey: ["report", type, params], enabled: !locked && (days !== "custom" || (!!from && !!to)), queryFn: () => api.get<Report>(`/api/v1/reports/${type}`, params) });
  const saved = useQuery({ queryKey: ["saved-reports"], queryFn: () => api.get<Saved[]>("/api/v1/saved-reports") });
  const del = useMutation({ mutationFn: (id: string) => api.delete(`/api/v1/saved-reports/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["saved-reports"] }) });
  const r = q.data; const cur = "INR"; const meta = META[type]; const dark = resolved === "dark";
  const kind = (k: string) => r?.columns.find((c) => c.key === k)?.type;
  const fmt = (series: { key: string }[]) => { const t = kind(series[0]?.key); return t === "currency" ? (v: number) => formatMoneyCompact(v, cur) : t === "percent" ? (v: number) => `${v}%` : (v: number) => formatNumber(v); };
  const cell = (c: Col, v: unknown) => v == null ? "—" : c.type === "currency" ? formatMoney(v as number, cur) : c.type === "percent" ? formatPercent(v as number) : c.type === "number" ? formatNumber(v as number) : c.type === "date" ? fmtDate(String(v)) : String(v);
  const download = async (ext: "csv" | "pdf") => { const res = await api.raw("GET", `/api/v1/reports/${type}/export.${ext}${api.qs(params)}`); if (!res.ok) { toast.error("Export failed", "Please try again."); return; } const u = URL.createObjectURL(await res.blob()); const a = document.createElement("a"); a.href = u; a.download = `${type}-report.${ext}`; a.click(); URL.revokeObjectURL(u); };
  const summaryFmt = (s: Report["summary"][number]) => (n: number) => s.format === "currency" ? formatMoneyCompact(n, cur) : s.format === "percent" ? formatPercent(n) : formatNumber(Math.round(n * 10) / 10);
  const Chart = r && (r.chart.type === "area" ? AreaTrend : r.chart.type === "line" ? LineTrend : BarsChart);
  // The inventory chart uses the same colours as the building view, so a flat looks the same everywhere.
  const series = r?.chart.series.map((s) => (s.key in STATUS ? { ...s, color: dark ? STATUS[s.key as UnitStatus].bgDark : STATUS[s.key as UnitStatus].bg } : s)) ?? [];
  const insight = r ? makeInsight(type, r, cur) : null;
  const isRanking = type === "sales" || type === "team_performance";

  return (
    <PageContainer wide>
      <PageHeader title="Reports" description="Your business in plain numbers. Pick a question, see the answer."
        actions={<>{can("data.export") && <><Button variant="secondary" onClick={() => download("csv")} disabled={!r}><Download /> CSV</Button><Button variant="secondary" onClick={() => download("pdf")} disabled={!r}><FileText /> PDF</Button></>}{can("reports.manage") && <Button onClick={() => setSaveOpen(true)} disabled={!r}><Bookmark /> Save / schedule</Button>}</>} />

      {/* 1 — what do you want to know? */}
      <div className="space-y-4">
        {GROUPS.map((g) => (
          <section key={g.title} aria-label={g.title}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-subtle">{g.title}</p>
            <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
              {g.keys.map((k) => {
                const m = META[k]; const on = type === k; const lockedTile = ADVANCED.has(k) && !has("advanced_reports"); const Icon = m.icon;
                return (
                  <button key={k} onClick={() => setType(k)} aria-pressed={on}
                    className={cn("group relative flex items-center gap-3 rounded-xl border p-3 text-left transition-all", on ? "border-primary bg-surface shadow-md ring-2 ring-primary/25" : "border-border bg-surface hover:-translate-y-0.5 hover:border-border-strong hover:shadow-md")}>
                    <span className="grid size-10 shrink-0 place-items-center rounded-lg transition-transform group-hover:scale-105" style={{ background: tint(m.tone, on ? 22 : 14), color: `var(--series-${m.tone})` }}><Icon className="size-5" /></span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 text-[13.5px] font-semibold text-fg">{m.label}{lockedTile && <Lock className="size-3 text-fg-subtle" />}</span>
                      <span className="line-clamp-2 text-xs leading-snug text-fg-muted">{m.ask}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
        {(saved.data?.length ?? 0) > 0 && (
          <section aria-label="Saved reports" className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-fg-subtle"><Bookmark className="size-3.5" /> Saved</span>
            {saved.data!.map((s) => (
              <span key={s.id} className="group inline-flex items-center rounded-full border border-border bg-surface pl-3 text-[13px] text-fg-muted transition-colors hover:border-border-strong hover:text-fg">
                <button onClick={() => { setType(s.report_type); const p = s.params; setDays(p.days ?? "30"); setOwner(p.owner_id ?? null); }} className="py-1 pr-1">{s.name}{s.schedule && <CalendarClock className="ml-1.5 inline size-3 text-primary" />}</button>
                <button aria-label={`Delete ${s.name}`} onClick={() => del.mutate(s.id)} className="rounded-full p-1.5 text-fg-subtle opacity-0 hover:text-danger focus:opacity-100 group-hover:opacity-100"><Trash2 className="size-3" /></button>
              </span>
            ))}
          </section>
        )}
      </div>

      {/* 2 — for when, and for whom */}
      <div className="mt-6 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2.5">
        <Segmented size="sm" value={days} onChange={setDays} options={RANGES} />
        {days === "custom" && <><Input type="date" className="h-8 w-40" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" /><span className="text-fg-subtle">→</span><Input type="date" className="h-8 w-40" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" /></>}
        <div className="w-44"><MemberSelect value={owner} onChange={setOwner} noneLabel="Whole team" size="sm" /></div>
        {type === "pipeline" && (pipelines.data?.length ?? 0) > 1 && <NativeSelect className="h-8 w-44 text-[13px]" value={pipeline} onChange={(e) => setPipeline(e.target.value)} aria-label="Pipeline"><option value="">Default pipeline</option>{pipelines.data!.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</NativeSelect>}
        {r && <span className="ml-auto hidden text-xs text-fg-subtle sm:block">{fmtDate(r.range.from.slice(0, 10))} → {fmtDate(r.range.to.slice(0, 10))}</span>}
      </div>

      {/* 3 — the answer */}
      <div className="mt-4 space-y-4" key={type}>
        {locked ? <ErrorState kind="permission" title="This report is on Growth and above" description="Upgrade to unlock team, forecast, closing speed and more." action={<Button asChild><Link href="/app/billing">Compare plans</Link></Button>} />
          : q.isError ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} />
          : q.isLoading || !r ? <div className="space-y-4"><div className="grid gap-3 sm:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div><Skeleton className="h-80" /></div>
          : (
            <>
              {insight && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="relative overflow-hidden rounded-xl border border-border p-4 sm:p-5" style={{ background: `linear-gradient(120deg, ${tint(meta.tone, 16)}, ${tint(meta.tone, 4)} 60%, transparent)` }}>
                  <div className="flex items-start gap-3">
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-surface shadow-sm" style={{ color: `var(--series-${meta.tone})` }}><Sparkles className="size-[18px]" /></span>
                    <div><p className="text-xs font-semibold uppercase tracking-wider text-fg-subtle">At a glance</p><p className="mt-0.5 text-[15px] font-medium leading-snug text-fg sm:text-base">{insight}</p></div>
                  </div>
                </motion.div>
              )}

              <div className={cn("grid gap-3", r.summary.length >= 4 ? "sm:grid-cols-2 lg:grid-cols-4" : r.summary.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2")}>
                {r.summary.map((s, i) => (
                  <motion.div key={s.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                    <Card className="relative h-full overflow-hidden p-4">
                      <span className="absolute inset-x-0 top-0 h-1" style={{ background: `var(--series-${((meta.tone + i - 1) % 8) + 1})` }} />
                      <p className="text-[13px] text-fg-muted">{s.label}</p>
                      <p className="tabular mt-2 text-[28px] font-semibold leading-none tracking-tight"><CountUp to={s.value} fmt={summaryFmt(s)} /></p>
                    </Card>
                  </motion.div>
                ))}
              </div>

              <Card>
                <CardHeader title={chartTitle(type, r.title)} description={meta.ask} actions={<Segmented size="sm" value={tableView ? "t" : "c"} onChange={(v) => setTableView(v === "t")} options={[{ value: "c", label: "Chart", icon: <BarChart3 /> }, { value: "t", label: "Table", icon: <Table2 /> }]} />} />
                <CardBody>
                  {!r.rows.length ? <EmptyState compact title="Nothing to show for these dates" description="Try a longer period, or choose the whole team." /> : tableView ? (
                    <div className="max-h-[420px] overflow-auto rounded-lg border border-border"><table className="w-full text-sm"><thead className="sticky top-0 bg-surface-2 text-left text-xs text-fg-subtle"><tr>{r.columns.map((c) => <th key={c.key} className={cn("px-4 py-2.5 font-medium", c.type !== "text" && c.type !== "date" && "text-right")}>{c.label}</th>)}</tr></thead><tbody>{r.rows.map((row, i) => <tr key={i} className="border-t border-border even:bg-bg-subtle/40">{r.columns.map((c) => <td key={c.key} className={cn("tabular px-4 py-2.5", c.type !== "text" && c.type !== "date" && "text-right")}>{cell(c, row[c.key])}</td>)}</tr>)}</tbody></table></div>
                  ) : isRanking ? <Leaderboard rows={r.rows} cur={cur} full={type === "team_performance"} />
                    : type === "conversion" ? <FunnelBars steps={r.rows.map((x) => ({ label: String(x.status), value: Number(x.count) }))} />
                    : Chart ? <Chart data={r.rows} xKey={r.chart.x} series={series} format={fmt(r.chart.series)} xFormat={fmtDate} height={320} {...(r.chart.type === "bar" ? { stacked: r.chart.stacked, horizontal: r.rows.length <= 8 && r.chart.x !== "period" && r.chart.x !== "stage" } : {})} /> : null}
                </CardBody>
              </Card>

              {r.breakdown && r.breakdown.rows.length > 0 && <Card><CardHeader title={r.breakdown.title} /><CardBody><Breakdown rows={r.breakdown.rows} tone={meta.tone} dark={dark} /></CardBody></Card>}
            </>)}
      </div>
      <SaveDialog open={saveOpen} onOpenChange={setSaveOpen} type={type} params={params as Record<string, string>} />
    </PageContainer>
  );
}

const chartTitle = (type: string, fallback: string) => ({ revenue: "Revenue over time", leads: "New leads over time", pipeline: "Deals by stage", conversion: "Where leads end up", sales: "Agent ranking", team_performance: "Agent ranking", inventory: "Flats by project", forecast: "Expected revenue by month", deal_velocity: "Days to close a deal", customer_acquisition: "New clients over time", activity: "Work done over time" } as Record<string, string>)[type] ?? fallback;

/** A one-sentence read of the numbers, so nobody has to interpret a chart to get the point. */
function makeInsight(type: string, r: Report, cur: string): string | null {
  const rows = r.rows; if (!rows.length) return null;
  const top = (key: string) => rows.reduce((a, b) => (Number(b[key] ?? 0) > Number(a[key] ?? 0) ? b : a), rows[0]);
  const money = (n: unknown) => formatMoneyCompact(Number(n), cur);
  const s = (label: string) => r.summary.find((x) => x.label === label)?.value ?? 0;
  const when = (row: Row, k: string) => fmtDate(String(row[k]));
  switch (type) {
    case "revenue": { const t = top("revenue"); return s("Total revenue") ? `You earned ${money(s("Total revenue"))} from ${s("Deals won")} closed deal${s("Deals won") === 1 ? "" : "s"}. Your best stretch started ${when(t, "period")} with ${money(t.revenue)}.` : "No deals were closed in this period yet."; }
    case "sales": case "team_performance": { const t = top("revenue"); return Number(t.revenue) ? `${t.rep} is leading with ${money(t.revenue)} from ${t.deals_won} deal${t.deals_won === 1 ? "" : "s"}, a ${t.win_rate}% win rate.` : "No deals were closed in this period yet."; }
    case "pipeline": { const t = top("value"); return Number(t.value) ? `${money(s("Open pipeline"))} is open right now. Most of it, ${money(t.value)}, is sitting in “${t.stage}”.` : "There are no open deals in this pipeline."; }
    case "leads": { const b = r.breakdown?.rows[0]; return s("New leads") ? `${s("New leads")} new lead${s("New leads") === 1 ? "" : "s"} came in${b ? `, mostly from ${b.label} (${b.value})` : ""}.` : "No new leads in this period."; }
    case "conversion": { const b = [...(r.breakdown?.rows ?? [])].sort((x, y) => y.value - x.value)[0]; return `${s("Lead → customer")}% of leads became clients${b && b.value ? `. ${b.label} works best at ${b.value}%` : ""}.`; }
    case "forecast": { const t = top("weighted"); return s("Weighted (6 mo)") ? `Expect about ${money(s("Weighted (6 mo)"))} over six months. ${when(t, "period")} looks strongest.` : "Nothing is forecast yet. Add expected close dates to your deals."; }
    case "deal_velocity": return s("Average sales cycle (days)") ? `A deal takes ${s("Average sales cycle (days)")} days to close on average.` : "No deals were closed in this period yet.";
    case "customer_acquisition": return s("New customers") ? `${s("New customers")} new client${s("New customers") === 1 ? "" : "s"} joined, and ${s("New contacts")} new contact${s("New contacts") === 1 ? " was" : "s were"} added.` : "No new clients in this period.";
    case "activity": { const k = [...r.summary].sort((a, b) => b.value - a.value)[0]; return k?.value ? `Your team did ${formatNumber(r.summary.reduce((n, x) => n + x.value, 0))} things. ${k.label} is the most common (${k.value}).` : "No activity logged in this period."; }
    case "inventory": { const t = top("for_sale"); return `${s("Available now")} of ${s("Total flats")} flats are available now${Number(t.for_sale) ? `, most of them in ${t.project}` : ""}. ${s("Sold or rented")}% are sold or rented.`; }
    default: return null;
  }
}

const MEDAL = ["#f5b301", "#9aa4b2", "#c9803f"];
function Leaderboard({ rows, cur, full }: { rows: Row[]; cur: string; full: boolean }) {
  const max = Math.max(...rows.map((r) => Number(r.revenue)), 1);
  return (
    <ol className="space-y-2">
      {rows.map((r, i) => (
        <motion.li key={String(r.rep)} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }} className="rounded-xl border border-border p-3 transition-colors hover:bg-bg-subtle/50">
          <div className="flex items-center gap-3">
            <span className="grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-bold text-white" style={{ background: Number(r.revenue) > 0 ? MEDAL[i] ?? "var(--fg-subtle)" : "var(--fg-subtle)" }}>{i + 1}</span>
            <Avatar name={String(r.rep)} size={32} />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3"><span className="truncate text-sm font-semibold">{String(r.rep)}</span><span className="tabular text-sm font-semibold">{formatMoneyCompact(Number(r.revenue), cur)}</span></div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-bg-subtle"><motion.div className="h-full rounded-full" style={{ background: "var(--series-1)" }} initial={{ width: 0 }} animate={{ width: `${Math.max((Number(r.revenue) / max) * 100, Number(r.revenue) ? 3 : 0)}%` }} transition={{ duration: 0.7, delay: i * 0.05, ease: "easeOut" }} /></div>
            </div>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1.5 pl-[72px] text-xs">
            <Chip tone={3}>{String(r.deals_won)} won</Chip><Chip tone={8}>{String(r.deals_lost)} lost</Chip><Chip tone={1}>{String(r.win_rate)}% win rate</Chip><Chip tone={4}>{String(r.open_deals)} open</Chip>
            {full && <><Chip tone={2}>{String(r.new_leads)} new leads</Chip><Chip tone={5}>{String(r.activities)} activities</Chip><Chip tone={6}>{String(r.tasks_completed)} to-dos done</Chip></>}
          </div>
        </motion.li>
      ))}
    </ol>
  );
}
const Chip = ({ tone, children }: { tone: number; children: React.ReactNode }) => <span className="rounded-full px-2 py-0.5 font-medium text-fg-muted" style={{ background: tint(tone, 14) }}>{children}</span>;

function Breakdown({ rows, tone, dark }: { rows: { label: string; value: number; avg_score?: number; format?: string }[]; tone: number; dark: boolean }) {
  const max = Math.max(...rows.map((b) => b.value), 1);
  return (
    <ul className="grid gap-x-10 gap-y-3.5 sm:grid-cols-2">
      {rows.map((b, i) => {
        const st = STATUS[b.label.replace(/ /g, "_") as UnitStatus];
        const color = st ? (dark ? st.bgDark : st.bg) : `var(--series-${((tone + i - 1) % 8) + 1})`;
        return (
          <li key={b.label}>
            <div className="mb-1 flex items-baseline justify-between text-sm"><span className="capitalize text-fg-muted">{b.label}</span><span className="tabular font-semibold">{b.format === "percent" ? `${b.value}%` : formatNumber(b.value)}{b.avg_score != null && <span className="ml-2 text-xs font-normal text-fg-subtle">score {b.avg_score}</span>}</span></div>
            <div className="h-2 overflow-hidden rounded-full bg-bg-subtle"><motion.div className="h-full rounded-full" style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${Math.max((b.value / max) * 100, b.value ? 3 : 0)}%` }} transition={{ duration: 0.7, delay: i * 0.04, ease: "easeOut" }} /></div>
          </li>
        );
      })}
    </ul>
  );
}

function SaveDialog({ open, onOpenChange, type, params }: { open: boolean; onOpenChange: (o: boolean) => void; type: string; params: Record<string, string> }) {
  const qc = useQueryClient(); const toast = useToast();
  const [name, setName] = React.useState(""); const [schedule, setSchedule] = React.useState(""); const [rec, setRec] = React.useState(""); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  React.useEffect(() => { if (open) { setName(`${META[type]?.label ?? type.replace(/_/g, " ")} report`); setSchedule(""); setRec(""); setErr(null); } }, [open, type]);
  const go = async () => {
    setBusy(true); setErr(null);
    try { await api.post("/api/v1/saved-reports", { name, report_type: type, params: Object.fromEntries(Object.entries(params).filter(([, v]) => v)), schedule: schedule || null, recipients: rec.split(/[,\s]+/).filter(Boolean) }); qc.invalidateQueries({ queryKey: ["saved-reports"] }); toast.success(schedule ? `Saved & scheduled ${schedule}` : "Report saved"); onOpenChange(false); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent size="sm" title="Save report" description="Keep this view handy, or have it emailed on a schedule.">
      <div className="space-y-4"><Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Email me this report"><NativeSelect value={schedule} onChange={(e) => setSchedule(e.target.value)}><option value="">Don't schedule</option><option value="daily">Every day</option><option value="weekly">Every week</option><option value="monthly">Every month</option></NativeSelect></Field>
        {schedule && <Field label="Recipients" hint="Comma separated. Leave blank to send to yourself."><Input value={rec} onChange={(e) => setRec(e.target.value)} placeholder="you@company.com, boss@company.com" /></Field>}{err && <p role="alert" className="text-sm text-danger">{err}</p>}</div>
      <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={go} loading={busy} disabled={!name.trim()}>Save</Button></DialogFooter></DialogContent></Dialog>
  );
}
