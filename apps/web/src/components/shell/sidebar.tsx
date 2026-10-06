"use client";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Bell, Check, ChevronsUpDown, HelpCircle, Keyboard, LifeBuoy, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Plus, Settings2, Sun, User } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { Avatar, Badge, Button, DropdownContent, DropdownItem, DropdownLabel, DropdownMenu, DropdownSeparator, DropdownTrigger, Logo, LogoMark, Tooltip, cn, humanDuration, useTheme } from "@crm/ui";
import { api } from "@/lib/api";
import { NAV } from "@/lib/nav";
import { useAccess, useMe } from "@/lib/queries";
import { NotificationsPopover } from "./notifications";
import { useUI } from "./ui-context";

export function useNavItems() {
  const { can, has } = useAccess();
  return NAV.filter((n) => (!n.perm || can(n.perm)) && (!n.feature || has(n.feature)));
}

export function WorkspaceSwitcher({ collapsed }: { collapsed?: boolean }) {
  const { data: me } = useMe();
  const router = useRouter();
  const ws = me?.workspace;
  const switchTo = async (id: string) => { await api.post("/api/v1/auth/switch-workspace", { workspace_id: id }); window.location.href = "/app"; };
  const create = async () => {
    const name = window.prompt("Name your new workspace");
    if (!name?.trim()) return;
    const r = await api.post<{ workspace_id: string }>("/api/v1/workspaces", { name: name.trim() });
    await switchTo(r.workspace_id);
  };
  void router;
  return (
    <DropdownMenu>
      <DropdownTrigger asChild>
        <button className={cn("flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition-colors hover:bg-surface-hover", collapsed && "justify-center")} aria-label="Switch workspace">
          <Avatar name={ws?.name} src={ws?.logo_url} size={28} square />
          {!collapsed && <><span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-semibold leading-tight">{ws?.name}</span><span className="block truncate text-xs text-fg-subtle">{me?.subscription?.plan_name}</span></span><ChevronsUpDown className="size-3.5 text-fg-subtle" /></>}
        </button>
      </DropdownTrigger>
      <DropdownContent align="start" side="top" className="w-64">
        <DropdownLabel>Workspaces</DropdownLabel>
        {me?.workspaces.map((w) => (
          <DropdownItem key={w.workspace_id} icon={<Avatar name={w.name} size={20} square />} onSelect={() => w.workspace_id !== ws?.id && switchTo(w.workspace_id)}>
            <span className="flex items-center justify-between gap-2"><span className="truncate">{w.name}</span>{w.workspace_id === ws?.id && <Check className="!size-4 !text-primary" />}</span>
          </DropdownItem>
        ))}
        <DropdownSeparator />
        <DropdownItem icon={<Plus />} onSelect={create}>Create workspace</DropdownItem>
      </DropdownContent>
    </DropdownMenu>
  );
}

export function HelpMenu({ collapsed }: { collapsed?: boolean }) {
  const ui = useUI();
  return (
    <DropdownMenu>
      <Tooltip content="Help" side="right">
        <DropdownTrigger asChild><Button variant="ghost" size={collapsed ? "icon" : "sm"} className={cn(!collapsed && "min-w-0 flex-1 justify-start")} aria-label="Help"><HelpCircle />{!collapsed && "Help"}</Button></DropdownTrigger>
      </Tooltip>
      <DropdownContent align="start" side="top">
        <DropdownItem icon={<Keyboard />} shortcut="?" onSelect={() => ui.openShortcuts()}>Keyboard shortcuts</DropdownItem>
        <DropdownItem icon={<LifeBuoy />} onSelect={() => window.open("mailto:support@crmwala.com")}>Contact support</DropdownItem>
        <DropdownItem icon={<Settings2 />} onSelect={() => ui.openCommand()} shortcut="⌘K">Open command palette</DropdownItem>
      </DropdownContent>
    </DropdownMenu>
  );
}

export function UserMenu({ collapsed }: { collapsed?: boolean }) {
  const { data: me } = useMe();
  const router = useRouter();
  const { resolved, setPref } = useTheme();
  const logout = async () => { try { await api.post("/api/v1/auth/logout"); } finally { window.location.href = "/login"; } };
  const u = me?.user;
  return (
    <DropdownMenu>
      <DropdownTrigger asChild>
        <button className={cn("flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition-colors hover:bg-surface-hover", collapsed && "justify-center")} aria-label="Account menu">
          <Avatar name={u?.name} src={u?.avatar_url} size={28} />
          {!collapsed && <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium leading-tight">{u?.name}</span><span className="block truncate text-xs text-fg-subtle">{me?.role?.name}</span></span>}
        </button>
      </DropdownTrigger>
      <DropdownContent align="start" side="top" className="w-60">
        <div className="px-2.5 py-2"><p className="truncate text-sm font-medium">{u?.name}</p><p className="truncate text-xs text-fg-muted">{u?.email}</p></div>
        <DropdownSeparator />
        <DropdownItem icon={<User />} onSelect={() => router.push("/app/settings/profile")}>Profile & preferences</DropdownItem>
        <DropdownItem icon={resolved === "dark" ? <Sun /> : <Moon />} onSelect={() => { const next = resolved === "dark" ? "light" : "dark"; setPref(next); api.patch("/api/v1/me/preferences", { theme: next }).catch(() => {}); }}>{resolved === "dark" ? "Light mode" : "Dark mode"}</DropdownItem>
        <DropdownSeparator />
        <DropdownItem icon={<LogOut />} danger onSelect={logout}>Sign out</DropdownItem>
      </DropdownContent>
    </DropdownMenu>
  );
}

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  const items = useNavItems();
  const { data: me } = useMe();
  const { can } = useAccess();
  const tasks = useQuery({ queryKey: ["tasks-summary-badge"], enabled: can("tasks.read"), queryFn: () => api.get<{ today: number; overdue: number }>("/api/v1/tasks/summary", { mine: "true" }), refetchInterval: 60_000 });
  const badge = (href: string) => (href === "/app/tasks" ? (tasks.data?.overdue ?? 0) + (tasks.data?.today ?? 0) : 0);
  const active = (href: string) => (href === "/app" ? pathname === "/app" : pathname.startsWith(href));
  const trialLeft = me?.subscription?.status === "trialing" ? me.subscription.access.seconds_left : null;
  return (
    <aside className={cn("sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200 ease-out md:flex", collapsed ? "w-[68px]" : "w-[248px]")} aria-label="Sidebar">
      <div className={cn("flex h-14 items-center px-4", collapsed ? "justify-center" : "justify-between")}>
        <Link href="/app" aria-label="Home">{collapsed ? <LogoMark /> : <Logo />}</Link>
        {!collapsed && <Tooltip content="Collapse sidebar" shortcut="["><Button variant="ghost" size="icon-sm" onClick={onToggle} aria-label="Collapse sidebar"><PanelLeftClose /></Button></Tooltip>}
      </div>
      <nav className="hide-scrollbar flex-1 space-y-0.5 overflow-y-auto px-3 py-2" aria-label="Main">
        {items.map((n) => {
          const a = active(n.href);
          const b = badge(n.href);
          const link = (
            <Link key={n.href} href={n.href} aria-current={a ? "page" : undefined}
              className={cn("group relative flex h-9 items-center gap-3 rounded-lg px-3 text-[13.5px] font-medium transition-colors", a ? "text-primary" : "text-fg-muted hover:bg-surface-hover hover:text-fg", collapsed && "justify-center px-0")}>
              {a && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-lg bg-primary-soft" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
              <n.icon className="relative size-[18px] shrink-0" />
              {!collapsed && <span className="relative flex-1 truncate">{n.label}</span>}
              {!collapsed && b > 0 && <Badge tone="primary" className="relative">{b}</Badge>}
              {collapsed && b > 0 && <span className="absolute right-2 top-1.5 size-2 rounded-full bg-primary ring-2 ring-surface" />}
            </Link>
          );
          return collapsed ? <Tooltip key={n.href} content={n.label} side="right">{link}</Tooltip> : link;
        })}
      </nav>
      {!collapsed && trialLeft != null && (
        <Link href="/app/billing" className="mx-3 mb-2 block rounded-lg border border-primary/20 bg-primary-soft/60 p-3 transition-colors hover:bg-primary-soft">
          <p className="text-xs font-semibold text-primary">Free trial</p><p className="mt-0.5 text-[13px] text-fg">{trialLeft > 0 ? `${humanDuration(trialLeft)} left` : "Ended"}</p>
          <p className="mt-1 text-xs font-medium text-primary">Choose a plan →</p>
        </Link>
      )}
      <div className={cn("space-y-1 border-t border-border p-3", collapsed && "flex flex-col items-center")}>
        <div className={cn("flex items-center gap-1", collapsed && "flex-col")}>
          <HelpMenu collapsed={collapsed} />
          <NotificationsPopover collapsed={collapsed} />
          {collapsed && <Tooltip content="Expand sidebar" shortcut="[" side="right"><Button variant="ghost" size="icon" onClick={onToggle} aria-label="Expand sidebar"><PanelLeftOpen /></Button></Tooltip>}
        </div>
        <WorkspaceSwitcher collapsed={collapsed} />
        <UserMenu collapsed={collapsed} />
      </div>
    </aside>
  );
}
