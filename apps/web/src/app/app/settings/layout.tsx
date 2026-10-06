"use client";
import { Bell, Building2, ClipboardList, CreditCard, Database, GitBranch, KeyRound, ListChecks, Mail, Shield, Tags, User, Users, Wand2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { useAccess } from "@/lib/queries";

const GROUPS = [
  { title: "Personal", items: [["profile", "Profile & preferences", User], ["notifications", "Notifications", Bell], ["security", "Security", Shield]] },
  { title: "Workspace", items: [["workspace", "Workspace & branding", Building2, "settings.manage"], ["team", "Team", Users, "team.read"], ["roles", "Roles & permissions", KeyRound, "team.read"], ["pipelines", "Pipelines & stages", GitBranch, "pipelines.read"], ["lead-statuses", "Lead statuses", ListChecks, "settings.manage"], ["custom-fields", "Custom fields", Wand2, "settings.manage"], ["tags", "Tags", Tags, "settings.manage"], ["email", "Email & templates", Mail, "emails.read"], ["data", "Import & export", Database, "data.export"], ["audit", "Audit log", ClipboardList, "audit.read"]] },
] as const;

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname(); const { can } = useAccess();
  return (
    <PageContainer>
      <PageHeader title="Settings" description="Manage your profile, workspace and billing." />
      <div className="grid gap-8 lg:grid-cols-[230px_1fr]">
        <nav aria-label="Settings" className="hide-scrollbar -mx-4 flex gap-1 overflow-x-auto px-4 lg:mx-0 lg:flex-col lg:px-0">
          {GROUPS.map((g) => <div key={g.title} className="flex gap-1 lg:block lg:space-y-0.5"><p className="mb-1 mt-2 hidden px-3 text-xs font-semibold uppercase tracking-wider text-fg-subtle first:mt-0 lg:block">{g.title}</p>
            {g.items.filter((i) => !i[3] || can(i[3])).map(([k, l, I]) => <Link key={k} href={`/app/settings/${k}`} aria-current={path === `/app/settings/${k}` ? "page" : undefined} className={cn("flex shrink-0 items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors", path === `/app/settings/${k}` ? "bg-primary-soft text-primary" : "text-fg-muted hover:bg-surface-hover hover:text-fg")}><I className="size-4" />{l}</Link>)}</div>)}
          {can("billing.manage") && <Link href="/app/billing" className="flex shrink-0 items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-[13.5px] font-medium text-fg-muted hover:bg-surface-hover hover:text-fg lg:mt-2"><CreditCard className="size-4" />Billing & plan</Link>}
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </PageContainer>
  );
}
