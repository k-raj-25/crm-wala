import { useQuery } from "@tanstack/react-query";
import { Eye, Flame, Snowflake, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";

export type DemandLevel = "hot" | "warm" | "cool" | "cold";
export type UnitDemand = { level: DemandLevel; score: number; holds: number; visits: number; compared: number; interested: number; matched: number };
export type Evidence = { flats: number; left: number; taken: number; on_hold: number; holds: number; visits: number; compared: number; interested: number; matched: number; booked_recently: number; window_days: number };
export type Suggestion = {
  id: string; rule: "raise_hot" | "cut_cold"; pct: number; headline: string; segment_key: string; segment_label: string; tower_id: string; evidence: Evidence;
  price: { min: number | null; max: number | null }; units: { id: string; number: string; floor: number; status: string; price: number }[];
};
export type Pace = { holds: number; booked: number };
export type PriceChange = {
  id: string; status: "applied" | "dismissed" | "undone"; rule: string; pct: number; headline: string | null; segment_label: string; created_at: string; undone_at: string | null;
  decided_by_name: string | null; undone_by_name: string | null; evidence: Evidence; units: { id: string; number: string; before: number; after: number }[];
  tracking: { days: number; before: Pace; after: Pace; verdict: "too_early" | "no_interest" | "faster" | "slower" | "same" } | null;
};

/** Heat-map colours for the tower's demand view. Each level also has its own icon, so it never depends on colour alone. */
export const DEMAND: Record<DemandLevel, { label: string; hint: string; bg: string; bgDark: string; ink: string; inkDark: string; icon: LucideIcon }> = {
  hot: { label: "Hot", hint: "Lots of holds, visits or enquiries", bg: "#e11d48", bgDark: "#e11d48", ink: "#ffffff", inkDark: "#ffffff", icon: Flame },
  warm: { label: "Warm", hint: "Some holds, visits or enquiries", bg: "#f97316", bgDark: "#ea580c", ink: "#ffffff", inkDark: "#ffffff", icon: TrendingUp },
  cool: { label: "Cool", hint: "A little interest", bg: "#7dd3fc", bgDark: "#0369a1", ink: "#0c4a6e", inkDark: "#e0f2fe", icon: Eye },
  cold: { label: "No interest", hint: "No holds, visits, comparisons or enquiries", bg: "#cbd5e1", bgDark: "#334155", ink: "#334155", inkDark: "#cbd5e1", icon: Snowflake },
};
export const DEMAND_ORDER: DemandLevel[] = ["hot", "warm", "cool", "cold"];
export const TAKEN_TILE = { bg: "#eef1f5", bgDark: "#1c2230", ink: "#94a3b8", inkDark: "#5b6578" };

export const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
export const demandLine = (d: Pick<UnitDemand, "holds" | "visits" | "compared" | "interested" | "matched">) =>
  [d.holds && plural(d.holds, "hold"), d.visits && plural(d.visits, "visit"), d.compared && `compared ${d.compared}×`, d.interested && plural(d.interested, "enquiry", "enquiries"),
    d.matched && `${plural(d.matched, "buyer")} fit`].filter(Boolean).join(" · ") || "No interest yet";

export const useDemand = (projectId: string | undefined, towerId: string | undefined, enabled: boolean) => {
  const { can } = useAccess();
  return useQuery({
    queryKey: ["pricing", "demand", projectId, towerId], enabled: enabled && !!projectId && !!towerId && can("pricing.read"), staleTime: 60_000,
    queryFn: () => api.get<{ window_days: number; units: Record<string, UnitDemand> }>(`/api/v1/pricing/projects/${projectId}/demand`, { tower_id: towerId! }),
  });
};
