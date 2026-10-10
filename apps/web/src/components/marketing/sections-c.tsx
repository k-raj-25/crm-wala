"use client";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Check, Minus, Plus, Star } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Avatar, Badge, Button, Card, Logo, Segmented, cn, formatMoney } from "@crm/ui";
import { Container, Reveal, Section } from "./primitives";

const INTEGRATIONS = [["Gmail", "#ea4335"], ["Outlook", "#0a64c8"], ["Google Calendar", "#4285f4"], ["Slack", "#611f69"], ["Microsoft Teams", "#5b5fc7"], ["WhatsApp", "#25d366"], ["Zoom", "#2d8cff"], ["Stripe", "#635bff"], ["Razorpay", "#0c2451"], ["Zapier", "#ff4a00"], ["Webhooks", "#475569"], ["Google Sheets", "#0f9d58"]];
export function Integrations() {
  return (
    <Section id="integrations" tone="subtle" eyebrow="Integrations" title="Plays well with the tools you already use" subtitle="Connect email, calendar, chat and payments — or build your own with signed webhooks.">
      <div className="mx-auto grid max-w-4xl grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {INTEGRATIONS.map(([n, c], i) => (
          <Reveal key={n} delay={(i % 4) * 0.05}>
            <Card hover className="flex items-center gap-3 p-4"><span className="flex size-9 items-center justify-center rounded-lg text-sm font-bold text-white" style={{ background: c }}>{n[0]}</span><span className="text-sm font-medium">{n}</span></Card>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}

const QUOTES = [
  { q: "I used to keep flat availability in a spreadsheet and WhatsApp. Now I open one tower and see everything. My clients think I'm psychic.", n: "Neha Kapoor", r: "Independent agent, Gurugram" },
  { q: "Holds with a timer changed our team. No more two agents promising the same flat to two clients.", n: "Arjun Mehta", r: "Team lead, brokerage" },
  { q: "Our juniors were scared of the old CRM. They learned this one in an afternoon.", n: "Sarah Whitfield", r: "Sales head, channel partner" },
];
export function Testimonials() {
  return (
    <Section eyebrow="Loved by realtors" title="Simple enough to adopt in a day">
      <div className="grid gap-4 md:grid-cols-3">
        {QUOTES.map((t, i) => (
          <Reveal key={t.n} delay={i * 0.08}>
            <Card className="flex h-full flex-col p-6"><div className="mb-3 flex gap-0.5 text-warning" aria-label="5 out of 5 stars">{Array.from({ length: 5 }).map((_, k) => <Star key={k} className="size-4 fill-current" />)}</div>
              <p className="flex-1 text-[15px] leading-relaxed">“{t.q}”</p>
              <div className="mt-5 flex items-center gap-3"><Avatar name={t.n} size={36} /><div><p className="text-sm font-semibold">{t.n}</p><p className="text-xs text-fg-muted">{t.r}</p></div></div></Card>
          </Reveal>
        ))}
      </div>
      <p className="mt-6 text-center text-xs text-fg-subtle">Sample testimonials shown for illustration.</p>
    </Section>
  );
}

type PublicPlan = { key: string; name: string; tagline: string | null; currency: string; price_monthly: number | null; price_annual: number | null; highlights: string[]; is_custom: boolean };
const FALLBACK: PublicPlan[] = [
  { key: "starter", name: "Starter", tagline: "For solo agents and small desks", currency: "INR", price_monthly: 99900, price_annual: 999000, highlights: ["2 team members", "1,000 clients & leads", "Unlimited projects", "5 automations", "100 AI actions / month"], is_custom: false },
  { key: "growth", name: "Growth", tagline: "For growing brokerages", currency: "INR", price_monthly: 249900, price_annual: 2499000, highlights: ["10 team members", "10,000 clients & leads", "Unlimited projects", "25 automations", "Advanced reports", "500 AI actions / month"], is_custom: false },
  { key: "business", name: "Business", tagline: "For large brokerages and developer sales teams", currency: "INR", price_monthly: 599900, price_annual: 5999000, highlights: ["50 team members", "100,000 clients & leads", "Unlimited automations", "Advanced permissions", "WhatsApp", "Fair-use AI"], is_custom: false },
  { key: "enterprise", name: "Enterprise", tagline: "Custom limits, SSO and dedicated support", currency: "INR", price_monthly: null, price_annual: null, highlights: ["Unlimited everything", "Custom contract & invoicing", "Priority support"], is_custom: true },
];

export function Pricing() {
  const [annual, setAnnual] = useState(false);
  const [plans, setPlans] = useState<PublicPlan[]>(FALLBACK);
  useEffect(() => { fetch("/api/v1/public/plans").then((r) => r.json()).then((j) => j?.data?.plans?.length && setPlans(j.data.plans)).catch(() => {}); }, []);
  return (
    <Section id="pricing" tone="subtle" eyebrow="Pricing" title="Start free for 3 days. Pick a plan when you're ready." subtitle="No credit card to start. No long-term commitment. Your data is never deleted if your trial ends.">
      <div className="mb-10 flex items-center justify-center gap-3">
        <Segmented value={annual ? "annual" : "monthly"} onChange={(v) => setAnnual(v === "annual")} options={[{ value: "monthly", label: "Monthly" }, { value: "annual", label: "Annual" }]} />
        <Badge tone="success">Save ~17% yearly</Badge>
      </div>
      <div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-2 lg:grid-cols-4">
        {plans.map((p, i) => {
          const featured = p.key === "growth";
          const price = annual ? p.price_annual : p.price_monthly;
          return (
            <Reveal key={p.key} delay={i * 0.06}>
              <Card className={cn("relative flex h-full flex-col p-6", featured && "border-primary shadow-md ring-1 ring-primary/30")}>
                {featured && <Badge tone="primary" className="absolute -top-3 left-6 bg-primary text-primary-fg">Most popular</Badge>}
                <h3 className="text-lg font-semibold">{p.name}</h3><p className="mt-1 min-h-10 text-sm text-fg-muted">{p.tagline}</p>
                <div className="my-5 h-14">
                  {p.is_custom || price == null ? <p className="text-3xl font-semibold tracking-tight">Custom</p> : (
                    <AnimatePresence mode="wait"><motion.div key={String(annual)} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                      <p className="text-4xl font-semibold tracking-tight tabular">{formatMoney(price / 100, p.currency)}<span className="text-base font-normal text-fg-muted"> /{annual ? "year" : "month"}</span></p>
                      {annual && <p className="text-xs text-fg-subtle">{formatMoney(Math.round(price / 1200), p.currency)} per month, billed yearly</p>}
                    </motion.div></AnimatePresence>
                  )}
                </div>
                <Button asChild variant={featured ? "primary" : "secondary"} className="w-full"><Link href={p.is_custom ? "/signup?plan=enterprise" : `/signup?plan=${p.key}`}>{p.is_custom ? "Talk to sales" : "Start free trial"}</Link></Button>
                <ul className="mt-6 space-y-2.5 text-sm">{p.highlights.map((h) => <li key={h} className="flex gap-2.5"><Check className="mt-0.5 size-4 shrink-0 text-success" />{h}</li>)}</ul>
              </Card>
            </Reveal>
          );
        })}
      </div>
    </Section>
  );
}

const FAQS = [
  ["Is this a general CRM?", "No. It is built only for real estate: projects, towers, floors and flats, buyers, renters and investors, site visits and bookings. If you sell software, there are better tools for that."],
  ["How do I add my projects?", "Create a project, then add a tower: tell us the floors and how many flats on each floor, and we draw the building. You can then change any flat's size, price or status in one tap."],
  ["How does the 3-day free trial work?", "Create a workspace and everything is unlocked for 3 days — no credit card needed. We'll remind you before it ends, and you choose a plan when you're ready."],
  ["What happens to my data if the trial ends?", "Nothing is deleted. Your workspace becomes restricted: you can still sign in, view billing, upgrade and export all of your data."],
  ["Can I import my leads from 99acres, MagicBricks or Housing.com?", "Yes. Export the enquiries as a CSV, map the columns, fix any errors in the preview and import. Duplicate detection helps you keep things clean."],
  ["Is my brokerage's data isolated from other customers?", "Every workspace is isolated at the API and database level (Postgres row-level security), and the AI assistant can only ever read your own workspace."],
  ["Do you support Indian payments and GST invoices?", "Yes — plans are priced in INR, and billing works with Razorpay as well as Stripe. Invoices include GST."],
];
export function FAQ() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <Section id="faq" eyebrow="FAQ" title="Questions, answered">
      <div className="mx-auto max-w-3xl divide-y divide-border rounded-xl border border-border bg-surface">
        {FAQS.map(([q, a], i) => (
          <div key={q}>
            <h3><button className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left font-medium hover:bg-surface-hover" aria-expanded={open === i} onClick={() => setOpen(open === i ? null : i)}>{q}{open === i ? <Minus className="size-4 shrink-0 text-fg-subtle" /> : <Plus className="size-4 shrink-0 text-fg-subtle" />}</button></h3>
            <AnimatePresence initial={false}>{open === i && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden"><p className="px-5 pb-5 text-[15px] text-fg-muted">{a}</p></motion.div>}</AnimatePresence>
          </div>
        ))}
      </div>
    </Section>
  );
}

