"use client";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Plus, X } from "lucide-react";
import * as React from "react";
import { Avatar, Input, Popover, PopoverContent, PopoverTrigger, Select, Spinner, cn, useDebounce } from "@crm/ui";
import { api } from "@/lib/api";
import { useMembers, useTags } from "@/lib/queries";

/** Server-searched single select (companies, contacts, deals, leads). Optionally offers inline creation. */
export function AsyncSelect({ value, onChange, endpoint, labelKey = "name", placeholder = "Search…", initialLabel, onCreate, id, invalid, params, clearable = true }: {
  value: string | null | undefined; onChange: (id: string | null, item?: Record<string, unknown>) => void; endpoint: string; labelKey?: string; placeholder?: string; initialLabel?: string | null;
  onCreate?: (name: string) => Promise<{ id: string; label: string }>; id?: string; invalid?: boolean; params?: Record<string, unknown>; clearable?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const dq = useDebounce(q, 200);
  const [label, setLabel] = React.useState<string | null>(initialLabel ?? null);
  const [creating, setCreating] = React.useState(false);
  React.useEffect(() => { if (initialLabel) setLabel(initialLabel); }, [initialLabel]);
  React.useEffect(() => { if (!value) setLabel(null); }, [value]);
  const res = useQuery({ queryKey: ["async-select", endpoint, dq, params], enabled: open, queryFn: () => api.page<Record<string, unknown>>(endpoint, { q: dq, per_page: 8, ...params }), staleTime: 15_000 });
  const items = res.data?.data ?? [];
  const nameOf = (i: Record<string, unknown>) => String(i[labelKey] ?? i.title ?? i.name ?? "");
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button id={id} type="button" aria-invalid={invalid} className={cn("flex h-9 w-full items-center justify-between gap-2 rounded-md border border-border bg-surface px-3 text-left text-sm shadow-xs transition-[border-color,box-shadow] hover:border-border-strong focus:border-primary focus:outline-none focus:ring-4 focus:ring-[var(--ring)]", invalid && "border-danger")}>
          <span className={cn("truncate", !label && "text-fg-subtle")}>{label ?? placeholder}</span>
          <span className="flex items-center gap-1">{clearable && value && <span role="button" aria-label="Clear" onClick={(e) => { e.stopPropagation(); onChange(null); setLabel(null); }} className="rounded p-0.5 text-fg-subtle hover:bg-surface-hover hover:text-fg"><X className="size-3.5" /></span>}<ChevronsUpDown className="size-4 text-fg-subtle" /></span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] min-w-[260px] p-2" align="start">
        <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type to search…" />
        <ul className="mt-2 max-h-56 overflow-y-auto" role="listbox">
          {res.isFetching && !items.length && <li className="flex justify-center py-4"><Spinner /></li>}
          {items.map((i) => (
            <li key={String(i.id)}><button type="button" role="option" aria-selected={i.id === value} className="flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm hover:bg-surface-hover" onClick={() => { onChange(String(i.id), i); setLabel(nameOf(i)); setOpen(false); setQ(""); }}>
              <span className="truncate">{nameOf(i)}{i.email ? <span className="ml-2 text-xs text-fg-subtle">{String(i.email)}</span> : null}</span>{i.id === value && <Check className="size-4 text-primary" />}</button></li>
          ))}
          {!res.isFetching && !items.length && !onCreate && <li className="px-2.5 py-3 text-center text-sm text-fg-subtle">No results</li>}
          {onCreate && q.trim().length > 1 && !items.some((i) => nameOf(i).toLowerCase() === q.trim().toLowerCase()) && (
            <li><button type="button" disabled={creating} className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm font-medium text-primary hover:bg-primary-soft" onClick={async () => { setCreating(true); try { const c = await onCreate(q.trim()); onChange(c.id); setLabel(c.label); setOpen(false); setQ(""); } finally { setCreating(false); } }}>
              {creating ? <Spinner /> : <Plus className="size-4" />} Create “{q.trim()}”</button></li>
          )}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

export function MemberSelect({ value, onChange, id, allowNone = true, noneLabel = "Unassigned", size }: { value: string | null | undefined; onChange: (v: string | null) => void; id?: string; allowNone?: boolean; noneLabel?: string; size?: "sm" | "md" }) {
  const { data } = useMembers();
  const opts = [...(allowNone ? [{ value: "__none", label: <span className="text-fg-muted">{noneLabel}</span> }] : []), ...(data ?? []).filter((m) => m.status === "active").map((m) => ({ value: m.user_id, label: <span className="flex items-center gap-2"><Avatar name={m.name} size={18} />{m.name}</span> }))];
  return <Select id={id} size={size} value={value ?? (allowNone ? "__none" : undefined)} onValueChange={(v) => onChange(v === "__none" ? null : v)} options={opts} placeholder="Select person" />;
}

export function TagInput({ value, onChange, id, placeholder = "Add tag…" }: { value: string[]; onChange: (v: string[]) => void; id?: string; placeholder?: string }) {
  const [text, setText] = React.useState("");
  const tags = useTags();
  const colors = new Map((tags.data ?? []).map((t) => [t.name, t.color]));
  const add = (raw: string) => { const t = raw.trim().replace(/,$/, "").slice(0, 40); if (t && !value.includes(t)) onChange([...value, t]); setText(""); };
  const suggestions = (tags.data ?? []).filter((t) => !value.includes(t.name) && t.name.toLowerCase().includes(text.toLowerCase())).slice(0, 6);
  return (
    <div>
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1.5 shadow-xs focus-within:border-primary focus-within:ring-4 focus-within:ring-[var(--ring)]">
        {value.map((t) => { const c = colors.get(t) ?? "#6366f1"; return (
          <span key={t} className="inline-flex items-center gap-1 rounded-full py-0.5 pl-2.5 pr-1 text-xs font-medium" style={{ background: `color-mix(in srgb, ${c} 14%, transparent)`, color: `color-mix(in srgb, ${c} 75%, var(--fg))` }}>{t}<button type="button" aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((x) => x !== t))} className="rounded-full p-0.5 hover:bg-black/10"><X className="size-3" /></button></span>); })}
        <input id={id} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(text); } else if (e.key === "Backspace" && !text && value.length) onChange(value.slice(0, -1)); }} onBlur={() => text && add(text)} placeholder={value.length ? "" : placeholder} className="min-w-[80px] flex-1 bg-transparent text-sm outline-none placeholder:text-fg-subtle" />
      </div>
      {text && suggestions.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1.5">{suggestions.map((s) => <button key={s.id} type="button" onClick={() => add(s.name)} className="rounded-full border border-border px-2.5 py-0.5 text-xs text-fg-muted hover:bg-surface-hover">{s.name}</button>)}</div>}
    </div>
  );
}

export const toLocalInput = (iso?: string | null) => { if (!iso) return ""; const d = new Date(iso); const p = (n: number) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };
export const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);
