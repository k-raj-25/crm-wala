"use client";
import { Building2, LayoutGrid } from "lucide-react";
import { useRouter } from "next/navigation";
import { Segmented } from "@crm/ui";
import { useCompare, useSocietyCompare } from "@/lib/compare";

/** Flats | Societies switch at the top of the comparison page, with how many of each are picked. */
export function CompareTabs({ value }: { value: "flats" | "societies" }) {
  const router = useRouter();
  const flats = useCompare().length;
  const societies = useSocietyCompare().length;
  const count = (n: number) => (n ? <span className="ml-0.5 rounded-full bg-primary-soft px-1.5 text-[11px] tabular-nums text-primary">{n}</span> : null);
  return (
    <Segmented value={value} onChange={(v) => router.replace(v === "societies" ? "/app/compare?tab=societies" : "/app/compare")}
      options={[{ value: "flats", label: <>Flats{count(flats)}</>, icon: <LayoutGrid /> }, { value: "societies", label: <>Societies{count(societies)}</>, icon: <Building2 /> }]} />
  );
}
