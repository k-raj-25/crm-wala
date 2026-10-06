"use client";
import {
  Activity, BarChart3, Building2, CreditCard, FileText, Flag, Gauge, HeartPulse, LogOut, Mail, Menu, Settings, ShieldCheck, Tag, UserCog, Users, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { ApiError, Avatar, Badge, Button, DropdownContent, DropdownItem, DropdownLabel, DropdownMenu, DropdownSeparator, DropdownTrigger, ErrorState, Logo, Skeleton, ThemeToggle, cn } from "@crm/ui";
import { A, api } from "@/lib/api";
import { useAdmin } from "@/lib/hooks";

type Item = { href: string; label: string; icon: React.ReactNode; roles?: string[] };
const NAV: { group: string; items: Item[] }[] = [
  { group: "Overview", items: [{ href: "/dashboard", label: "Dashboard", icon: <Gauge /> }, { href: "/analytics", label: "Analytics", icon: <BarChart3 /> }] },
  { group: "Accounts", items: [{ href: "/users", label: "Users", icon: <Users /> }, { href: "/workspaces", label: "Workspaces", icon: <Building2 /> }] },
  { group: "Revenue", items: [{ href: "/billing", label: "Billing & payments", icon: <CreditCard /> }, { href: "/plans", label: "Plans & limits", icon: <Tag /> }, { href: "/coupons", label: "Coupons", icon: <Tag /> }] },
  { group: "Platform", items: [
    { href: "/flags", label: "Feature flags", icon: <Flag /> }, { href: "/audit", label: "Audit logs", icon: <FileText /> }, { href: "/system", label: "System health", icon: <HeartPulse /> },
    { href: "/emails", label: "Email templates", icon: <Mail /> }, { href: "/settings", label: "Settings", icon: <Settings /> }, { href: "/admins", label: "Admin team", icon: <UserCog />, roles: ["superadmin"] },
  ] },
];

function Nav({ onNavigate, role }: { onNavigate?: () => void; role?: string }) {
  const path = usePathname();
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4" aria-label="Admin navigation">
      {NAV.map((g) => (
        <div key={g.group}>
          <p className="px-2.5 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-white/40">{g.group}</p>
          <ul className="space-y-0.5">
            {g.items.filter((i) => !i.roles || (role && (role === "superadmin" || i.roles.includes(role)))).map((i) => {
              const active = path === i.href || path.startsWith(i.href + "/");
              return (
                <li key={i.href}>
                  <Link href={i.href} onClick={onNavigate} aria-current={active ? "page" : undefined}
                    className={cn("flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm transition-colors [&_svg]:size-4", active ? "bg-white/12 font-medium text-white" : "text-white/65 hover:bg-white/8 hover:text-white")}>
                    {i.icon}{i.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex h-14 items-center gap-2.5 px-4">
      <span className="flex size-8 items-center justify-center rounded-lg bg-amber-400 text-slate-900"><ShieldCheck className="size-4" /></span>
      <div className="leading-tight"><p className="text-sm font-semibold text-white">CRM Wala</p><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-300">Super Admin</p></div>
    </div>
  );
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading, error, refetch } = useAdmin();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const path = usePathname();
  React.useEffect(() => setOpen(false), [path]);
  React.useEffect(() => { if (error instanceof ApiError && [401, 403].includes(error.status)) router.replace(`/login?next=${encodeURIComponent(path)}`); }, [error, router, path]);

  const logout = async () => { await api.post(`${A}/auth/logout`).catch(() => null); router.replace("/login"); };

  if (isLoading) return <div className="grid min-h-dvh place-items-center"><Skeleton className="h-8 w-48" /></div>;
  if (error || !data) return <ErrorState kind="network" onRetry={() => refetch()} />;
  const { admin } = data;

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-[248px] shrink-0 flex-col bg-[#0d0f1f] lg:flex"><Brand /><Nav role={admin.role} /></aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="relative flex h-full w-[272px] flex-col bg-[#0d0f1f]"><Brand /><Nav role={admin.role} onNavigate={() => setOpen(false)} />
            <button onClick={() => setOpen(false)} aria-label="Close menu" className="absolute right-3 top-3 rounded p-1 text-white/70"><X className="size-5" /></button></aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur sm:px-6">
          <Button variant="ghost" size="icon-sm" className="lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu /></Button>
          <div className="flex items-center gap-2"><Badge tone="warning" dot>Production console</Badge><span className="hidden text-xs text-fg-subtle sm:inline">Every action here is audit-logged</span></div>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <DropdownMenu>
              <DropdownTrigger asChild><button className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-surface-hover" aria-label="Account menu"><Avatar name={admin.name} size={28} /><span className="hidden text-left text-sm leading-tight sm:block"><span className="block font-medium">{admin.name}</span><span className="block text-xs capitalize text-fg-subtle">{admin.role}</span></span></button></DropdownTrigger>
              <DropdownContent>
                <DropdownLabel>{admin.email}</DropdownLabel><DropdownSeparator />
                <DropdownItem icon={<LogOut />} onSelect={logout}>Sign out</DropdownItem>
              </DropdownContent>
            </DropdownMenu>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-8 sm:py-8">{children}</main>
      </div>
    </div>
  );
}
