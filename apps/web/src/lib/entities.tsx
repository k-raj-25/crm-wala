import { Mail, Phone } from "lucide-react";
import Link from "next/link";
import { Badge, formatMoney, formatMoneyCompact } from "@crm/ui";
import { Ago, DueCell, InlineOwner, LeadStatus, Muted, NameCell, ScorePill, StageSelect, TagList } from "@/components/list/cells";
import type { EntityConfig } from "@/components/list/types";
import { SOURCES, label } from "./constants";

const owner = { key: "owner", label: "Owner", render: (r: any, c: any) => <InlineOwner value={r.owner_id} owner={r.owner} disabled={!c.canEdit} onChange={(id) => c.update(r.id, { owner_id: id })} /> }; // eslint-disable-line @typescript-eslint/no-explicit-any
const created = { key: "created_at", label: "Created", sort: "created_at", render: (r: any) => <Ago iso={r.created_at} />, defaultVisible: false }; // eslint-disable-line @typescript-eslint/no-explicit-any

export const LEADS: EntityConfig = {
  key: "leads", title: "Leads", singular: "lead", entityType: "lead", endpoint: "/api/v1/leads", perm: "leads.read", createKind: "lead", importAs: "leads", defaultSort: "-created_at", bulk: ["assign", "tags", "status", "delete"],
  searchPlaceholder: "Search leads by name, email or company…", href: (r) => `/app/leads/${r.id}`,
  empty: { title: "No leads yet", description: "Capture your first lead and start tracking who could become a customer." },
  columns: [
    { key: "name", label: "Name", sort: "name", render: (r) => <NameCell name={r.name} sub={r.email ?? r.job_title} href={`/app/leads/${r.id}`} /> },
    { key: "company", label: "Company", sort: "company", render: (r) => <div className="min-w-[120px]"><div className="truncate text-[13px]">{r.company_name || "—"}</div>{r.job_title && <div className="truncate text-xs text-fg-subtle">{r.job_title}</div>}</div> },
    { key: "status", label: "Status", sort: "status", render: (r, c) => <LeadStatus value={r.status} disabled={!c.canEdit} onChange={(s) => c.update(r.id, { status: s })} /> },
    { key: "score", label: "Score", sort: "score", render: (r) => <ScorePill score={r.score} /> },
    { key: "source", label: "Source", sort: "source", render: (r) => <Muted>{label(r.source)}</Muted> },
    owner,
    { key: "tags", label: "Tags", render: (r) => <TagList tags={r.tags} />, defaultVisible: false },
    { key: "next_follow_up_at", label: "Next follow-up", sort: "next_follow_up_at", render: (r) => <DueCell iso={r.next_follow_up_at} done={["converted", "lost", "unqualified"].includes(r.status)} /> },
    { key: "last_contacted_at", label: "Last contacted", sort: "last_contacted_at", render: (r) => <Ago iso={r.last_contacted_at} /> },
    { key: "phone", label: "Phone", render: (r) => <Muted>{r.phone}</Muted>, defaultVisible: false },
    { key: "location", label: "Location", render: (r) => <Muted>{r.location}</Muted>, defaultVisible: false },
    created,
  ],
  filters: [
    { kind: "multi", param: "status", label: "Status", from: "statuses" }, { kind: "multi", param: "owner_id", label: "Owner", from: "members" },
    { kind: "multi", param: "source", label: "Source", options: SOURCES.map((s) => ({ value: s, label: label(s) })) }, { kind: "multi", param: "tags", label: "Tags", from: "tags" },
    { kind: "range", param: "score", label: "Lead score" }, { kind: "select", param: "follow_up", label: "Follow-up", options: [{ value: "overdue", label: "Overdue" }, { value: "today", label: "Due today" }, { value: "upcoming", label: "Upcoming" }, { value: "none", label: "None scheduled" }] },
    { kind: "date", param: "created_at", label: "Created" },
  ],
  defaultViews: [
    { id: "all", name: "All leads", params: {} }, { id: "mine", name: "My leads", params: { owner_id: "me" } }, { id: "hot", name: "Hot leads", params: { score_min: "70" } },
    { id: "followup", name: "Overdue follow-ups", params: { follow_up: "overdue" } }, { id: "stale", name: "Not contacted in 7 days", params: { stale_days: "7" } }, { id: "new", name: "New this week", params: { created_at_from: "date:7" } },
  ],
  mobile: (r) => ({ title: r.name, subtitle: [r.company_name, r.job_title].filter(Boolean).join(" · ") || r.email, meta: <ScorePill score={r.score} /> }),
};

