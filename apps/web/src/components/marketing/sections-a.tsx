"use client";
import { AnimatePresence, motion } from "framer-motion";
import { BarChart3, CalendarDays, FileText, Kanban, Mail, Phone, Repeat, ShieldCheck, Target, Users, Workflow, Zap, Building2, Handshake, CheckCircle2, Clock } from "lucide-react";
import { useState } from "react";
import { Avatar, Badge, Card, Segmented, cn } from "@crm/ui";
import { Container, Reveal, Section, Window } from "./primitives";

export function TrustedBy() {
  const names = ["Northwind", "Lumina", "Fieldstone", "Aperture", "Brightly", "Cobalt & Co"];
  return (
    <section className="border-y border-border bg-surface/50 py-10" aria-label="Customers">
      <Container>
        <p className="mb-6 text-center text-sm font-medium text-fg-subtle">Trusted by fast-growing teams</p>
        <div className="grid grid-cols-2 items-center gap-x-8 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
          {names.map((n, i) => (
            <Reveal key={n} delay={i * 0.04} className="flex items-center justify-center gap-2 text-fg-subtle/90 transition-colors hover:text-fg-muted">
              <span className="size-5 rounded-md bg-current opacity-60" style={{ borderRadius: i % 2 ? "999px" : "6px" }} aria-hidden /><span className="text-[17px] font-semibold tracking-tight">{n}</span>
            </Reveal>
          ))}
        </div>
      </Container>
    </section>
  );
}

