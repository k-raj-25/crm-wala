"use client";
import { AnimatePresence, motion } from "framer-motion";
import { BarChart3, CalendarDays, Kanban, Mail, Phone, ShieldCheck, Target, Users, Workflow, Zap, Building2, Handshake, CheckCircle2, Clock } from "lucide-react";
import { useState } from "react";
import { Avatar, Badge, Card, Segmented, cn } from "@crm/ui";
import { Container, Reveal, Section, Window } from "./primitives";

export function TrustedBy() {
  const names = ["Independent agents", "Brokerage teams", "Channel partners", "Developer sales desks", "Rental specialists", "Property consultants"];
  return (
    <section className="border-y border-border bg-surface/50 py-10" aria-label="Who it's for">
      <Container>
        <p className="mb-6 text-center text-sm font-medium text-fg-subtle">Made for people who sell and rent property</p>
        <div className="grid grid-cols-2 items-center gap-x-8 gap-y-4 text-center sm:grid-cols-3 lg:grid-cols-6">
          {names.map((n, i) => <Reveal key={n} delay={i * 0.04}><span className="text-[15px] font-semibold tracking-tight text-fg-muted">{n}</span></Reveal>)}
        </div>
      </Container>
    </section>
  );
}

const BENEFITS = [
  { icon: Building2, title: "See the whole building", body: "Every tower, floor and flat drawn the way you see it. Vacant, listed, held, sold or rented — in colour, in a second.", color: "var(--series-1)" },
  { icon: Target, title: "Match clients to flats", body: "Note a client's budget and size once. We show the flats that fit — and the clients who fit a flat.", color: "var(--series-3)" },
  { icon: Clock, title: "Hold with a countdown", body: "Hold a flat for a client for 24 hours or a week. It returns to stock by itself when time runs out.", color: "var(--series-2)" },
  { icon: CalendarDays, title: "Never miss a site visit", body: "Schedule visits against the exact flat. Today's visits and follow-ups sit on your home screen.", color: "var(--series-7)" },
  { icon: Handshake, title: "Close with one drag", body: "Move a deal to Closed and the flat turns sold on the building. No double entry, ever.", color: "var(--series-5)" },
];
export function Benefits() {
  return (
    <Section eyebrow="Why realtors switch" title="Everything you need to sell property. Nothing you don't." subtitle="Most CRMs are built for software sales and make you learn them. CRM Wala speaks real estate and makes it obvious what to do next.">
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

function PreviewBuilding() {
  const rows = ["vrvs", "ovrv", "vsvr", "vvhv", "rvvs", "bvdv"];
  const C: Record<string, string> = { v: "#dfe5ee", s: "#dc2626", r: "#15803d", o: "#f59e0b", h: "#7c3aed", b: "#2563eb", d: "#334155" };
  const ink: Record<string, string> = { v: "#3b4558", o: "#3a2100" };
  return (
    <div className="grid gap-4 p-4 sm:grid-cols-[1.2fr_1fr]">
      <div className="rounded-xl border border-border bg-[var(--frame)] p-2">
        {rows.map((r, ri) => (
          <div key={ri} className="grid grid-cols-[28px_1fr] items-center gap-2 border-b-4 border-[var(--slab)] py-[3px] last:border-0"><span className="text-right text-[10px] font-semibold text-fg-muted">{String(rows.length - ri).padStart(2, "0")}</span>
            <div className="grid grid-cols-4 gap-1.5">{r.split("").map((c, i) => <span key={i} className="flex h-8 items-center rounded-md px-1.5 text-[10.5px] font-semibold" style={{ background: C[c], color: ink[c] ?? "#fff", boxShadow: "inset 0 -3px 0 rgba(0,0,0,.18)" }}>{rows.length - ri}0{i + 1}</span>)}</div></div>
        ))}
      </div>
      <div className="space-y-3">
        {[["Available", "12", "var(--success)"], ["On hold", "2", "#7c3aed"], ["Sold or rented", "9", "var(--fg)"]].map(([a, b, c]) => <div key={a} className="rounded-xl border border-border bg-surface p-3.5"><p className="text-xs text-fg-muted">{a}</p><p className="mt-1 text-2xl font-semibold tabular" style={{ color: c }}>{b}</p></div>)}
        <div className="rounded-xl border border-border bg-surface p-3.5 text-sm"><p className="font-medium">Unit 304 · 3 BHK · ₹2.4 Cr</p><p className="mt-0.5 text-xs text-fg-muted">3 clients may want this</p></div>
      </div>
    </div>
  );
}
function PreviewToday() {
  return (
    <div className="grid gap-3 p-4 sm:grid-cols-3">
      {[["Site visits today", "3", "next at 4:00 PM"], ["Follow-ups due", "7", "2 overdue"], ["Holds ending", "2", "within 24 hours"]].map(([a, b, c]) => <div key={a} className="rounded-xl border border-border bg-surface p-3.5"><p className="text-xs text-fg-muted">{a}</p><p className="mt-1 text-2xl font-semibold tabular">{b}</p><p className="text-xs text-fg-subtle">{c}</p></div>)}
      <div className="rounded-xl border border-border bg-surface p-4 sm:col-span-3">
        <p className="mb-3 text-sm font-medium">What needs your attention</p>
        {[["Call back Mohit Agarwal about the 4 BHK", "Today · High", "warning"], ["Hold on Unit 603 ends in 5 hours", "Mehta family", "danger"], ["Send brochure to Lakshmi Pillai", "Overdue by 1 day", "danger"]].map(([t, s, tone]) => (
          <div key={t} className="flex items-center justify-between gap-3 border-t border-border py-2.5 first:border-0 first:pt-0"><span className="flex items-center gap-2.5 text-sm"><span className="size-4 rounded-full border-2 border-border-strong" />{t}</span><Badge tone={tone as "warning" | "danger"}>{s}</Badge></div>
        ))}
      </div>
    </div>
  );
}
function PreviewPipeline() {
  const cols = [["Site visit", [["Gautam Bhatt — Unit 802", "₹1.73Cr"], ["Aarti Desai — Unit 1004", "₹3.42Cr"]]], ["Negotiation", [["Lakshmi Pillai — Unit 603", "₹2.41Cr"], ["Rohan Bose — Unit 404", "₹2.53Cr"]]], ["Token paid", [["Siddharth Rao — Unit 401", "₹2.53Cr"]]]] as const;
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
      <div className="rounded-xl border border-border bg-surface p-4 text-center"><Avatar name="Lakshmi Pillai" size={56} className="mx-auto" /><p className="mt-2 font-semibold">Lakshmi Pillai</p><p className="text-xs text-fg-muted">Buying · 3 BHK · up to ₹3 Cr</p><div className="mt-3 flex justify-center gap-2"><Badge tone="primary">first-time-buyer</Badge><Badge tone="warning">hot</Badge></div></div>
      <div className="rounded-xl border border-border bg-surface p-4">
        {[[Mail, "Brochure sent: Ireo Victory Valley", "10:30 AM"], [CalendarDays, "Site visit scheduled: Unit 603", "9:15 AM"], [Phone, "Call — connected (8 min)", "Yesterday"], [Handshake, "Deal moved to Negotiation", "Monday"]].map(([I, t, w], i) => {
          const Icon = I as typeof Mail;
          return <div key={t as string} className="flex gap-3 pb-4 last:pb-0"><div className="flex flex-col items-center"><span className="flex size-7 items-center justify-center rounded-full bg-primary-soft text-primary"><Icon className="size-3.5" /></span>{i < 3 && <span className="mt-1 w-px flex-1 bg-border" />}</div><div><p className="text-sm font-medium">{t as string}</p><p className="text-xs text-fg-subtle">{w as string}</p></div></div>;
        })}
      </div>
    </div>
  );
}

export function ProductPreview() {
  const [tab, setTab] = useState<"building" | "today" | "pipeline" | "customer">("building");
  return (
    <Section id="product" tone="subtle" eyebrow="Product tour" title="Clear at a glance. Powerful when you need it." subtitle="Click through the product. The building comes first; the detail is one tap away.">
      <Reveal className="mx-auto max-w-4xl">
        <div className="mb-5 flex justify-center"><Segmented value={tab} onChange={setTab} options={[{ value: "building", label: "Building" }, { value: "today", label: "Today" }, { value: "pipeline", label: "Pipeline" }, { value: "customer", label: "Client" }]} /></div>
        <Window>
          <AnimatePresence mode="wait"><motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="bg-bg">
            {tab === "building" ? <PreviewBuilding /> : tab === "today" ? <PreviewToday /> : tab === "pipeline" ? <PreviewPipeline /> : <PreviewContact />}
          </motion.div></AnimatePresence>
        </Window>
      </Reveal>
    </Section>
  );
}

const FEATURES = [
  [Building2, "Projects, towers & flats", "Add a tower with its floors and flats per floor and we draw the whole building for you."],
  [Target, "Smart matching", "Budget, size and purpose on every lead. See the flats that fit, and the clients who fit a flat."],
  [Clock, "Holds that expire", "Hold a flat for a client for a set time. It goes back on the market on its own."],
  [Users, "Leads & clients", "Enquiries from portals, walk-ins and referrals in one list, with owners and follow-ups."],
  [Kanban, "Deal pipeline", "Enquiry → Site visit → Negotiation → Token → Closed. Drag to move; the flat updates itself."],
  [CalendarDays, "Site visits", "Schedule visits against a flat. Day, week and month views, plus reminders."],
  [CheckCircle2, "Daily plan", "Today's calls, follow-ups and visits at the top, overdue in red. Nothing hides."],
  [Mail, "Email & calls", "Send brochures, log calls and keep every conversation on the right client."],
  [Workflow, "Automations", "New enquiry? Assign it, send the brochure, create a call task and remind in 2 days."],
  [BarChart3, "Reports", "Sales, pipeline, team performance and forecast — exportable and schedulable."],
  [ShieldCheck, "Teams & security", "Roles, audit log, 2FA and strict separation between brokerages."],
  [Zap, "Instant search", "Press ⌘K and type a flat number, a client or a project. You're there."],
] as const;
export function Features() {
  return (
    <Section id="features" eyebrow="Features" title="A complete real estate CRM, without the clutter" subtitle="Strong where it counts, quiet everywhere else.">
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
