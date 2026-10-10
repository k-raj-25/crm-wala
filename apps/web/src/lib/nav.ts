import { Activity, BarChart3, Bot, Building2, Landmark, CalendarDays, CheckSquare, Handshake, Home, Inbox, Kanban, Plug, Settings, UserRound, Users, Workflow } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; perm?: string; feature?: string; chord?: string };
export const NAV: NavItem[] = [
  { href: "/app", label: "Home", icon: Home, chord: "h" },
  { href: "/app/projects", label: "Projects", icon: Building2, perm: "projects.read", chord: "b" },
  { href: "/app/inbox", label: "Inbox", icon: Inbox, perm: "emails.read", chord: "i" },
  { href: "/app/leads", label: "Leads", icon: Users, perm: "leads.read", chord: "l" },
  { href: "/app/contacts", label: "Contacts", icon: UserRound, perm: "contacts.read", chord: "c" },
  { href: "/app/companies", label: "Companies", icon: Landmark, perm: "companies.read", chord: "o" },
  { href: "/app/deals", label: "Deals", icon: Handshake, perm: "deals.read", chord: "d" },
  { href: "/app/pipeline", label: "Pipeline", icon: Kanban, perm: "deals.read", chord: "p" },
  { href: "/app/tasks", label: "Tasks", icon: CheckSquare, perm: "tasks.read", chord: "t" },
  { href: "/app/calendar", label: "Calendar", icon: CalendarDays, perm: "meetings.read", chord: "k" },
  { href: "/app/activities", label: "Activities", icon: Activity, perm: "activities.read", chord: "a" },
  { href: "/app/automations", label: "Automations", icon: Workflow, perm: "automations.read", chord: "u" },
  { href: "/app/reports", label: "Reports", icon: BarChart3, perm: "reports.read", chord: "r" },
  { href: "/app/ai", label: "AI Assistant", icon: Bot, perm: "ai.use", chord: "j" },
  { href: "/app/integrations", label: "Integrations", icon: Plug, chord: "n" },
  { href: "/app/settings", label: "Settings", icon: Settings, chord: "s" },
];
export const MOBILE_PRIMARY = ["/app", "/app/leads", "/app/deals", "/app/tasks"];
