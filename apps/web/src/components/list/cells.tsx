"use client";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, ColorChip, DropdownContent, DropdownItem, DropdownMenu, DropdownTrigger, cn, formatDate, timeAgo } from "@crm/ui";
import { ChevronDown } from "lucide-react";
import { useMe, useMembers, usePipelines } from "@/lib/queries";
import { label } from "@/lib/constants";

export function NameCell({ name, sub, avatar, href, square }: { name: string; sub?: React.ReactNode; avatar?: string | null; href: string; square?: boolean }) {
  return (
    <div className="flex min-w-[180px] items-center gap-3">
      <Avatar name={name} src={avatar} size={34} square={square} />
      <div className="min-w-0"><Link href={href} className="block truncate font-medium hover:text-primary">{name}</Link>{sub && <div className="truncate text-xs text-fg-muted">{sub}</div>}</div>
    </div>
  );
}

export function ScorePill({ score }: { score: number }) {
  const tone = score >= 70 ? "var(--success)" : score >= 40 ? "var(--warning)" : "var(--fg-subtle)";
  return (
    <span className="inline-flex items-center gap-2" title={`Lead score ${score}/100`}>
      <span className="relative flex size-7 items-center justify-center"><svg viewBox="0 0 36 36" className="absolute inset-0 -rotate-90"><circle cx="18" cy="18" r="15" fill="none" stroke="var(--border)" strokeWidth="3.5" /><circle cx="18" cy="18" r="15" fill="none" stroke={tone} strokeWidth="3.5" strokeLinecap="round" strokeDasharray={`${(score / 100) * 94.2} 94.2`} /></svg><span className="tabular text-[10px] font-semibold">{score}</span></span>
    </span>
  );
}

export function InlineOwner({ value, owner, onChange, disabled }: { value: string | null; owner?: { name: string; avatar_url?: string | null } | null; onChange: (id: string | null) => void; disabled?: boolean }) {
  const { data } = useMembers();
  const trigger = (
    <button disabled={disabled} className={cn("-mx-2 flex items-center gap-2 rounded-md px-2 py-1 text-left text-[13px] transition-colors", !disabled && "hover:bg-bg-subtle")} aria-label="Change owner">
      {owner ? <><Avatar name={owner.name} src={owner.avatar_url} size={22} /><span className="max-w-[110px] truncate">{owner.name}</span></> : <span className="text-fg-subtle">Unassigned</span>}
      {!disabled && <ChevronDown className="size-3 text-fg-subtle opacity-0 group-hover:opacity-100" />}
    </button>
  );
  if (disabled) return trigger;
  return (
    <DropdownMenu><DropdownTrigger asChild>{trigger}</DropdownTrigger>
      <DropdownContent align="start" className="max-h-72 overflow-y-auto">{(data ?? []).filter((m) => m.status === "active").map((m) => <DropdownItem key={m.user_id} icon={<Avatar name={m.name} size={18} />} onSelect={() => m.user_id !== value && onChange(m.user_id)}>{m.name}</DropdownItem>)}<DropdownItem onSelect={() => onChange(null)}><span className="text-fg-muted">Unassigned</span></DropdownItem></DropdownContent>
    </DropdownMenu>
  );
}

export function LeadStatus({ value, onChange, disabled }: { value: string; onChange?: (s: string) => void; disabled?: boolean }) {
  const { data: me } = useMe();
  const statuses = me?.workspace?.lead_statuses ?? [];
  const cur = statuses.find((s) => s.key === value);
  const chip = <ColorChip color={cur?.color}>{cur?.label ?? label(value)}</ColorChip>;
  if (disabled || value === "converted" || !onChange) return chip;
  return (
    <DropdownMenu><DropdownTrigger asChild><button className="rounded-full focus-visible:outline-offset-2" aria-label="Change status">{chip}</button></DropdownTrigger>
      <DropdownContent align="start">{statuses.filter((s) => s.key !== "converted").map((s) => <DropdownItem key={s.key} onSelect={() => s.key !== value && onChange(s.key)}><ColorChip color={s.color}>{s.label}</ColorChip></DropdownItem>)}</DropdownContent>
    </DropdownMenu>
  );
}

export function StageSelect({ deal, onChange, disabled }: { deal: { stage: { id: string; name: string; color: string | null }; pipeline_id: string }; onChange?: (stageId: string) => void; disabled?: boolean }) {
  const { data } = usePipelines();
  const stages = data?.find((p) => p.id === deal.pipeline_id)?.stages ?? [];
  const chip = <ColorChip color={deal.stage.color}>{deal.stage.name}</ColorChip>;
  if (disabled || !onChange) return chip;
  return (
    <DropdownMenu><DropdownTrigger asChild><button className="rounded-full" aria-label="Change stage">{chip}</button></DropdownTrigger>
      <DropdownContent align="start">{stages.map((s) => <DropdownItem key={s.id} onSelect={() => s.id !== deal.stage.id && onChange(s.id)}><ColorChip color={s.color}>{s.name}</ColorChip></DropdownItem>)}</DropdownContent>
    </DropdownMenu>
  );
}

export const TagList = ({ tags }: { tags: string[] }) => <div className="flex flex-wrap gap-1">{tags.slice(0, 2).map((t) => <Badge key={t} tone="outline">{t}</Badge>)}{tags.length > 2 && <Badge tone="outline">+{tags.length - 2}</Badge>}</div>;

export function DueCell({ iso, done }: { iso: string | null; done?: boolean }) {
  if (!iso) return <span className="text-fg-subtle">—</span>;
  const d = new Date(iso); const overdue = !done && d.getTime() < Date.now();
  return <span className={cn("text-[13px]", overdue ? "font-medium text-danger" : "text-fg-muted")}>{formatDate(iso, d.getHours() ? "datetime" : "short")}</span>;
}
export const Ago = ({ iso }: { iso: string | null }) => <span className="text-[13px] text-fg-muted" title={iso ? formatDate(iso, "datetime") : undefined}>{iso ? timeAgo(iso) : "—"}</span>;
export const Muted = ({ children }: { children?: React.ReactNode }) => <span className="text-[13px] text-fg-muted">{children || "—"}</span>;
