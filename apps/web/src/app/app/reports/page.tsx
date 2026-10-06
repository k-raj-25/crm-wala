"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Bookmark, CalendarClock, Download, FileText, Lock, Table2, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { AreaTrend, BarsChart, Button, Card, CardBody, CardHeader, ChartTable, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Field, Input, LineTrend, NativeSelect, Segmented, Skeleton, cn, formatMoney, formatMoneyCompact, formatNumber, formatPercent, useToast } from "@crm/ui";
import { MemberSelect } from "@/components/forms/fields";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess, usePipelines } from "@/lib/queries";

type Col = { key: string; label: string; type: "text" | "date" | "number" | "currency" | "percent" };
type Report = { title: string; type: string; columns: Col[]; rows: Record<string, unknown>[]; range: { from: string; to: string }; chart: { type: "area" | "bar" | "line"; x: string; stacked?: boolean; series: { key: string; label: string }[] }; summary: { label: string; value: number; format: "currency" | "number" | "percent" }[]; breakdown?: { title: string; rows: { label: string; value: number; avg_score?: number; format?: string }[] } };
type Saved = { id: string; name: string; report_type: string; params: Record<string, string>; schedule: string | null; recipients: string[] };
const TYPES = [["revenue", "Revenue"], ["sales", "Sales"], ["leads", "Leads"], ["conversion", "Conversion"], ["pipeline", "Pipeline"], ["team_performance", "Team performance"], ["deal_velocity", "Deal velocity"], ["activity", "Activity"], ["forecast", "Forecast"], ["customer_acquisition", "Customer acquisition"]] as const;
const ADVANCED = new Set(["team_performance", "deal_velocity", "forecast", "customer_acquisition", "activity", "conversion"]);
const fmtDate = (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(v).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : v;

export default function ReportsPage() {
  const { can, has } = useAccess(); const toast = useToast(); const qc = useQueryClient(); const pipelines = usePipelines();
  const [type, setType] = React.useState("revenue"); const [days, setDays] = React.useState("30"); const [from, setFrom] = React.useState(""); const [to, setTo] = React.useState("");
  const [owner, setOwner] = React.useState<string | null>(null); const [pipeline, setPipeline] = React.useState(""); const [tableView, setTableView] = React.useState(false); const [saveOpen, setSaveOpen] = React.useState(false);
  const locked = ADVANCED.has(type) && !has("advanced_reports");
  const params = { ...(days === "custom" ? { from, to } : { days }), owner_id: owner, pipeline_id: pipeline || undefined };
  const q = useQuery({ queryKey: ["report", type, params], enabled: !locked && (days !== "custom" || (!!from && !!to)), queryFn: () => api.get<Report>(`/api/v1/reports/${type}`, params) });
  const saved = useQuery({ queryKey: ["saved-reports"], queryFn: () => api.get<Saved[]>("/api/v1/saved-reports") });
  const del = useMutation({ mutationFn: (id: string) => api.delete(`/api/v1/saved-reports/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["saved-reports"] }) });
  const r = q.data; const cur = "INR";
  const kind = (k: string) => r?.columns.find((c) => c.key === k)?.type;
  const fmt = (series: { key: string }[]) => { const t = kind(series[0]?.key); return t === "currency" ? (v: number) => formatMoneyCompact(v, cur) : t === "percent" ? (v: number) => `${v}%` : (v: number) => formatNumber(v); };
  const cell = (c: Col, v: unknown) => v == null ? "—" : c.type === "currency" ? formatMoney(v as number, cur) : c.type === "percent" ? formatPercent(v as number) : c.type === "number" ? formatNumber(v as number) : c.type === "date" ? fmtDate(String(v)) : String(v);
  const download = async (ext: "csv" | "pdf") => { const res = await api.raw("GET", `/api/v1/reports/${type}/export.${ext}${api.qs(params)}`); if (!res.ok) { toast.error("Export failed", "Please try again."); return; } const u = URL.createObjectURL(await res.blob()); const a = document.createElement("a"); a.href = u; a.download = `${type}-report.${ext}`; a.click(); URL.revokeObjectURL(u); };
  const summaryFmt = (s: Report["summary"][number]) => s.format === "currency" ? formatMoneyCompact(s.value, cur) : s.format === "percent" ? formatPercent(s.value) : formatNumber(s.value);
  const Chart = r && (r.chart.type === "area" ? AreaTrend : r.chart.type === "line" ? LineTrend : BarsChart);
  return (
    <PageContainer wide>
      <PageHeader title="Reports" description="Revenue, pipeline and team performance — filter, export and schedule."
        actions={<>{can("data.export") && <><Button variant="secondary" onClick={() => download("csv")} disabled={!r}><Download /> CSV</Button><Button variant="secondary" onClick={() => download("pdf")} disabled={!r}><FileText /> PDF</Button></>}{can("reports.manage") && <Button onClick={() => setSaveOpen(true)} disabled={!r}><Bookmark /> Save / schedule</Button>}</>} />
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav className="hide-scrollbar -mx-4 flex gap-1 overflow-x-auto px-4 lg:mx-0 lg:flex-col lg:px-0" aria-label="Report types">
          {TYPES.map(([k, l]) => <button key={k} onClick={() => setType(k)} aria-current={type === k} className={cn("flex shrink-0 items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-[13.5px] font-medium transition-colors", type === k ? "bg-primary-soft text-primary" : "text-fg-muted hover:bg-surface-hover hover:text-fg")}>{l}{ADVANCED.has(k) && !has("advanced_reports") && <Lock className="size-3.5 opacity-60" />}</button>)}
          {(saved.data?.length ?? 0) > 0 && <div className="mt-5 hidden lg:block"><p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-fg-subtle">Saved</p>{saved.data!.map((s) => <div key={s.id} className="group flex items-center"><button onClick={() => { setType(s.report_type); const p = s.params; setDays(p.days ?? "30"); setOwner(p.owner_id ?? null); }} className="flex-1 truncate rounded-lg px-3 py-1.5 text-left text-[13px] text-fg-muted hover:bg-surface-hover hover:text-fg">{s.name}{s.schedule && <CalendarClock className="ml-1.5 inline size-3" />}</button><button aria-label={`Delete ${s.name}`} onClick={() => del.mutate(s.id)} className="rounded p-1 text-fg-subtle opacity-0 hover:text-danger group-hover:opacity-100"><Trash2 className="size-3.5" /></button></div>)}</div>}
        </nav>
        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Segmented size="sm" value={days} onChange={setDays} options={[{ value: "7", label: "7d" }, { value: "30", label: "30d" }, { value: "90", label: "90d" }, { value: "365", label: "12m" }, { value: "custom", label: "Custom" }]} />
            {days === "custom" && <><Input type="date" className="h-8 w-40" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" /><span className="text-fg-subtle">→</span><Input type="date" className="h-8 w-40" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" /></>}
            <div className="w-44"><MemberSelect value={owner} onChange={setOwner} noneLabel="All team members" size="sm" /></div>
            {type === "pipeline" && (pipelines.data?.length ?? 0) > 1 && <NativeSelect className="h-8 w-44 text-[13px]" value={pipeline} onChange={(e) => setPipeline(e.target.value)} aria-label="Pipeline"><option value="">Default pipeline</option>{pipelines.data!.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</NativeSelect>}
          </div>
          {locked ? <ErrorState kind="permission" title="Advanced reports are on Growth and above" description="Upgrade to unlock team performance, forecasts, velocity and more." action={<Button asChild><Link href="/app/billing">Compare plans</Link></Button>} />
            : q.isError ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} />
            : q.isLoading || !r ? <div className="space-y-4"><div className="grid gap-3 sm:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}</div><Skeleton className="h-80" /></div>
            : (
              <>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{r.summary.map((s) => <Card key={s.label} className="p-4"><p className="text-[13px] text-fg-muted">{s.label}</p><p className="tabular mt-1.5 text-2xl font-semibold tracking-tight">{summaryFmt(s)}</p></Card>)}</div>
                <Card>
                  <CardHeader title={r.title} description={`${fmtDate(r.range.from.slice(0, 10))} → ${fmtDate(r.range.to.slice(0, 10))}`} actions={<Segmented size="sm" value={tableView ? "t" : "c"} onChange={(v) => setTableView(v === "t")} options={[{ value: "c", label: "Chart", icon: <BarChart3 /> }, { value: "t", label: "Table", icon: <Table2 /> }]} />} />
                  <CardBody>
                    {!r.rows.length ? <EmptyState compact title="No data for this range" description="Try a wider date range or different filters." /> : tableView ? (
                      <div className="max-h-[420px] overflow-auto rounded-lg border border-border"><table className="w-full text-sm"><thead className="sticky top-0 bg-surface-2 text-left text-xs text-fg-subtle"><tr>{r.columns.map((c) => <th key={c.key} className={cn("px-4 py-2.5 font-medium", c.type !== "text" && c.type !== "date" && "text-right")}>{c.label}</th>)}</tr></thead><tbody>{r.rows.map((row, i) => <tr key={i} className="border-t border-border">{r.columns.map((c) => <td key={c.key} className={cn("tabular px-4 py-2.5", c.type !== "text" && c.type !== "date" && "text-right")}>{cell(c, row[c.key])}</td>)}</tr>)}</tbody></table></div>
                    ) : Chart ? <Chart data={r.rows} xKey={r.chart.x} series={r.chart.series} format={fmt(r.chart.series)} xFormat={fmtDate} height={320} {...(r.chart.type === "bar" ? { stacked: r.chart.stacked, horizontal: r.rows.length <= 8 && r.chart.x !== "period" && r.chart.x !== "stage" } : {})} /> : null}
                  </CardBody>
                </Card>
                {r.breakdown && <Card><CardHeader title={r.breakdown.title} /><CardBody><ul className="grid gap-x-8 gap-y-2 sm:grid-cols-2">{r.breakdown.rows.map((b) => <li key={b.label} className="flex items-center justify-between border-b border-border py-2 text-sm last:border-0"><span className="capitalize text-fg-muted">{b.label}</span><span className="tabular font-medium">{b.format === "percent" ? `${b.value}%` : formatNumber(b.value)}{b.avg_score != null && <span className="ml-2 text-xs text-fg-subtle">avg score {b.avg_score}</span>}</span></li>)}</ul></CardBody></Card>}
              </>)}
        </div>
      </div>
      <SaveDialog open={saveOpen} onOpenChange={setSaveOpen} type={type} params={params as Record<string, string>} />
    </PageContainer>
  );
}

function SaveDialog({ open, onOpenChange, type, params }: { open: boolean; onOpenChange: (o: boolean) => void; type: string; params: Record<string, string> }) {
  const qc = useQueryClient(); const toast = useToast();
  const [name, setName] = React.useState(""); const [schedule, setSchedule] = React.useState(""); const [rec, setRec] = React.useState(""); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  React.useEffect(() => { if (open) { setName(`${type.replace(/_/g, " ")} report`.replace(/^\w/, (c) => c.toUpperCase())); setSchedule(""); setRec(""); setErr(null); } }, [open, type]);
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
export { ChartTable };