export const CONTACTS: EntityConfig = {
  key: "contacts", title: "Contacts", singular: "contact", entityType: "contact", endpoint: "/api/v1/contacts", perm: "contacts.read", createKind: "contact", importAs: "contacts", defaultSort: "-created_at", bulk: ["assign", "tags", "delete"],
  searchPlaceholder: "Search contacts by name or email…", href: (r) => `/app/contacts/${r.id}`,
  empty: { title: "No contacts yet", description: "Add the people you work with, or import them from a spreadsheet." },
  columns: [
    { key: "name", label: "Name", sort: "name", render: (r) => <NameCell name={r.name} sub={r.job_title} avatar={r.avatar_url} href={`/app/contacts/${r.id}`} /> },
    { key: "company", label: "Company", render: (r) => r.company ? <Link href={`/app/companies/${r.company.id}`} className="text-[13px] hover:text-primary">{r.company.name}</Link> : <Muted /> },
    { key: "email", label: "Email", sort: "email", render: (r) => r.email ? <a href={`mailto:${r.email}`} className="inline-flex items-center gap-1.5 text-[13px] text-fg-muted hover:text-primary"><Mail className="size-3.5" />{r.email}</a> : <Muted /> },
    { key: "phone", label: "Phone", render: (r) => r.phone ? <a href={`tel:${r.phone}`} className="inline-flex items-center gap-1.5 text-[13px] text-fg-muted hover:text-primary"><Phone className="size-3.5" />{r.phone}</a> : <Muted /> },
    owner, { key: "tags", label: "Tags", render: (r) => <TagList tags={r.tags} /> },
    { key: "last_activity_at", label: "Last activity", sort: "last_activity_at", render: (r) => <Ago iso={r.last_activity_at} /> }, created,
  ],
  filters: [{ kind: "multi", param: "owner_id", label: "Owner", from: "members" }, { kind: "multi", param: "tags", label: "Tags", from: "tags" }, { kind: "date", param: "created_at", label: "Created" }, { kind: "date", param: "last_contacted_at", label: "Last contacted" }],
  defaultViews: [{ id: "all", name: "All contacts", params: {} }, { id: "mine", name: "My contacts", params: { owner_id: "me" } }, { id: "new", name: "Added this month", params: { created_at_from: "date:30" } }],
  mobile: (r) => ({ title: r.name, subtitle: [r.job_title, r.company?.name].filter(Boolean).join(" · ") || r.email }),
};

