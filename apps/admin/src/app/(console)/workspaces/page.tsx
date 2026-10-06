"use client";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Card, EmptyState, ErrorState, Input, NativeSelect, SkeletonRows, Table, TBody, TD, TH, THead, TR, formatDate, useDebounce } from "@crm/ui";
import { PageHeader, Pager, StatusBadge, inr } from "@/components/bits";
import { A, api } from "@/lib/api";
import type { Meta } from "@/lib/types";

type Row = { id: string; name: string; owner: { id: string; name: string; email: string } | null; users: number; plan: string; mrr: number; created_at: string; status: string; trial_ends_at: string | null; last_activity: string | null; contacts: number; leads: number; deals: number; is_demo: boolean };

export default function Page() {
  const [q, setQ] = useState(""); const [plan, setPlan] = useState(""); const [status, setStatus] = useState(""); const [sort, setSort] = useState("created_at"); const [page, setPage] = useState(1);
  const dq = useDebounce(q, 300);
  const params = { q: dq, plan, status, sort, page, per_page: 25 };
  const ws = useQuery({ queryKey: ["workspaces", params], queryFn: () => api.page<Row>(`${A}/workspaces`, params), placeholderData: (p) => p });
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => api.get<{ plans: { key: string; name: string }[] }>(`${A}/plans`), staleTime: 300_000 });
  const reset = (fn: () => void) => { fn(); setPage(1); };
  return (
    <>
      <PageHeader title="Workspaces" description="Every customer account. Open one to manage its plan, limits and access." />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-border p-3">
          <div className="min-w-[220px] flex-1"><Input icon={<Search />} placeholder="Search workspace, slug or owner…" value={q} onChange={(e) => reset(() => setQ(e.target.value))} aria-label="Search workspaces" /></div>
          <NativeSelect className="w-40" value={plan} onChange={(e) => reset(() => setPlan(e.target.value))} aria-label="Plan"><option value="">All plans</option>{plans.data?.plans.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</NativeSelect>
          <NativeSelect className="w-40" value={status} onChange={(e) => reset(() => setStatus(e.target.value))} aria-label="Status"><option value="">All statuses</option>{[["trial", "In trial"], ["trial_expired", "Trial expired"], ["active", "Active"], ["past_due", "Past due"], ["canceled", "Canceled"], ["suspended", "Suspended"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect>
          <NativeSelect className="w-44" value={sort} onChange={(e) => reset(() => setSort(e.target.value))} aria-label="Sort"><option value="created_at">Newest first</option><option value="last_activity">Last activity</option><option value="name">Name</option></NativeSelect>
        </div>
        {ws.isError ? <ErrorState compact kind="unavailable" onRetry={() => ws.refetch()} /> : ws.isLoading ? <div className="p-4"><SkeletonRows rows={8} /></div> : !ws.data?.data.length ? <EmptyState compact title="No workspaces match" description="Adjust the filters or search." /> : (
          <div className="overflow-x-auto"><Table>
            <THead><TR><TH>Workspace</TH><TH>Owner</TH><TH>Plan</TH><TH>Status</TH><TH className="text-right">Users</TH><TH className="text-right">Contacts</TH><TH className="text-right">Deals</TH><TH className="text-right">MRR</TH><TH>Last active</TH></TR></THead>
            <TBody>{ws.data.data.map((w) => (
              <TR key={w.id} className="hover:bg-surface-hover">
                <TD><Link href={`/workspaces/${w.id}`} className="font-medium text-fg hover:text-primary">{w.name}</Link>{w.is_demo && <Badge className="ml-2" tone="outline">demo</Badge>}<p className="text-xs text-fg-subtle">Created {formatDate(w.created_at)}</p></TD>
                <TD className="text-fg-muted">{w.owner ? <><span className="block text-fg">{w.owner.name}</span><span className="text-xs">{w.owner.email}</span></> : "—"}</TD>
                <TD className="capitalize">{w.plan.replace(/_/g, " ")}</TD>
                <TD><StatusBadge status={w.status} />{w.status === "trial" && w.trial_ends_at && <p className="mt-0.5 text-xs text-fg-subtle">ends {formatDate(w.trial_ends_at)}</p>}</TD>
                <TD className="tabular text-right">{w.users}</TD><TD className="tabular text-right">{w.contacts}</TD><TD className="tabular text-right">{w.deals}</TD>
                <TD className="tabular text-right">{w.mrr ? inr(w.mrr) : "—"}</TD>
                <TD className="text-fg-muted">{w.last_activity ? formatDate(w.last_activity) : "—"}</TD>
              </TR>))}</TBody></Table></div>
        )}
        <Pager meta={ws.data?.meta as Meta | undefined} onPage={setPage} />
      </Card>
    </>
  );
}
