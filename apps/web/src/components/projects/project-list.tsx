"use client";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Building2, MapPin, Plus, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Skeleton, useDebounce } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { PROJECT_STAGES, STATUS, money, where } from "@/lib/realestate";
import type { Project } from "@/lib/realestate";
import { NewProjectDialog } from "./forms";
import { ProjectSkyline, StatusBar } from "./tower-art";

function ProjectCard({ p, i }: { p: Project; i: number }) {
  const s = p.summary;
  const stage = PROJECT_STAGES.find((x) => x[0] === p.stage)?.[1];
  const hot = (["for_sale", "on_hold", "booked"] as const).filter((k) => (s.counts[k] ?? 0) > 0);
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.05, 0.4), duration: 0.35, ease: [0.16, 1, 0.3, 1] }}>
      <Link href={`/app/projects/${p.id}`} className="group block overflow-hidden rounded-2xl border border-border bg-surface shadow-xs transition-all hover:-translate-y-0.5 hover:border-border-strong hover:shadow-md focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[var(--ring)]">
        <div className="relative"><ProjectSkyline towers={p.towers} counts={s.counts} />
          <div className="absolute left-3 top-3 flex gap-1.5">{stage && <Badge tone={p.stage === "ready" ? "success" : p.stage === "under_construction" ? "warning" : "info"}>{stage}</Badge>}</div></div>
        <div className="space-y-3 p-4">
          <div>
            <h2 className="truncate text-[17px] font-semibold tracking-tight group-hover:text-primary">{p.name}</h2>
            <p className="mt-0.5 flex items-center gap-1 truncate text-[13px] text-fg-muted"><MapPin className="size-3.5 shrink-0" />{where(p) || "No address yet"}{p.developer ? ` · ${p.developer}` : ""}</p>
          </div>
          <StatusBar counts={s.counts} />
          <div className="flex items-end justify-between gap-3">
            <div><div className="text-2xl font-semibold leading-none tabular-nums text-success">{s.available}</div><div className="mt-1 text-xs text-fg-muted">of {s.total} flats available</div></div>
            <div className="text-right"><div className="text-sm font-semibold tabular-nums">{p.starting_price ? `from ${money(p.starting_price)}` : "—"}</div><div className="mt-1 text-xs text-fg-muted">{p.towers.length} tower{p.towers.length === 1 ? "" : "s"}</div></div>
          </div>
          {hot.length > 0 && <div className="flex flex-wrap gap-1.5">{hot.map((k) => <span key={k} className="rounded-full px-2 py-0.5 text-[11px] font-semibold" style={{ background: STATUS[k].bg, color: STATUS[k].ink }}>{s.counts[k]} {STATUS[k].label.toLowerCase()}</span>)}</div>}
        </div>
      </Link>
    </motion.div>
  );
}

export function ProjectList() {
  const { can } = useAccess();
  const [q, setQ] = React.useState(""); const dq = useDebounce(q);
  const [open, setOpen] = React.useState(false);
  const list = useQuery({ queryKey: ["projects", dq], queryFn: () => api.page<Project>("/api/v1/projects", { per_page: 50, q: dq }) });
  const items = list.data?.data ?? [];
  const totals = items.reduce((a, p) => ({ units: a.units + p.summary.total, avail: a.avail + p.summary.available, closed: a.closed + p.summary.closed }), { units: 0, avail: 0, closed: 0 });
  return (
    <PageContainer wide>
      <PageHeader title="Projects" description="Pick a project and see every tower, every floor and every flat — what's free, held, sold or rented — at a glance."
        actions={can("projects.create") ? <Button onClick={() => setOpen(true)}><Plus /> New project</Button> : undefined} />
      {(items.length > 0 || dq) && (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div className="w-full sm:w-80"><Input icon={<Search />} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by project, builder or area" aria-label="Search projects" /></div>
          {items.length > 0 && <p className="text-sm text-fg-muted"><b className="text-fg">{items.length}</b> projects · <b className="text-fg">{totals.units}</b> flats · <b className="text-success">{totals.avail}</b> available · <b className="text-fg">{totals.closed}</b> sold or rented</p>}
        </div>
      )}
      {list.isLoading ? <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-[380px] rounded-2xl" />)}</div>
        : list.isError ? <ErrorState kind="unavailable" onRetry={() => list.refetch()} />
        : !items.length ? <Card><EmptyState icon={<Building2 />} title={dq ? "No projects match" : "Add your first project"} description={dq ? "Try a different name or area." : "Create a project, tell us how many floors and flats it has, and we'll draw the building for you."} action={!dq && can("projects.create") ? <Button onClick={() => setOpen(true)}><Plus /> New project</Button> : undefined} /></Card>
        : <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{items.map((p, i) => <ProjectCard key={p.id} p={p} i={i} />)}</div>}
      <NewProjectDialog open={open} onOpenChange={setOpen} />
    </PageContainer>
  );
}