export const COMPANIES: EntityConfig = {
  key: "companies", title: "Companies", singular: "company", entityType: "company", endpoint: "/api/v1/companies", perm: "companies.read", createKind: "company", importAs: "companies", defaultSort: "name", bulk: ["assign", "tags", "delete"],
  searchPlaceholder: "Search companies…", href: (r) => `/app/companies/${r.id}`,
  empty: { title: "No companies yet", description: "Group contacts and deals under the companies you sell to." },
  columns: [
    { key: "name", label: "Company", sort: "name", render: (r) => <NameCell name={r.name} sub={r.website?.replace(/^https?:\/\//, "")} href={`/app/companies/${r.id}`} square /> },
    { key: "industry", label: "Industry", sort: "industry", render: (r) => <Muted>{r.industry}</Muted> }, { key: "size", label: "Size", sort: "size", render: (r) => <Muted>{r.size}</Muted> },
    { key: "location", label: "Location", render: (r) => <Muted>{r.location}</Muted> },
    { key: "contacts", label: "Contacts", render: (r) => <span className="tabular text-[13px]">{r.contacts_count}</span> },
    { key: "deals", label: "Open deals", render: (r) => r.open_deals_count ? <span className="text-[13px]"><span className="tabular font-medium">{formatMoneyCompact(r.open_deals_value)}</span> <span className="text-fg-subtle">· {r.open_deals_count}</span></span> : <Muted /> },
    owner, { key: "tags", label: "Tags", render: (r) => <TagList tags={r.tags} />, defaultVisible: false }, { key: "last_activity_at", label: "Last activity", sort: "last_activity_at", render: (r) => <Ago iso={r.last_activity_at} /> },
  ],
  filters: [{ kind: "multi", param: "owner_id", label: "Owner", from: "members" }, { kind: "multi", param: "tags", label: "Tags", from: "tags" }, { kind: "date", param: "created_at", label: "Created" }],
  defaultViews: [{ id: "all", name: "All companies", params: {} }, { id: "mine", name: "My companies", params: { owner_id: "me" } }],
  mobile: (r) => ({ title: r.name, subtitle: [r.industry, r.location].filter(Boolean).join(" · "), meta: r.open_deals_count ? <Badge tone="primary">{formatMoneyCompact(r.open_deals_value)}</Badge> : null }),
};

const PRIO: Record<string, "neutral" | "info" | "warning" | "danger"> = { low: "neutral", medium: "info", high: "warning", urgent: "danger" };
export const DEALS: EntityConfig = {
  key: "deals", title: "Deals", singular: "deal", entityType: "deal", endpoint: "/api/v1/deals", perm: "deals.read", createKind: "deal", importAs: "deals", defaultSort: "-created_at", bulk: ["assign", "tags", "delete"],
  searchPlaceholder: "Search deals…", href: (r) => `/app/deals/${r.id}`,
  empty: { title: "No deals yet", description: "Create your first deal and start tracking your sales pipeline." },
  columns: [
    { key: "name", label: "Deal", sort: "name", render: (r) => <NameCell name={r.name} sub={r.company?.name} href={`/app/deals/${r.id}`} square /> },
    { key: "value", label: "Value", sort: "value", align: "right", render: (r) => <span className="tabular text-[13px] font-semibold">{formatMoney(r.value, r.currency)}</span> },
    { key: "stage", label: "Stage", render: (r, c) => <StageSelect deal={r as never} disabled={!c.canEdit || r.status !== "open"} onChange={(s) => c.update(r.id, { stage_id: s })} /> },
    { key: "probability", label: "Prob.", sort: "probability", render: (r) => <span className="tabular text-[13px] text-fg-muted">{r.probability}%</span> },
    { key: "expected_close_date", label: "Expected close", sort: "expected_close_date", render: (r) => <DueCell iso={r.expected_close_date ? r.expected_close_date + "T00:00:00" : null} done={r.status !== "open"} /> },
    { key: "contact", label: "Contact", render: (r) => r.contact ? <Link href={`/app/contacts/${r.contact.id}`} className="text-[13px] hover:text-primary">{r.contact.name}</Link> : <Muted />, defaultVisible: false },
    owner, { key: "priority", label: "Priority", render: (r) => <Badge tone={PRIO[r.priority]}>{label(r.priority)}</Badge> },
    { key: "tags", label: "Tags", render: (r) => <TagList tags={r.tags} />, defaultVisible: false }, created,
  ],
  filters: [
    { kind: "select", param: "status", label: "Status", options: [{ value: "open", label: "Open" }, { value: "won", label: "Won" }, { value: "lost", label: "Lost" }] }, { kind: "multi", param: "stage_id", label: "Stage", from: "stages" },
    { kind: "multi", param: "owner_id", label: "Owner", from: "members" }, { kind: "multi", param: "priority", label: "Priority", options: ["low", "medium", "high", "urgent"].map((p) => ({ value: p, label: label(p) })) },
    { kind: "multi", param: "tags", label: "Tags", from: "tags" }, { kind: "range", param: "value", label: "Deal value" }, { kind: "date", param: "expected_close_date", label: "Expected close" },
  ],
  defaultViews: [
    { id: "all", name: "All deals", params: {} }, { id: "open", name: "Open", params: { status: "open" } }, { id: "mine", name: "My deals", params: { owner_id: "me", status: "open" } },
    { id: "closing", name: "Closing this month", params: { closing: "this_month" } }, { id: "stalled", name: "Stalled 14+ days", params: { stale_days: "14" } }, { id: "won", name: "Won", params: { status: "won" } }, { id: "lost", name: "Lost", params: { status: "lost" } },
  ],
  mobile: (r) => ({ title: r.name, subtitle: `${r.company?.name ?? "—"} · ${r.stage.name}`, meta: <span className="tabular text-sm font-semibold">{formatMoneyCompact(r.value, r.currency)}</span> }),
};
