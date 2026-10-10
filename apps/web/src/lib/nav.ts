import { Activity, BarChart3, Bot, Building2, CalendarDays, CheckSquare, Handshake, Home, Inbox, Kanban, Landmark, Plug, Settings, UserRound, Users, Workflow } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; perm?: string; feature?: string; chord?: string; more?: boolean };
/** Built for realtors: what you touch every day sits up top; the rest folds away under "More" so the sidebar stays calm. */
export const NAV: NavItem[] = [
  { href: "/app", label: "Home", icon: Home, chord: "h" },
  { href: "/app/projects", label: "Projects", icon: Building2, perm: "projects.read", chord: "b" },
  { href: "/app/leads", label: "Leads", icon: Users, perm: "leads.read", chord: "l" },
  { href: "/app/contacts", label: "Clients", icon: UserRound, perm: "contacts.read", chord: "c" },
  { href: "/app/pipeline", label: "Pipeline", icon: Kanban, perm: "deals.read", chord: "p" },
  { href: "/app/deals", label: "Deals", icon: Handshake, perm: "deals.read", chord: "d" },
  { href: "/app/calendar", label: "Site Visits", icon: CalendarDays, perm: "meetings.read", chord: "k" },
  { href: "/app/tasks", label: "Daily Plan", icon: CheckSquare, perm: "tasks.read", chord: "t" },
  { href: "/app/inbox", label: "Inbox", icon: Inbox, perm: "emails.read", chord: "i" },
  { href: "/app/reports", label: "Reports", icon: BarChart3, perm: "reports.read", chord: "r", more: true },
  { href: "/app/companies", label: "Builders", icon: Landmark, perm: "companies.read", chord: "o", more: true },
  { href: "/app/activities", label: "Activities", icon: Activity, perm: "activities.read", chord: "a", more: true },
  { href: "/app/automations", label: "Automations", icon: Workflow, perm: "automations.read", chord: "u", more: true },
  { href: "/app/ai", label: "AI Assistant", icon: Bot, perm: "ai.use", chord: "j", more: true },
  { href: "/app/integrations", label: "Integrations", icon: Plug, chord: "n", more: true },
  { href: "/app/settings", label: "Settings", icon: Settings, chord: "s" },
];
export const MOBILE_PRIMARY = ["/app", "/app/projects", "/app/leads", "/app/tasks"];
