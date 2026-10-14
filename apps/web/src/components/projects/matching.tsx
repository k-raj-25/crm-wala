"use client";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Sparkles } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Button, Card, CardBody, CardHeader, Segmented, Skeleton, useTheme } from "@crm/ui";
import { type AiProposal, useAiFeature } from "@/lib/ai";
import { api } from "@/lib/api";
import { WaMessage } from "../ai/lead-ai-bits";
import { ProposalCard } from "../ai/proposal-card";
import { useAccess } from "@/lib/queries";
import { STATUS, priceLine } from "@/lib/realestate";
import type { Unit } from "@/lib/realestate";

/** On a lead: the flats that fit what they asked for. One tap opens the flat on its building. */
export function MatchingFlats({ leadId, hasRequirement, firstName, phone }: { leadId: string; hasRequirement: boolean; firstName?: string; phone?: string | null }) {
  const { can } = useAccess();
  const { resolved } = useTheme();
  const aiOn = useAiFeature("matching"); const [mode, setMode] = React.useState<"all" | "ai">("all");
  const q = useQuery({ queryKey: ["lead-matches", leadId, hasRequirement], enabled: can("units.read"), queryFn: () => api.get<Unit[]>(`/api/v1/leads/${leadId}/matches`) });
  if (!can("units.read")) return null;
  return (
    <Card>
      <CardHeader title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Flats that fit</span>} description={mode === "ai" ? `The assistant's best 3 for ${firstName || "this lead"}, with reasons` : "Based on their budget, size and what they're looking to do"} className="!pt-4"
        actions={aiOn && hasRequirement ? <Segmented size="sm" value={mode} onChange={setMode} options={[{ value: "all", label: "All" }, { value: "ai", label: "Best 3", icon: <Sparkles /> }]} /> : undefined} />
      <CardBody className="pt-2">
        {mode === "ai" && aiOn ? <SmartMatches leadId={leadId} firstName={firstName} phone={phone} /> : q.isLoading ? <Skeleton className="h-24" /> : !q.data?.length ? (
          <p className="py-3 text-[13px] text-fg-muted">{hasRequirement ? "Nothing in your inventory fits right now. Try widening the budget." : "Add what they're looking for (size and budget) and matching flats will show up here."}</p>
        ) : (
          <ul className="space-y-2">
            {q.data.slice(0, 5).map((u) => {
              const m = STATUS[u.status];
              return (
                <li key={u.id}>
                  <Link href={`/app/projects/${u.project_id}?tower=${u.tower_id}&unit=${u.id}`} className="flex items-center gap-3 rounded-lg border border-border p-2.5 transition-colors hover:border-primary/40 hover:bg-primary-soft/40">
                    <span className="grid size-9 shrink-0 place-items-center rounded-md text-[13px] font-semibold" style={{ background: resolved === "dark" ? m.bgDark : m.bg, color: resolved === "dark" ? m.inkDark : m.ink }}>{u.number}</span>
                    <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium">{[u.bhk, u.tower_name, u.project_name].filter(Boolean).join(" · ")}</span><span className="block truncate text-xs text-fg-muted">{m.label} · {priceLine(u)}{u.match?.reasons.length ? ` · ${u.match.reasons.join(", ")}` : ""}</span></span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

type SmartPick = { unit: Unit; label: string; reason: string; hold: AiProposal | null };
type Smart = { picks: SmartPick[]; message: string | null; preferences: string[]; phone: string | null; explanation?: string | null };

/** AI picks: the 3 flats most worth showing this lead, why, a one-tap hold and a WhatsApp message to send. */
function SmartMatches({ leadId, firstName, phone }: { leadId: string; firstName?: string; phone?: string | null }) {
  // Loaded by hand (not a query) so approving a hold, which refreshes every query, doesn't swap the cards out from under the person.
  const [d, setD] = React.useState<Smart | null>(null); const [err, setErr] = React.useState<string | null>(null); const [busy, setBusy] = React.useState(true);
  const [msg, setMsg] = React.useState<string | null>(null);
  const load = React.useCallback(async () => { setBusy(true); setErr(null); try { const r = await api.get<Smart>(`/api/v1/ai/leads/${leadId}/smart-matches`); setD(r); setMsg(r.message ?? ""); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } }, [leadId]);
  React.useEffect(() => { load(); }, [load]);
  if (busy && !d) return <div className="space-y-2"><Skeleton className="h-16" /><Skeleton className="h-16" /><Skeleton className="h-16" /></div>;
  if (err || !d) return <div className="py-3 text-[13px]"><p className="text-danger">{err ?? "Couldn't load the picks."}</p><Button size="xs" variant="ghost" className="mt-1" onClick={load} loading={busy}>Try again</Button></div>;
  return (
    <div className="space-y-3">
      {d.preferences?.length > 0 && <div className="flex flex-wrap gap-1.5">{d.preferences.map((p) => <span key={p} className="rounded-full border border-border bg-surface-2 px-2.5 py-0.5 text-xs text-fg-muted">{p}</span>)}</div>}
      {!d.picks.length ? <p className="py-2 text-[13px] text-fg-muted">{d.explanation || `Nothing in your inventory fits ${firstName || "this lead"} right now.`}</p> : (
        <ol className="space-y-2.5">{d.picks.map((p, i) => (
          <li key={`${p.unit.id}-${p.hold?.id ?? ""}`} className="rounded-lg border border-border p-2.5">
            <div className="flex items-start gap-2.5">
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary-soft text-xs font-semibold text-primary">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <Link href={`/app/projects/${p.unit.project_id}?tower=${p.unit.tower_id}&unit=${p.unit.id}`} className="inline-flex items-center gap-1 text-[13px] font-medium hover:text-primary">{p.label}<ExternalLink className="size-3 shrink-0" /></Link>
                <p className="mt-0.5 text-xs text-fg-muted">{p.reason}</p>
              </div>
            </div>
            {p.hold && <div className="mt-2"><ProposalCard p={p.hold} compact /></div>}
          </li>))}</ol>
      )}
      {d.picks.length > 0 && !!d.message && msg !== null && <WaMessage value={msg} onChange={setMsg} phone={d.phone ?? phone} label={`Message for ${firstName || "them"}`} rows={5} />}
      <Button size="xs" variant="ghost" onClick={load} loading={busy}>Refresh picks</Button>
    </div>
  );
}
