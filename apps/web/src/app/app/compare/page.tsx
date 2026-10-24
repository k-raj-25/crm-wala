"use client";
import { useSearchParams } from "next/navigation";
import { ComparePage } from "@/components/compare/compare-page";
import { SocietyComparePage } from "@/components/compare/society-compare";

export default function Page() {
  const sp = useSearchParams();
  return sp.get("tab") === "societies" ? <SocietyComparePage openPicker={!!sp.get("pick")} /> : <ComparePage />;
}
