"use client";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Download, Search } from "lucide-react";
import { Fragment, useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorState, Input, NativeSelect, SkeletonRows, Table, TBody, TD, TH, THead, TR, formatDate, useDebounce } from "@crm/ui";
import { PageHeader, Pager } from "@/components/bits";
import { A, api } from "@/lib/api";
import type { Meta } from "@/lib/types";

type Log = { id: string; created_at: string; actor_type: string; actor_label: string | null; action: string; entity_type: string | null; entity_id: string | null; workspace_name: string | null; summary: string | null; before: unknown; after: unknown; ip: string | null };
const TONE = { admin: "warning", system: "neutral", user: "primary" } as const;

export default function Page() {
  const [q, setQ] = useState(""); const [actor, setActor] = useState(""); const [action, setAction] = useState(""); const [from, setFrom] = useState(""); const [to, setTo] = useState(""); const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const dq = useDebounce(q, 300); const da = useDebounce(action, 300);
  const params = { q: dq, actor_type: actor, action: da, from, to, page, per_page: 50 };
  const logs = useQuery({ queryKey: ["audit", params], queryFn: () => api.page<Log>(`${A}/audit-logs`, params), placeholderData: (p) => p });
  const reset = (fn: () => void) => { fn(); setPage(1); };
  const csv = `${A}/audit-logs${api.qs({ ...params, page: undefined, per_page: undefined, format: "csv" })}`;
  return (
    <>
      <PageHeader title="Audit logs" description="Append-only record of admin and customer actions." actions={<Button variant="secondary" asChild><a href={csv} download><Download /> Export CSV</a></Button>} />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-border p-3">
          <div className="min-w-[240px] flex-1"><Input icon={<Search />} placeholder="Search summary, actor or action…" value={q} onChange={(e) => reset(() => setQ(e.target.value))} aria-label="Search audit logs" /></div>
          <NativeSelect className="w-36" value={actor} onChange={(e) => reset(() => setActor(e.target.value))} aria-label="Actor type"><option value="">All actors</option><option value="admin">Admin</option><option value="user">Customer</option><option value="system">System</option></NativeSelect>
          <Input className="w-48 min-w-[150px]" placeholder="Action, e.g. admin.plan" value={action} onChange={(e) => reset(() => setAction(e.target.value))} aria-label="Action" />
          <Input type="date" className="w-40" value={from} onChange={(e) => reset(() => setFrom(e.target.value))} aria-label="From date" />
          <Input type="date" className="w-40" value={to} onChange={(e) => reset(() => setTo(e.target.value))} aria-label="To date" />
        </div>
        {logs.isError ? <ErrorState compact kind="unavailable" onRetry={() => logs.refetch()} /> : logs.isLoading ? <div className="p-4"><SkeletonRows rows={10} /></div> : !logs.data?.data.length ? <EmptyState compact title="No log entries" description="Nothing matches those filters." /> : (
          <div className="overflow-x-auto"><Table>
            <THead><TR><TH className="w-8" /><TH>Time</TH><TH>Actor</TH><TH>Action</TH><TH>Summary</TH><TH>Workspace</TH></TR></THead>
            <TBody>{logs.data.data.map((l) => {
              const has = !!(l.before || l.after); const isOpen = open === l.id;
              return (
                <Fragment key={l.id}>
                  <TR className={has ? "cursor-pointer hover:bg-surface-hover" : ""} onClick={() => has && setOpen(isOpen ? null : l.id)}>
                    <TD>{has && <ChevronRight className={`size-4 text-fg-subtle transition-transform ${isOpen ? "rotate-90" : ""}`} />}</TD>
                    <TD className="whitespace-nowrap text-fg-muted">{formatDate(l.created_at, "datetime")}</TD>
                    <TD><Badge tone={TONE[l.actor_type as keyof typeof TONE] ?? "neutral"}>{l.actor_type}</Badge> <span className="text-sm">{l.actor_label}</span></TD>
                    <TD className="font-mono text-xs">{l.action}</TD>
                    <TD className="max-w-[420px] text-fg-muted"><span className="line-clamp-2">{l.summary}</span></TD>
                    <TD className="text-fg-muted">{l.workspace_name ?? "—"}</TD>
                  </TR>
                  {isOpen && <tr className="bg-bg-subtle"><td colSpan={6} className="px-6 py-3"><div className="grid gap-3 md:grid-cols-2">
                    {([["Before", l.before], ["After", l.after]] as const).map(([t, v]) => <div key={t}><p className="mb-1 text-xs font-medium uppercase text-fg-subtle">{t}</p><pre className="max-h-56 overflow-auto rounded-lg border border-border bg-surface p-3 text-xs">{v ? JSON.stringify(v, null, 2) : "—"}</pre></div>)}
                    <p className="text-xs text-fg-subtle md:col-span-2">IP {l.ip ?? "—"} · entity {l.entity_type ?? "—"} {l.entity_id ?? ""}</p></div></td></tr>}
                </Fragment>);
            })}</TBody></Table></div>)}
        <Pager meta={logs.data?.meta as Meta | undefined} onPage={setPage} />
      </Card>
    </>
  );
}
