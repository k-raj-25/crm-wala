"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Building2, Check, Download, Plus, Scale, Share2, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { ApiError, Button, Card, EmptyState, ErrorState, Skeleton, Switch, cn, useTheme, useToast } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { MAX_COMPARE, compare, useCompare } from "@/lib/compare";
import { STATUS } from "@/lib/realestate";
import type { UnitStatus } from "@/lib/realestate";
import { FlatPicker } from "./flat-picker";
import { ShareComparison, comparisonPdf } from "./share-dialog";

export type Comparison = {
  flats: { id: string; number: string; title: string; subtitle: string; project_id: string; tower_id: string; status: UnitStatus }[];
  rows: { key: string; label: string; values: string[]; best: number[]; same: boolean }[];
};

export function ComparePage() {
  const list = useCompare();
  const sp = useSearchParams();
  const toast = useToast();
  const { resolved } = useTheme();
  const [picker, setPicker] = React.useState(false);
  const [share, setShare] = React.useState(false);
  const [diffOnly, setDiffOnly] = React.useState(false);
  const [downloading, setDownloading] = React.useState(false);
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  // "New comparison" from the Create menu lands here with ?pick=1: open the search straight away when nothing is picked yet
  React.useEffect(() => { if (mounted && sp.get("pick") && !list.length) setPicker(true); }, [mounted]); // eslint-disable-line react-hooks/exhaustive-deps

  const ids = list.map((f) => f.id);
  const q = useQuery({ queryKey: ["comparison", ids], enabled: ids.length > 0, placeholderData: keepPreviousData, queryFn: () => api.get<Comparison>("/api/v1/comparisons/preview", { ids }), retry: false });
  // a flat that was deleted since it was picked: drop it instead of failing the whole page
  React.useEffect(() => {
    const e = q.error;
    const gone = e instanceof ApiError && e.status === 404 ? (e.details as unknown as { missing?: string[] } | undefined)?.missing : undefined;
    if (Array.isArray(gone)) {
      const missing = new Set(gone);
      compare.set(list.filter((f) => !missing.has(f.id)));
      toast.toast({ tone: "info", title: "A flat in your list no longer exists, so we removed it" });
    }
  }, [q.error]); // eslint-disable-line react-hooks/exhaustive-deps

  const download = async () => {
    setDownloading(true);
    try {
      const f = await comparisonPdf(ids);
      const url = URL.createObjectURL(f); const a = document.createElement("a"); a.href = url; a.download = f.name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { toast.error((e as Error).message); } finally { setDownloading(false); }
  };

  // keepPreviousData shows the old table while a just-added flat loads; line columns up by id so nothing shifts
  const d = q.data;
  const idx = list.map((f) => d?.flats.findIndex((x) => x.id === f.id) ?? -1);
  const rows = (d?.rows ?? []).map((r) => ({ ...r, cells: idx.map((i) => (i < 0 ? null : { v: r.values[i], best: r.best.includes(i) })) }));
  const visible = diffOnly && list.length > 1 ? rows.filter((r) => new Set(r.cells.map((c) => c?.v)).size > 1) : rows;
  const flatsLabel = list.map((f) => `Flat ${f.number}`).join(", ");

  return (
    <PageContainer wide>
      <PageHeader title="Compare flats" description={list.length ? `${list.length} of ${MAX_COMPARE} flats, side by side. Green marks the best value.` : "Line flats up side by side and send the comparison to your client."}
        actions={mounted && list.length > 0 && <>
          <Button variant="secondary" onClick={() => setPicker(true)} disabled={list.length >= MAX_COMPARE}><Plus /> Add flats</Button>
          <Button variant="secondary" onClick={download} loading={downloading}><Download /> PDF</Button>
          <Button onClick={() => setShare(true)}><Share2 /> Share</Button>
        </>} />

      {!mounted ? <Skeleton className="h-96" />
        : !list.length ? (
          <Card>
            <EmptyState icon={<Scale />} title="Pick flats to compare" description="Search any flat by number or size, or open a tower and tap Compare to pick flats right on the building."
              action={<Button onClick={() => setPicker(true)}><Plus /> Search flats</Button>} secondary={<Button variant="secondary" asChild><Link href="/app/projects"><Building2 /> Pick from a tower</Link></Button>} />
          </Card>
        ) : q.isError && !d ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} />
        : (
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
              <label className="flex items-center gap-2.5 text-sm text-fg-muted"><Switch checked={diffOnly} onCheckedChange={setDiffOnly} aria-label="Only show differences" />Only show differences</label>
              <button type="button" onClick={() => compare.clear()} className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-danger"><Trash2 className="size-4" /> Clear all</button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[calc(88px+var(--n)*132px)] table-fixed border-separate border-spacing-0 text-sm sm:min-w-[calc(140px+var(--n)*170px)] [&_td]:break-words" style={{ ["--n" as string]: list.length }}>
                <thead>
                  <tr>
                    <th scope="col" className="sticky left-0 z-10 w-[88px] border-b sm:w-[140px] border-border bg-surface px-4 py-3 text-left align-bottom text-xs font-medium uppercase tracking-wide text-fg-subtle">Flat</th>
                    {list.map((f) => {
                      const meta = d?.flats.find((x) => x.id === f.id);
                      const s = meta ? STATUS[meta.status] : null;
                      return (
                        <th key={f.id} scope="col" className="border-b border-l border-border px-3 py-3 sm:px-4 text-left align-top font-normal">
                          <motion.div layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <Link href={meta ? `/app/projects/${meta.project_id}?tower=${meta.tower_id}&unit=${meta.id}` : "#"} className="block text-base font-semibold tracking-tight hover:text-primary">Flat {f.number}</Link>
                              <p className="truncate text-xs text-fg-muted">{meta?.subtitle ?? f.where}</p>
                              {s && <span className="mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold" style={{ background: resolved === "dark" ? s.bgDark : s.bg, color: resolved === "dark" ? s.inkDark : s.ink }}><s.icon className="size-3" />{s.label}</span>}
                            </div>
                            <button type="button" onClick={() => compare.remove(f.id)} aria-label={`Remove flat ${f.number}`} className="-mr-1 grid size-7 shrink-0 place-items-center rounded-md text-fg-subtle hover:bg-surface-hover hover:text-fg"><X className="size-4" /></button>
                          </motion.div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {!d ? Array.from({ length: 7 }).map((_, i) => <tr key={i}><td className="sticky left-0 bg-surface px-4 py-3"><Skeleton className="h-4 w-20" /></td>{list.map((f) => <td key={f.id} className="border-l border-border px-4 py-3"><Skeleton className="h-4 w-24" /></td>)}</tr>)
                    : visible.map((r, ri) => (
                      <tr key={r.key} className={cn(ri % 2 === 1 && "[&>td]:bg-surface-2")}>
                        <th scope="row" className="sticky left-0 z-10 border-t border-border bg-surface px-3 py-2.5 sm:px-4 text-left text-[13px] font-normal text-fg-muted">{r.label}</th>
                        {r.cells.map((c, i) => (
                          <td key={list[i].id} className={cn("border-l border-t border-border px-3 py-2.5 sm:px-4 align-top", c?.best && "font-semibold text-success", r.key === "price" && "text-[15px] font-semibold")}>
                            {c ? <span className="inline-flex items-start gap-1">{c.v}{c.best && <Check className="mt-0.5 size-3.5 shrink-0" aria-label="best" />}</span> : <Skeleton className="h-4 w-20" />}</td>
                        ))}
                      </tr>
                    ))}
                  {d && !visible.length && <tr><td colSpan={list.length + 1} className="px-4 py-8 text-center text-sm text-fg-muted">These flats are the same on every detail we have.</td></tr>}
                </tbody>
              </table>
            </div>
            {list.length === 1 && <div className="border-t border-border bg-primary-soft/50 px-4 py-3 text-sm">Add at least one more flat to see them side by side. <button type="button" onClick={() => setPicker(true)} className="font-medium text-primary hover:underline">Add flats</button></div>}
          </Card>
        )}

      <FlatPicker open={picker} onOpenChange={setPicker} />
      <ShareComparison open={share} onOpenChange={setShare} unitIds={ids} flatsLabel={flatsLabel} />
    </PageContainer>
  );
}
