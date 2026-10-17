"use client";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ScrollText, Search } from "lucide-react";
import * as React from "react";
import { Button, Card, EmptyState, Input, Segmented, SkeletonRows, useDebounce } from "@crm/ui";
import { type BuyerPromise, type PromiseStatus, PromiseRow, usePromiseSummary } from "@/components/promises/promises";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";

type Filter = PromiseStatus | "all";
const EMPTY: Record<Filter, [string, string]> = {
  pending: ["Nothing waiting for approval", "When a rep records a promise to a buyer, it shows up here for a manager to approve or reject."],
  approved: ["No approved promises yet", "Approved promises print on the buyer's booking form."],
  rejected: ["No rejected promises", ""], cancelled: ["No cancelled promises", ""],
  all: ["No promises yet", "Open a lead, client or deal and record what was promised under Promises."],
};

export default function PromisesPage() {
  const summary = usePromiseSummary(); const counts = summary.data?.counts;
  const [f, setF] = React.useState<Filter>("pending"); const [term, setTerm] = React.useState(""); const q = useDebounce(term, 250);
  const list = useInfiniteQuery({
    queryKey: ["promises", "page", f, q], initialPageParam: 1,
    queryFn: ({ pageParam }) => api.page<BuyerPromise>("/api/v1/promises", { page: pageParam, per_page: 30, status: f === "all" ? undefined : f, q: q || undefined, sort: f === "pending" ? "created_at" : "-created_at" }),
    getNextPageParam: (l) => (l.meta.page < l.meta.pages ? l.meta.page + 1 : undefined),
  });
  const items = list.data?.pages.flatMap((p) => p.data) ?? [];
  const n = (k: PromiseStatus) => (counts?.[k] ? ` (${counts[k]})` : "");
  return (
    <PageContainer>
      <PageHeader title="Promises to buyers" description={summary.data?.can_approve ? "Everything your team promised buyers. Approve or reject each one; only approved promises print on the booking form." : "Everything promised to buyers, and whether a manager approved it. Only approved promises print on the booking form."}
        tabs={<div className="flex flex-wrap items-center justify-between gap-3">
          <div className="max-w-full overflow-x-auto"><Segmented size="sm" className="[&_button]:whitespace-nowrap" value={f} onChange={setF} options={[{ value: "pending", label: `Waiting${n("pending")}` }, { value: "approved", label: `Approved${n("approved")}` }, { value: "rejected", label: "Rejected" }, { value: "cancelled", label: "Cancelled" }, { value: "all", label: "All" }]} /></div>
          <Input icon={<Search />} value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search promises" aria-label="Search promises" className="w-full sm:w-64" />
        </div>} />
      <Card className="overflow-hidden">
        {list.isLoading ? <div className="p-6"><SkeletonRows /></div> : !items.length ? <EmptyState icon={<ScrollText />} title={q ? "No promises match" : EMPTY[f][0]} description={q ? "Try another word." : EMPTY[f][1]} /> : (
          <ul className="divide-y divide-border">{items.map((p) => <PromiseRow key={p.id} p={p} showBuyer canApprove={!!summary.data?.can_approve} />)}</ul>)}
      </Card>
      {list.hasNextPage && <div className="mt-4 flex justify-center"><Button variant="secondary" onClick={() => list.fetchNextPage()} loading={list.isFetchingNextPage}>Load more</Button></div>}
    </PageContainer>
  );
}