export function FinalCTA() {
  return (
    <section className="py-20 sm:py-28">
      <Container>
        <Reveal>
          <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#4f46e5] to-[#7c3aed] px-6 py-16 text-center text-white sm:px-16">
            <div className="pointer-events-none absolute inset-0 opacity-30" style={{ background: "radial-gradient(500px 220px at 20% 0%, white, transparent), radial-gradient(400px 200px at 90% 100%, #c4b5fd, transparent)" }} aria-hidden />
            <h2 className="relative text-balance text-3xl font-semibold tracking-tight sm:text-5xl">See your first tower in two minutes</h2>
            <p className="relative mx-auto mt-4 max-w-xl text-lg text-white/80">Add a project, tell us its floors and flats, and watch the building appear. 3-day free trial.</p>
            <div className="relative mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button asChild size="lg" className="bg-white text-[#4f46e5] hover:bg-white/90"><Link href="/signup">Start Free Trial <ArrowRight /></Link></Button>
            </div>
            <p className="relative mt-4 text-sm text-white/70">No credit card • No long-term commitment</p>
          </div>
        </Reveal>
      </Container>
    </section>
  );
}

export function Footer() {
  const cols: [string, [string, string][]][] = [["Product", [["Building view", "#product"], ["Features", "#features"], ["AI assistant", "#ai"], ["Automation", "#automation"], ["Pricing", "#pricing"]]], ["Company", [["Sign in", "/login"], ["Start free trial", "/signup"], ["FAQ", "#faq"]]]];
  return (
    <footer className="border-t border-border py-12">
      <Container className="grid gap-10 md:grid-cols-[1.5fr_1fr_1fr]">
        <div><Logo /><p className="mt-3 max-w-xs text-sm text-fg-muted">The simple CRM for realtors. See every flat at a glance.</p></div>
        {cols.map(([t, ls]) => <div key={t}><p className="mb-3 text-sm font-semibold">{t}</p><ul className="space-y-2">{ls.map(([l, h]) => <li key={l}><a href={h} className="text-sm text-fg-muted hover:text-fg">{l}</a></li>)}</ul></div>)}
      </Container>
      <Container className="mt-10 text-xs text-fg-subtle">© {new Date().getFullYear()} CRM Wala. All rights reserved.</Container>
    </footer>
  );
}
