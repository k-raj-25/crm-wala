"use client";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, Building2 } from "lucide-react";
import Link from "next/link";
import { Card, CardBody, CardHeader, EmptyState, Skeleton, useTheme } from "@crm/ui";
import { StatusBar } from "@/components/projects/tower-art";
import { api } from "@/lib/api";
import { STATUS, STATUS_ORDER } from "@/lib/realestate";
import type { CountMap, Project } from "@/lib/realestate";

/** Home: the whole portfolio in one glance — how many flats are free, held, sold — and which project needs attention. */
export function InventorySnapshot() {
  const { resolved } = useTheme();
  const q = useQuery({ queryKey: ["projects", "snapshot"], queryFn: () => api.page<Project>("/api/v1/projects", { per_page: 50 }), refetchInterval: 120_000 });
  const projects = q.data?.data ?? [];
  const counts: CountMap = {};
  projects.forEach((p) => STATUS_ORDER.forEach((s) => { counts[s] = (counts[s] ?? 0) + (p.summary.counts[s] ?? 0); }));
  const total = projects.reduce((n, p) => n + p.summary.total, 0);
  return (
    <Card>
      <CardHeader title="Your inventory" description={total ? `${total} flats across ${projects.length} project${projects.length === 1 ? "" : "s"}` : "Every flat you sell or rent, at a glance"} actions={<Link href="/app/projects" className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline">Open projects <ArrowRight className="size-3.5" /></Link>} />
      <CardBody className="pt-3">
        {q.isLoading ? <Skeleton className="h-28" /> : !projects.length ? <EmptyState compact icon={<Building2 />} title="No projects yet" description="Add a project and its towers to see every flat here." /> : (
          <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
            <div>
              <StatusBar counts={counts} height={12} />
              <ul className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2.5 sm:grid-cols-4">
                {STATUS_ORDER.filter((s) => counts[s]).map((s) => (
                  <li key={s} className="flex items-center gap-2 text-sm"><span className="size-2.5 rounded-full" style={{ background: resolved === "dark" ? STATUS[s].bgDark : STATUS[s].bg }} /><span className="tabular font-semibold">{counts[s]}</span><span className="text-fg-muted">{STATUS[s].label}</span></li>
                ))}
              </ul>
            </div>
            <ul className="space-y-2.5">
              {projects.slice(0, 4).map((p, i) => (
                <li key={p.id}>
                  <Link href={`/app/projects/${p.id}`} className="group block rounded-lg px-1 py-0.5">
                    <div className="mb-1 flex items-baseline justify-between gap-2 text-[13px]"><span className="truncate font-medium group-hover:text-primary">{p.name}</span><span className="shrink-0 text-xs text-fg-muted"><b className="tabular text-success">{p.summary.available}</b> free of {p.summary.total}</span></div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-bg-subtle"><motion.div className="h-full rounded-full bg-success" initial={{ width: 0 }} animate={{ width: `${p.summary.total ? (p.summary.available / p.summary.total) * 100 : 0}%` }} transition={{ delay: i * 0.08, duration: 0.7 }} /></div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
