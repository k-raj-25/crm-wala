"use client";
import * as React from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "../lib/cn";
import { motion } from "framer-motion";

export type Series = { key: string; label: string; color?: string };
const SERIES_VARS = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`);
export const seriesColor = (i: number, s?: Series) => s?.color ?? SERIES_VARS[i % SERIES_VARS.length];

const axisTick = { fontSize: 12, fill: "var(--fg-subtle)" } as const;

type TipProps = { active?: boolean; payload?: { dataKey: string; value: number; color?: string; payload: Record<string, unknown> }[]; label?: string | number };

function makeTooltip(series: Series[], format: (v: number) => string, xFormat?: (v: string) => string) {
  return function ChartTooltip({ active, payload, label }: TipProps) {
    if (!active || !payload?.length) return null;
    return (
      <div className="min-w-[150px] rounded-lg border border-border bg-surface px-3 py-2.5 shadow-lg">
        <p className="mb-1.5 text-xs font-medium text-fg-muted">{xFormat ? xFormat(String(label)) : label}</p>
        <ul className="space-y-1">
          {payload.map((p, i) => {
            const idx = series.findIndex((s) => s.key === p.dataKey);
            const s = series[idx] ?? series[i];
            return (
              <li key={p.dataKey} className="flex items-center justify-between gap-4 text-[13px]">
                <span className="flex items-center gap-2 text-fg-muted"><span className="size-2.5 rounded-sm" style={{ background: seriesColor(Math.max(idx, 0), s) }} />{s?.label ?? p.dataKey}</span>
                <span className="tabular font-semibold text-fg">{format(p.value)}</span>
              </li>
            );
          })}
        </ul>
      </div>
    );
  };
}

export function Legend({ series, className }: { series: Series[]; className?: string }) {
  if (series.length < 2) return null;
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1", className)} aria-label="Legend">
      {series.map((s, i) => <li key={s.key} className="flex items-center gap-1.5 text-xs text-fg-muted"><span className="size-2.5 rounded-sm" style={{ background: seriesColor(i, s) }} />{s.label}</li>)}
    </ul>
  );
}

type Common = { data: Record<string, unknown>[]; xKey: string; series: Series[]; height?: number; format?: (v: number) => string; xFormat?: (v: string) => string; className?: string };

export function AreaTrend({ data, xKey, series, height = 240, format = (v) => v.toLocaleString(), xFormat, className }: Common) {
  const id = React.useId().replace(/:/g, "");
  const Tip = React.useMemo(() => makeTooltip(series, format, xFormat), [series, format, xFormat]);
  return (
    <div className={className}>
      <Legend series={series} className="mb-2" />
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>{series.map((s, i) => (
            <linearGradient key={s.key} id={`${id}-${s.key}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={seriesColor(i, s)} stopOpacity={0.28} /><stop offset="100%" stopColor={seriesColor(i, s)} stopOpacity={0} /></linearGradient>
          ))}</defs>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={xKey} tick={axisTick} tickLine={false} axisLine={false} tickFormatter={xFormat} minTickGap={28} />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} width={52} />
          <Tooltip content={<Tip />} cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }} />
          {series.map((s, i) => (
            <Area key={s.key} type="monotone" dataKey={s.key} stroke={seriesColor(i, s)} strokeWidth={2} fill={`url(#${id}-${s.key})`} dot={false} animationDuration={800}
              activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2, fill: seriesColor(i, s) }} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LineTrend({ data, xKey, series, height = 240, format = (v) => v.toLocaleString(), xFormat, className }: Common) {
  const Tip = React.useMemo(() => makeTooltip(series, format, xFormat), [series, format, xFormat]);
  return (
    <div className={className}>
      <Legend series={series} className="mb-2" />
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={xKey} tick={axisTick} tickLine={false} axisLine={false} tickFormatter={xFormat} minTickGap={28} />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} width={44} />
          <Tooltip content={<Tip />} cursor={{ stroke: "var(--border-strong)" }} />
          {series.map((s, i) => <Line key={s.key} type="monotone" dataKey={s.key} stroke={seriesColor(i, s)} strokeWidth={2} dot={false} animationDuration={800} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2, fill: seriesColor(i, s) }} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BarsChart({ data, xKey, series, height = 240, format = (v) => v.toLocaleString(), xFormat, className, stacked, horizontal, colorByPoint }: Common & { stacked?: boolean; horizontal?: boolean; colorByPoint?: string[] }) {
  const Tip = React.useMemo(() => makeTooltip(series, format, xFormat), [series, format, xFormat]);
  return (
    <div className={className}>
      <Legend series={series} className="mb-2" />
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap="28%">
          <CartesianGrid vertical={horizontal} horizontal={!horizontal} stroke="var(--grid)" />
          {horizontal ? (
            <>
              <XAxis type="number" tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} />
              <YAxis type="category" dataKey={xKey} tick={{ ...axisTick, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={96} />
            </>
          ) : (
            <>
              <XAxis dataKey={xKey} tick={axisTick} tickLine={false} axisLine={false} tickFormatter={xFormat} interval="preserveStartEnd" minTickGap={16} />
              <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} width={52} />
            </>
          )}
          <Tooltip content={<Tip />} cursor={{ fill: "var(--bg-subtle)", opacity: 0.7 }} />
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} stackId={stacked ? "a" : undefined} fill={seriesColor(i, s)} radius={stacked ? [0, 0, 0, 0] : horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={36} animationDuration={700}
              stroke={stacked ? "var(--surface)" : undefined} strokeWidth={stacked ? 2 : 0}>
              {colorByPoint && series.length === 1 && data.map((_, idx) => <Cell key={idx} fill={colorByPoint[idx % colorByPoint.length]} />)}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DonutChart({ data, format = (v) => v.toLocaleString(), height = 200, center }: { data: { name: string; value: number; color?: string }[]; format?: (v: number) => string; height?: number; center?: React.ReactNode }) {
  const total = data.reduce((a, d) => a + d.value, 0);
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="relative" style={{ width: height, height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius="68%" outerRadius="100%" paddingAngle={2} stroke="var(--surface)" strokeWidth={2} animationDuration={800}>
              {data.map((d, i) => <Cell key={d.name} fill={d.color ?? seriesColor(i)} />)}
            </Pie>
            <Tooltip content={({ active, payload }) => active && payload?.[0] ? (
              <div className="rounded-lg border border-border bg-surface px-3 py-2 text-[13px] shadow-lg"><span className="text-fg-muted">{payload[0].name}</span> <span className="ml-2 font-semibold tabular">{format(Number(payload[0].value))}</span></div>
            ) : null} />
          </PieChart>
        </ResponsiveContainer>
        {center && <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">{center}</div>}
      </div>
      <ul className="min-w-[140px] flex-1 space-y-2">
        {data.map((d, i) => (
          <li key={d.name} className="flex items-center justify-between gap-3 text-[13px]">
            <span className="flex items-center gap-2 text-fg-muted"><span className="size-2.5 rounded-sm" style={{ background: d.color ?? seriesColor(i) }} />{d.name}</span>
            <span className="tabular font-medium">{format(d.value)} <span className="text-fg-subtle">· {total ? Math.round((d.value / total) * 100) : 0}%</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sparkline({ data, color = "var(--series-1)", height = 32, width = 96 }: { data: number[]; color?: string; height?: number; width?: number }) {
  if (data.length < 2) return <div style={{ width, height }} />;
  const max = Math.max(...data), min = Math.min(...data), span = max - min || 1;
  const pts = data.map((v, i) => [(i / (data.length - 1)) * width, height - 3 - ((v - min) / span) * (height - 6)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} aria-hidden>
      <motion.path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.8, ease: "easeOut" }} />
    </svg>
  );
}

/** Horizontal funnel using one sequential hue (magnitude, not identity). */
export function FunnelBars({ steps, format = (v) => v.toLocaleString() }: { steps: { label: string; value: number }[]; format?: (v: number) => string }) {
  const max = Math.max(...steps.map((s) => s.value), 1);
  const ramp = ["var(--seq-5)", "var(--seq-4)", "var(--seq-3)", "var(--seq-2)", "var(--seq-1)"];
  return (
    <ul className="space-y-2.5">
      {steps.map((s, i) => {
        const prev = i > 0 ? steps[i - 1].value : null;
        return (
          <li key={s.label} className="group">
            <div className="mb-1 flex items-center justify-between text-[13px]">
              <span className="font-medium text-fg">{s.label}</span>
              <span className="tabular text-fg-muted"><span className="font-semibold text-fg">{format(s.value)}</span>{prev ? <span className="ml-2 text-fg-subtle">{prev ? Math.round((s.value / prev) * 100) : 0}%</span> : null}</span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-bg-subtle">
              <motion.div className="h-full rounded-full" style={{ background: ramp[Math.min(i, ramp.length - 1)] }} initial={{ width: 0 }} animate={{ width: `${Math.max((s.value / max) * 100, s.value ? 2 : 0)}%` }} transition={{ duration: 0.7, delay: i * 0.06, ease: "easeOut" }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Accessible table alternative for any chart. */
export function ChartTable({ data, columns }: { data: Record<string, unknown>[]; columns: { key: string; label: string; format?: (v: unknown) => string }[] }) {
  return (
    <div className="max-h-64 overflow-auto rounded-md border border-border">
      <table className="w-full text-[13px]">
        <thead className="sticky top-0 bg-surface-2 text-left text-xs text-fg-subtle"><tr>{columns.map((c) => <th key={c.key} className="px-3 py-2 font-medium">{c.label}</th>)}</tr></thead>
        <tbody>{data.map((r, i) => <tr key={i} className="border-t border-border">{columns.map((c) => <td key={c.key} className="tabular px-3 py-1.5">{c.format ? c.format(r[c.key]) : String(r[c.key] ?? "")}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
