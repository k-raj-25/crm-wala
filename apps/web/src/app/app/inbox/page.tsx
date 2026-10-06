"use client";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Eye, Inbox as InboxIcon, Mail, Pencil, Reply, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, Button, Card, EmptyState, ErrorState, Input, Segmented, SkeletonRows, cn, formatDate, timeAgo, useDebounce } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { useUI } from "@/components/shell/ui-context";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import type { EmailMsg } from "@/lib/types";

type F = "all" | "inbound" | "outbound" | "scheduled";
export default function InboxPage() {
  const ui = useUI(); const { can } = useAccess();
  const [f, setF] = React.useState<F>("all"); const [search, setSearch] = React.useState(""); const dq = useDebounce(search); const [sel, setSel] = React.useState<string | null>(null);
  const q = useQuery({ queryKey: ["emails", "inbox", f, dq], queryFn: () => api.page<EmailMsg>("/api/v1/emails", { per_page: 50, q: dq, sort: "-created_at", direction: f === "inbound" || f === "outbound" ? f : undefined, status: f === "scheduled" ? "scheduled" : undefined }) });
  const emails = q.data?.data ?? []; const cur = emails.find((e) => e.id === sel) ?? (typeof window !== "undefined" && window.innerWidth >= 1024 ? emails[0] : undefined);
  const rel = cur?.related[0]; const relHref = rel ? `/app/${rel.type === "company" ? "companies" : rel.type + "s"}/${rel.id}` : null;
  const reply = (e: EmailMsg) => ui.openCompose({ to: e.direction === "inbound" ? e.from_address ?? "" : e.to_addresses.join(", "), subject: e.subject.startsWith("Re:") ? e.subject : `Re: ${e.subject}`, ...Object.fromEntries(e.related.map((r) => [`${r.type}_id`, r.id])) });
  return (
    <PageContainer wide>
      <PageHeader title="Inbox" description="Every email linked to your leads, contacts and deals." actions={can("emails.create") ? <Button onClick={() => ui.openCompose()}><Pencil /> Compose</Button> : undefined} />
      <Card className="overflow-hidden">
        <div className="grid min-h-[560px] lg:grid-cols-[380px_1fr]">
          <div className={cn("border-r border-border", cur && sel && "hidden lg:block")}>
            <div className="space-y-3 border-b border-border p-3"><Input icon={<Search />} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search subject…" aria-label="Search emails" /><Segmented size="sm" value={f} onChange={setF} options={[{ value: "all", label: "All" }, { value: "inbound", label: "Received" }, { value: "outbound", label: "Sent" }, { value: "scheduled", label: "Scheduled" }]} /></div>
            {q.isLoading ? <div className="p-4"><SkeletonRows rows={7} /></div> : q.isError ? <ErrorState compact kind="unavailable" onRetry={() => q.refetch()} /> : !emails.length ? <EmptyState compact icon={<InboxIcon />} title="No emails" description="Send an email from a contact, or log one that happened elsewhere." action={can("emails.create") ? <Button size="sm" onClick={() => ui.openCompose()}>Compose</Button> : undefined} /> : (
              <ul className="max-h-[640px] divide-y divide-border overflow-y-auto">{emails.map((e) => { const who = e.direction === "inbound" ? e.from_address : e.to_addresses[0]; return (
                <li key={e.id}><button onClick={() => setSel(e.id)} className={cn("flex w-full gap-3 px-4 py-3.5 text-left transition-colors hover:bg-surface-hover", cur?.id === e.id && "bg-primary-soft/50")}><Avatar name={who ?? "?"} size={34} /><span className="min-w-0 flex-1"><span className="flex items-baseline justify-between gap-2"><span className="truncate text-sm font-medium">{who}</span><span className="shrink-0 text-xs text-fg-subtle">{timeAgo(e.sent_at ?? e.created_at)}</span></span><span className="block truncate text-[13px]">{e.subject}</span><span className="mt-0.5 flex items-center gap-1.5">{e.direction === "outbound" ? <Badge tone="neutral">Sent</Badge> : <Badge tone="success">Received</Badge>}{e.status === "scheduled" && <Badge tone="warning">Scheduled</Badge>}{e.opens > 0 && <Badge tone="info"><Eye className="size-3" />{e.opens}</Badge>}</span></span></button></li>); })}</ul>)}
          </div>
          <div className={cn("min-w-0", !(cur && sel) && "hidden lg:block")}>
            {cur ? (
              <article className="p-6">
                <button onClick={() => setSel(null)} className="mb-4 flex items-center gap-1.5 text-[13px] text-fg-muted lg:hidden"><ArrowLeft className="size-3.5" /> Back</button>
                <div className="flex items-start justify-between gap-4"><h2 className="text-xl font-semibold tracking-tight">{cur.subject}</h2>{can("emails.create") && <Button variant="secondary" size="sm" onClick={() => reply(cur)}><Reply /> Reply</Button>}</div>
                <div className="mt-4 flex items-center gap-3 text-sm"><Avatar name={cur.from_address ?? "?"} size={36} /><div className="min-w-0"><p className="truncate font-medium">{cur.from_address}</p><p className="truncate text-xs text-fg-muted">to {cur.to_addresses.join(", ")} · {formatDate(cur.sent_at ?? cur.created_at, "datetime")}</p></div></div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">{cur.status === "scheduled" && <Badge tone="warning">Scheduled for {formatDate(cur.scheduled_at, "datetime")}</Badge>}{cur.opens > 0 && <Badge tone="success"><Eye className="size-3" /> Opened {cur.opens}×</Badge>}{cur.status === "failed" && <Badge tone="danger">Delivery failed</Badge>}{rel && relHref && <Link href={relHref} className="rounded-full border border-border px-2.5 py-0.5 font-medium text-primary hover:bg-primary-soft">{rel.label}</Link>}</div>
                <div className="mt-6 whitespace-pre-line rounded-xl bg-bg-subtle p-5 text-sm leading-relaxed">{cur.body}</div>
              </article>
            ) : <EmptyState icon={<Mail />} title="Select an email" description="Pick a conversation to read it here." />}
          </div>
        </div>
      </Card>
    </PageContainer>
  );
}
