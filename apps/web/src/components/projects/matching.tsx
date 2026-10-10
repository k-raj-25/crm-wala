"use client";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import { Card, CardBody, CardHeader, Skeleton, useTheme } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { STATUS, priceLine } from "@/lib/realestate";
import type { Unit } from "@/lib/realestate";

/** On a lead: the flats that fit what they asked for. One tap opens the flat on its building. */
export function MatchingFlats({ leadId, hasRequirement }: { leadId: string; hasRequirement: boolean }) {
  const { can } = useAccess();
  const { resolved } = useTheme();
  const q = useQuery({ queryKey: ["lead-matches", leadId, hasRequirement], enabled: can("units.read"), queryFn: () => api.get<Unit[]>(`/api/v1/leads/${leadId}/matches`) });
  if (!can("units.read")) return null;
  return (
    <Card>
      <CardHeader title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Flats that fit</span>} description="Based on their budget, size and what they're looking to do" className="!pt-4" />
      <CardBody className="pt-2">
        {q.isLoading ? <Skeleton className="h-24" /> : !q.data?.length ? (
          <p className="py-3 text-[13px] text-fg-muted">{hasRequirement ? "Nothing in your inventory fits right now. Try widening the budget." : "Add what they're looking for (size and budget) and matching flats will show up here."}</p>
        ) : (
          <ul className="space-y-2">
            {q.data.slice(0, 5).map((u) => {
              const m = STATUS[u.status];
              return (
                <li key={u.id}>
                  <Link href={`/app/projects/${u.project_id}?tower=${u.tower_id}&unit=${u.id}`} className="flex items-center gap-3 rounded-lg border border-border p-2.5 transition-colors hover:border-primary/40 hover:bg-primary-soft/40">
                    <span className="grid size-9 shrink-0 place-items-center rounded-md text-[13px] font-semibold" style={{ background: resolved === "dark" ? m.bgDark : m.bg, color: m.ink }}>{u.number}</span>
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
