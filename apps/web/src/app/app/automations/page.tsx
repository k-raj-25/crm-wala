"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Sparkles, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Skeleton, Switch, timeAgo, useToast } from "@crm/ui";
import { ACTION_ICONS, TEMPLATES, toGraph, uid } from "@/components/automations/meta";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";

type Auto = { id: string; name: string; description: string | null; trigger_type: string; graph: { nodes: { type: string; data: { action_type?: string } }[] }; is_active: boolean; run_count: number; last_run_at: string | null };
export default function AutomationsPage() {
  const router = useRouter(); const qc = useQueryClient(); const toast = useToast(); const { can } = useAccess(); const [del, setDel] = React.useState<Auto | null>(null);
  const q = useQuery({ queryKey: ["automations"], queryFn: () => api.get<Auto[]>("/api/v1/automations") });
  const toggle = useMutation({ mutationFn: (a: Auto) => api.patch(`/api/v1/automations/${a.id}`, { is_active: !a.is_active }), onSuccess: () => qc.invalidateQueries({ queryKey: ["automations"] }), onError: (e) => toast.error("Couldn't update", (e as Error).message) });
  const fromTemplate = async (t: (typeof TEMPLATES)[number]) => { try { const steps = t.steps.map((s) => ({ ...s, id: uid() })); const a = await api.post<{ id: string }>("/api/v1/automations", { name: t.name, description: t.description, trigger_type: t.trigger, graph: toGraph(t.trigger, {}, steps), is_active: false }); router.push(`/app/automations/${a.id}`); } catch (e) { toast.error("Couldn't create", (e as Error).message); } };
  const locked = (q.error as { code?: string } | null)?.code === "feature_unavailable";
  return (
    <PageContainer>
      <PageHeader title="Automations" description="Do the repetitive work automatically — assign, email, create tasks and remind." actions={can("automations.create") && !locked ? <Button asChild><Link href="/app/automations/new"><Plus /> New automation</Link></Button> : undefined} />
      {locked ? <ErrorState kind="permission" title="Automations aren't included in your plan" description="Upgrade to unlock the visual automation builder." action={<Button asChild><Link href="/app/billing">See plans</Link></Button>} />
        : q.isError ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} />
        : q.isLoading ? <div className="space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-24" />)}</div>
        : (
          <div className="space-y-8">
            {q.data!.length === 0 ? <EmptyState icon={<Workflow />} title="No automations yet" description="Start from a template below, or build your own from scratch." action={can("automations.create") ? <Button asChild><Link href="/app/automations/new"><Plus /> Build from scratch</Link></Button> : undefined} /> : (
              <div className="space-y-3">{q.data!.map((a) => { const steps = a.graph.nodes.filter((n) => n.type === "action"); return (
                <Card key={a.id} hover className="flex flex-wrap items-center gap-4 p-5">
                  <Link href={`/app/automations/${a.id}`} className="min-w-0 flex-1"><p className="truncate font-semibold">{a.name}</p><p className="mt-0.5 truncate text-[13px] text-fg-muted">{a.description || `When ${a.trigger_type.replace(".", " ").replace("_", " ")}`}</p>
                    <div className="mt-2.5 flex items-center gap-1.5">{steps.slice(0, 7).map((s, i) => { const I = ACTION_ICONS[s.data.action_type ?? "create_activity"]; return <span key={i} className="flex size-6 items-center justify-center rounded-md bg-bg-subtle text-fg-muted"><I className="size-3.5" /></span>; })}<span className="ml-1 text-xs text-fg-subtle">{steps.length} step{steps.length === 1 ? "" : "s"}</span></div></Link>
                  <div className="flex items-center gap-6 text-sm"><div className="text-right"><p className="tabular font-semibold">{a.run_count}</p><p className="text-xs text-fg-subtle">runs{a.last_run_at ? ` · ${timeAgo(a.last_run_at)}` : ""}</p></div>
                    <Badge tone={a.is_active ? "success" : "neutral"} dot>{a.is_active ? "Active" : "Paused"}</Badge>{can("automations.update") && <Switch checked={a.is_active} onCheckedChange={() => toggle.mutate(a)} aria-label={`${a.is_active ? "Pause" : "Activate"} ${a.name}`} />}
                    {can("automations.delete") && <Button variant="ghost" size="xs" onClick={() => setDel(a)}>Delete</Button>}</div>
                </Card>); })}</div>)}
            {can("automations.create") && <section><h2 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-primary" /> Start from a template</h2>
              <div className="grid gap-3 md:grid-cols-3">{TEMPLATES.map((t) => <button key={t.name} onClick={() => fromTemplate(t)} className="rounded-xl border border-border bg-surface p-5 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"><p className="font-semibold">{t.name}</p><p className="mt-1 text-[13px] text-fg-muted">{t.description}</p><p className="mt-3 text-xs font-medium text-primary">{t.steps.length} steps · Use template →</p></button>)}</div></section>}
          </div>)}
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete “${del?.name}”?`} description="It will stop running immediately. Past run history is kept in the audit log." confirmLabel="Delete" onConfirm={async () => { await api.delete(`/api/v1/automations/${del!.id}`); qc.invalidateQueries({ queryKey: ["automations"] }); toast.success("Automation deleted"); }} />
    </PageContainer>
  );
}
