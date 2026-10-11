"use client";
import { LayoutGrid, List } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Segmented } from "@crm/ui";
import { EntityList } from "@/components/list/entity-list";
import { PipelineBoard } from "@/components/pipeline/board";
import { DEALS } from "@/lib/entities";

/** One place for deals: a drag-and-drop board, or the same deals as a filterable table. */
function Pipeline() {
  const router = useRouter(); const sp = useSearchParams();
  const view = sp.get("view") === "list" ? "list" : "board";
  const switcher = (
    <Segmented value={view} onChange={(v) => { const q = new URLSearchParams(v === "list" ? sp.toString() : ""); if (v === "list") q.set("view", "list"); else q.delete("view"); router.replace(`/app/pipeline${q.toString() ? "?" + q.toString() : ""}`, { scroll: false }); }}
      options={[{ value: "board", label: "Board", icon: <LayoutGrid /> }, { value: "list", label: "List", icon: <List /> }]} />
  );
  return view === "list" ? <EntityList cfg={DEALS} heading="Pipeline" headerLead={switcher} /> : <PipelineBoard headerLead={switcher} />;
}

export default function Page() { return <Suspense><Pipeline /></Suspense>; }
