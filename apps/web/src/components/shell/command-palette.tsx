"use client";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Activity, ArrowRight, Building2, CalendarPlus, CheckSquare, FileUp, Handshake, Mail, Moon, Plus, Search, Settings, StickyNote, Sun, UserRound, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Dialog as D } from "radix-ui";
import { Kbd, Spinner, useDebounce, useTheme } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { useNavItems } from "./sidebar";
import { useUI } from "./ui-context";

type Result = { id: string; title: string; subtitle?: string; url: string };
const GROUPS: [string, string, React.ElementType][] = [["contacts", "Contacts", UserRound], ["leads", "Leads", Users], ["companies", "Companies", Building2], ["deals", "Deals", Handshake], ["tasks", "Tasks", CheckSquare], ["notes", "Notes", StickyNote], ["activities", "Activities", Activity]];

export function CommandPalette() {
  const ui = useUI(); const router = useRouter(); const { can } = useAccess(); const nav = useNavItems(); const { resolved, setPref } = useTheme();
  const [q, setQ] = React.useState("");
  const dq = useDebounce(q, 120);
  React.useEffect(() => { setQ(ui.command ? ui.commandInitial : ""); }, [ui.command, ui.commandInitial]);
  const search = useQuery({ queryKey: ["cmd-search", dq], enabled: ui.command && dq.trim().length > 0, staleTime: 10_000, queryFn: () => api.get<Record<string, Result[]>>("/api/v1/search", { q: dq, limit: 5 }) });
  const close = () => ui.setCommand(false);
  const run = (fn: () => void) => () => { close(); setTimeout(fn, 60); };
  const create = (kind: Parameters<typeof ui.openCreate>[0]) => run(() => ui.openCreate(kind));
  const cmds = [
    { label: "Create lead", icon: Plus, perm: "leads.create", on: create("lead"), kw: "new add" }, { label: "Create contact", icon: Plus, perm: "contacts.create", on: create("contact"), kw: "new add person" },
    { label: "Create deal", icon: Plus, perm: "deals.create", on: create("deal"), kw: "new add opportunity" }, { label: "Create task", icon: CheckSquare, perm: "tasks.create", on: create("task"), kw: "new add todo" },
    { label: "Create company", icon: Building2, perm: "companies.create", on: create("company"), kw: "new add account" },
    { label: "Schedule meeting", icon: CalendarPlus, perm: "meetings.create", on: create("meeting"), kw: "calendar book" }, { label: "Send email", icon: Mail, perm: "emails.create", on: run(() => ui.openCompose()), kw: "compose write" },
    { label: "Import contacts", icon: FileUp, perm: "data.import", on: run(() => router.push("/app/settings/data?import=contacts")), kw: "csv upload" },
    { label: "Open settings", icon: Settings, perm: "", on: run(() => router.push("/app/settings")), kw: "preferences" },
    { label: resolved === "dark" ? "Switch to light mode" : "Switch to dark mode", icon: resolved === "dark" ? Sun : Moon, perm: "", on: run(() => setPref(resolved === "dark" ? "light" : "dark")), kw: "theme" },
  ].filter((c) => !c.perm || can(c.perm));
  const match = (label: string, kw = "") => !q.trim() || (label + " " + kw).toLowerCase().includes(q.trim().toLowerCase());
  const hasResults = GROUPS.some(([k]) => search.data?.[k]?.length);
  return (
    <D.Root open={ui.command} onOpenChange={ui.setCommand}>
      <D.Portal>
        <D.Overlay className="anim-overlay fixed inset-0 z-[110] bg-[var(--overlay)] backdrop-blur-[2px]" />
        <D.Content aria-label="Command palette" className="anim-pop fixed left-1/2 top-[12vh] z-[111] w-[calc(100vw-24px)] max-w-[640px] -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-surface shadow-lg focus:outline-none">
          <D.Title className="sr-only">Command palette</D.Title><D.Description className="sr-only">Search records or run a command</D.Description>
          <Command shouldFilter={false} loop>
            <div className="flex items-center gap-3 border-b border-border px-4">
              <Search className="size-4 text-fg-subtle" />
              <Command.Input autoFocus value={q} onValueChange={setQ} placeholder="Search contacts, deals, tasks… or type a command" className="h-14 flex-1 bg-transparent text-[15px] outline-none placeholder:text-fg-subtle" />
              {search.isFetching ? <Spinner className="text-fg-subtle" /> : <Kbd>esc</Kbd>}
            </div>
            <Command.List className="max-h-[min(60vh,440px)] overflow-y-auto p-2">
              <Command.Empty className="py-10 text-center text-sm text-fg-muted">{search.isFetching ? "Searching…" : q ? `No results for “${q}”` : "Start typing to search"}</Command.Empty>
              {q.trim() && GROUPS.map(([k, label, Icon]) => search.data?.[k]?.length ? (
                <Command.Group key={k} heading={label} className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-fg-subtle">
                  {search.data[k].map((r) => (
                    <Command.Item key={r.id} value={`${k}-${r.id}`} onSelect={run(() => router.push(r.url))} className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm aria-selected:bg-primary-soft">
                      <Icon className="size-4 shrink-0 text-fg-subtle" /><span className="min-w-0 flex-1"><span className="block truncate font-medium">{r.title}</span>{r.subtitle && <span className="block truncate text-xs text-fg-muted">{r.subtitle}</span>}</span><ArrowRight className="size-3.5 text-fg-subtle opacity-0 aria-selected:opacity-100" />
                    </Command.Item>))}
                </Command.Group>) : null)}
              {cmds.some((c) => match(c.label, c.kw)) && (
                <Command.Group heading="Commands" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-fg-subtle">
                  {cmds.filter((c) => match(c.label, c.kw)).map((c) => <Command.Item key={c.label} value={c.label} onSelect={c.on} className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm aria-selected:bg-primary-soft"><c.icon className="size-4 text-fg-subtle" />{c.label}</Command.Item>)}
                </Command.Group>)}
              {nav.some((n) => match(`go to ${n.label}`)) && (
                <Command.Group heading="Go to" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-fg-subtle">
                  {nav.filter((n) => match(`go to ${n.label}`)).map((n) => <Command.Item key={n.href} value={`go-${n.href}`} onSelect={run(() => router.push(n.href))} className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm aria-selected:bg-primary-soft"><n.icon className="size-4 text-fg-subtle" /><span className="flex-1">{n.label}</span>{n.chord && <span className="flex gap-1"><Kbd>G</Kbd><Kbd>{n.chord.toUpperCase()}</Kbd></span>}</Command.Item>)}
                </Command.Group>)}
              {!hasResults && null}
            </Command.List>
            <div className="flex items-center justify-between border-t border-border bg-surface-2 px-4 py-2 text-xs text-fg-subtle"><span className="flex items-center gap-3"><span><Kbd>↑</Kbd> <Kbd>↓</Kbd> navigate</span><span><Kbd>↵</Kbd> select</span></span><span>Search is scoped to your workspace</span></div>
          </Command>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