const BENEFITS = [
  { icon: Users, title: "Manage leads", body: "Capture, score and qualify leads in one list. Know who's hot at a glance.", color: "var(--series-1)" },
  { icon: Handshake, title: "Close deals", body: "A drag-and-drop pipeline that shows what's moving and what's stuck.", color: "var(--series-3)" },
  { icon: Repeat, title: "Automate follow-ups", body: "Assign, email and remind automatically — nothing slips through the cracks.", color: "var(--series-2)" },
  { icon: BarChart3, title: "Track performance", body: "Revenue, win rate and forecasts that update as your team works.", color: "var(--series-7)" },
  { icon: Users, title: "Collaborate with your team", body: "Roles, mentions and one shared timeline for every customer.", color: "var(--series-5)" },
];
export function Benefits() {
  return (
    <Section eyebrow="Why teams switch" title="Everything you need to sell. Nothing you don't." subtitle="Most CRMs make you learn them. CRM Wala makes it obvious what to do next.">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
        {BENEFITS.map((b, i) => (
          <Reveal key={b.title} delay={i * 0.06} className={cn("lg:col-span-2", i >= 3 && "lg:col-span-3")}>
            <Card hover className="h-full p-6">
              <span className="mb-4 flex size-10 items-center justify-center rounded-xl" style={{ background: `color-mix(in srgb, ${b.color} 14%, transparent)`, color: b.color }}><b.icon className="size-5" /></span>
              <h3 className="text-[17px] font-semibold tracking-tight">{b.title}</h3><p className="mt-1.5 text-[15px] text-fg-muted">{b.body}</p>
            </Card>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}

function PreviewDashboard() {
  return (
    <div className="grid gap-3 p-4 sm:grid-cols-3">
      {[["Revenue", "₹16.9L", "+172%"], ["Pipeline", "₹2.56Cr", "15 deals"], ["Win rate", "75%", "+8.3 pts"]].map(([a, b, c]) => <div key={a} className="rounded-xl border border-border bg-surface p-3.5"><p className="text-xs text-fg-muted">{a}</p><p className="mt-1 text-2xl font-semibold tabular">{b}</p><p className="text-xs text-success">{c}</p></div>)}
      <div className="rounded-xl border border-border bg-surface p-4 sm:col-span-3">
        <p className="mb-3 text-sm font-medium">What needs your attention</p>
        {[["Send revised proposal to Zenith", "Today · High", "warning"], ["Kavya — Dealer network CRM went quiet", "No activity in 9 days", "danger"], ["Follow up with Orbit CFO", "Overdue by 2 days", "danger"]].map(([t, s, tone]) => (
          <div key={t} className="flex items-center justify-between gap-3 border-t border-border py-2.5 first:border-0 first:pt-0"><span className="flex items-center gap-2.5 text-sm"><span className="size-4 rounded-full border-2 border-border-strong" />{t}</span><Badge tone={tone as "warning" | "danger"}>{s}</Badge></div>
        ))}
      </div>
    </div>
  );
}
function PreviewPipeline() {
  const cols = [["Qualified", [["Lumen — Admissions", "₹4.5L"], ["GreenLeaf — Starter", "₹1.2L"]]], ["Proposal", [["Vertex — Outreach", "₹31L"], ["Orbit — Compliance", "₹12L"]]], ["Negotiation", [["Zenith — Fleet CRM", "₹18.5L"]]]] as const;
  return (
    <div className="grid gap-3 p-4 sm:grid-cols-3">
      {cols.map(([n, deals]) => (
        <div key={n} className="rounded-xl bg-bg-subtle/70 p-2.5">
          <p className="mb-2 flex justify-between px-1 text-xs font-semibold text-fg-muted"><span>{n}</span><span className="tabular text-fg-subtle">{deals.length}</span></p>
          <div className="space-y-2">{deals.map(([d, v]) => <motion.div whileHover={{ y: -2 }} key={d} className="cursor-grab rounded-lg border border-border bg-surface p-3 shadow-xs"><p className="text-sm font-medium">{d}</p><div className="mt-2 flex items-center justify-between"><span className="tabular text-sm font-semibold text-primary">{v}</span><Avatar name={d} size={20} /></div></motion.div>)}</div>
        </div>
      ))}
    </div>
  );
}
function PreviewContact() {
  return (
    <div className="grid gap-4 p-4 sm:grid-cols-[220px_1fr]">
      <div className="rounded-xl border border-border bg-surface p-4 text-center"><Avatar name="Rahul Khanna" size={56} className="mx-auto" /><p className="mt-2 font-semibold">Rahul Khanna</p><p className="text-xs text-fg-muted">Head of Operations · Zenith Logistics</p><div className="mt-3 flex justify-center gap-2"><Badge tone="primary">enterprise</Badge><Badge tone="success">customer</Badge></div></div>
      <div className="rounded-xl border border-border bg-surface p-4">
        {[[Mail, "Email sent: Proposal — Fleet CRM", "10:30 AM"], [Handshake, "Deal moved to Negotiation", "9:15 AM"], [Phone, "Call — connected (12 min)", "Yesterday"], [CalendarDays, "Meeting completed: Kickoff", "Monday"]].map(([I, t, w], i) => {
          const Icon = I as typeof Mail;
          return <div key={t as string} className="flex gap-3 pb-4 last:pb-0"><div className="flex flex-col items-center"><span className="flex size-7 items-center justify-center rounded-full bg-primary-soft text-primary"><Icon className="size-3.5" /></span>{i < 3 && <span className="mt-1 w-px flex-1 bg-border" />}</div><div><p className="text-sm font-medium">{t as string}</p><p className="text-xs text-fg-subtle">{w as string}</p></div></div>;
        })}
      </div>
    </div>
  );
}

export function ProductPreview() {
  const [tab, setTab] = useState<"dashboard" | "pipeline" | "customer">("dashboard");
  return (
    <Section id="product" tone="subtle" eyebrow="Product tour" title="Clear at a glance. Powerful when you need it." subtitle="Click through the real interface — progressive disclosure keeps advanced options out of your way until you need them.">
      <Reveal className="mx-auto max-w-4xl">
        <div className="mb-5 flex justify-center"><Segmented value={tab} onChange={setTab} options={[{ value: "dashboard", label: "Dashboard" }, { value: "pipeline", label: "Pipeline" }, { value: "customer", label: "Customer" }]} /></div>
        <Window>
          <AnimatePresence mode="wait"><motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="bg-bg">
            {tab === "dashboard" ? <PreviewDashboard /> : tab === "pipeline" ? <PreviewPipeline /> : <PreviewContact />}
          </motion.div></AnimatePresence>
        </Window>
      </Reveal>
    </Section>
  );
}

const FEATURES = [
  [Users, "Leads & contacts", "Scoring, tags, owners, bulk actions and instant search across everything."],
  [Building2, "Companies", "One page per account that rolls up every contact, deal, email and note."],
  [Kanban, "Visual pipelines", "Drag deals between stages. Multiple pipelines, custom stages, live totals."],
  [CheckCircle2, "Tasks & follow-ups", "List, board and calendar views with due-today and overdue at the top."],
  [CalendarDays, "Calendar", "Meetings, calls, follow-ups and deadlines in day, week and month views."],
  [Mail, "Email & calls", "Send, track and log conversations; everything lands on the right timeline."],
  [FileText, "Files", "Attach contracts and proposals to any record with secure, signed links."],
  [Workflow, "Automations", "A visual builder for assign → email → task → wait → remind."],
  [BarChart3, "Reports", "Revenue, pipeline, team performance and forecast — exportable and schedulable."],
  [ShieldCheck, "Roles & security", "Granular permissions, audit logs, 2FA and strict workspace isolation."],
  [Target, "Imports & dedupe", "Map CSV columns, fix errors before import, and merge duplicates."],
  [Zap, "Command palette", "Press ⌘K to jump anywhere or create anything in two keystrokes."],
] as const;
export function Features() {
  return (
    <Section id="features" eyebrow="Features" title="A complete CRM, without the clutter" subtitle="Strong where it counts, quiet everywhere else.">
      <div className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(([I, t, b], i) => (
          <Reveal key={t} delay={(i % 3) * 0.06} className="flex gap-4">
            <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-surface text-primary shadow-xs"><I className="size-5" /></span>
            <div><h3 className="font-semibold tracking-tight">{t}</h3><p className="mt-1 text-[15px] text-fg-muted">{b}</p></div>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
export { Clock };
