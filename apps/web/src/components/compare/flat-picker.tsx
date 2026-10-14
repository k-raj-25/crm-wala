"use client";
import { useQuery } from "@tanstack/react-query";
import { Check, Search } from "lucide-react";
import * as React from "react";
import { Button, Dialog, DialogContent, DialogFooter, Input, NativeSelect, Spinner, Switch, cn, useDebounce, useTheme, useToast } from "@crm/ui";
import { AsyncSelect } from "@/components/forms/fields";
import { api } from "@/lib/api";
import { MAX_COMPARE, compare, useCompare } from "@/lib/compare";
import { AVAILABLE, BHK_OPTIONS, STATUS, floorLabel, priceLine } from "@/lib/realestate";
import type { Unit } from "@/lib/realestate";

export const flatWhere = (u: Pick<Unit, "tower_name" | "project_name">) => [u.tower_name, u.project_name].filter(Boolean).join(" · ");

/** Search every flat in the workspace and tick the ones to compare. Ticks apply at once, so "Done" just closes. */
export function FlatPicker({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const list = useCompare();
  const toast = useToast();
  const { resolved } = useTheme();
  const [q, setQ] = React.useState("");
  const dq = useDebounce(q, 200);
  const [project, setProject] = React.useState<string | null>(null);
  const [bhk, setBhk] = React.useState("");
  const [onlyFree, setOnlyFree] = React.useState(true);
  const res = useQuery({
    queryKey: ["compare-picker", dq, project, bhk, onlyFree], enabled: open, staleTime: 15_000,
    queryFn: () => api.page<Unit>("/api/v1/units", { q: dq, project_id: project, bhk: bhk || undefined, status: onlyFree ? AVAILABLE : undefined, per_page: 40, sort: "floor,number" }),
  });
  const rows = res.data?.data ?? [];
  const picked = new Set(list.map((f) => f.id));
  const toggle = (u: Unit) => {
    if (compare.toggle({ id: u.id, number: u.number, where: flatWhere(u) }) === "full") toast.error(`You can compare up to ${MAX_COMPARE} flats`, "Remove one to add another.");
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" title="Add flats to compare" description={`Pick up to ${MAX_COMPARE}. Search by flat number or size, or narrow down by project.`}>
        <div className="space-y-3">
          <Input autoFocus icon={<Search />} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Flat number or size, e.g. 801 or 3 BHK" aria-label="Search flats" />
          <div className="grid gap-2 sm:grid-cols-[1fr_140px_auto] sm:items-center">
            <AsyncSelect value={project} onChange={setProject} endpoint="/api/v1/projects" placeholder="All projects" />
            <NativeSelect aria-label="Size" value={bhk} onChange={(e) => setBhk(e.target.value)}><option value="">All sizes</option>{BHK_OPTIONS.map((b) => <option key={b}>{b}</option>)}</NativeSelect>
            <label className="flex items-center gap-2 whitespace-nowrap text-sm text-fg-muted"><Switch checked={onlyFree} onCheckedChange={setOnlyFree} aria-label="Only available flats" />Only available</label>
          </div>
          <ul className="max-h-[46vh] divide-y divide-border overflow-y-auto rounded-xl border border-border" aria-label="Flats">
            {res.isLoading && <li className="flex justify-center py-10"><Spinner /></li>}
            {!res.isLoading && !rows.length && <li className="px-4 py-10 text-center text-sm text-fg-muted">No flats match. Try another search{onlyFree ? ", or include flats that aren't available" : ""}.</li>}
            {rows.map((u) => {
              const on = picked.has(u.id); const s = STATUS[u.status]; const Icon = s.icon;
              return (
                <li key={u.id}>
                  <button type="button" onClick={() => toggle(u)} aria-pressed={on} className={cn("flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface-hover", on && "bg-primary-soft/60")}>
                    <span className={cn("grid size-5 shrink-0 place-items-center rounded-md border", on ? "border-primary bg-primary text-primary-fg" : "border-border-strong")}>{on && <Check className="size-3.5" />}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">Flat {u.number}<span className="ml-2 font-normal text-fg-muted">{flatWhere(u)}</span></span>
                      <span className="block truncate text-xs text-fg-subtle">{[u.bhk, u.area_sqft ? `${Math.round(u.area_sqft).toLocaleString("en-IN")} sq ft` : null, floorLabel(u.floor), u.facing].filter(Boolean).join(" · ")}</span>
                    </span>
                    <span className="hidden shrink-0 text-right sm:block"><span className="block text-sm font-semibold tabular-nums">{priceLine(u)}</span>
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium" style={{ color: resolved === "dark" ? s.bgDark : s.bg === "#dfe5ee" ? "#64748b" : s.bg }}><Icon className="size-3" />{s.label}</span></span>
                  </button>
                </li>
              );
            })}
          </ul>
          {(res.data?.meta.total ?? 0) > rows.length && <p className="text-xs text-fg-subtle">Showing the first {rows.length}. Search or pick a project to find more.</p>}
        </div>
        <DialogFooter className="items-center sm:justify-between">
          <span className="text-sm text-fg-muted">{list.length} of {MAX_COMPARE} picked</span>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
