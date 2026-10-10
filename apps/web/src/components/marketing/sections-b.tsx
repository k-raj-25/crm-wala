"use client";
import { motion, useInView } from "framer-motion";
import { Bell, Brain, CheckSquare, ChevronRight, Clock, Mail, Send, Sparkles, UserPlus, Zap, TrendingDown, AlertTriangle, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AreaTrend, BarsChart, Card, FunnelBars, Avatar, cn, formatMoneyCompact } from "@crm/ui";
import { Container, Reveal, Section, Window } from "./primitives";

const CHAT = [
  { q: "Which 3 BHK flats under ₹2.5 Cr are free in Victory Valley?", a: "**4 flats** match:\n• Tower D-13 · 804 · 3 BHK · ₹2.41Cr · for sale\n• Tower D-13 · 403 · 3 BHK · ₹2.38Cr · vacant\n• Tower D-12 · 1102 · 3 BHK · ₹2.45Cr · for sale\nWant me to find clients who would like them?" },
  { q: "Which leads haven't been contacted in 7 days?", a: "**9 open leads** are going cold. Highest scoring: Rohan Bose (84, buying a 4 BHK), Lakshmi Pillai (79), Gautam Bhatt (76). Want me to draft follow-ups?" },
];
function Typed({ text, run }: { text: string; run: boolean }) {
  const [n, setN] = useState(0);
  useEffect(() => { setN(0); if (!run) return; const t = setInterval(() => setN((v) => (v >= text.length ? v : v + 3)), 16); return () => clearInterval(t); }, [text, run]);
  return <span className="whitespace-pre-line">{text.slice(0, n).split(/(\*\*[^*]+\*\*)/g).map((p, i) => p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p)}</span>;
}

export function AISection() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-120px" });
  const [i, setI] = useState(0);
  useEffect(() => { if (!inView) return; const t = setInterval(() => setI((v) => (v + 1) % CHAT.length), 7000); return () => clearInterval(t); }, [inView]);
  const items = [[Brain, "Lead scoring & deal probability", "Explainable scores that tell you why a lead is hot."], [Mail, "Messages in your voice", "Draft a follow-up or a brochure email for any lead in one click."], [Sparkles, "Next-best-action", "A daily short-list of exactly what to do next."], [TrendingDown, "Cold-lead alerts", "Spot enquiries and clients going quiet before they go elsewhere."], [Copy, "Duplicate & cleanup suggestions", "Keep your data tidy automatically."]] as const;
  return (
    <Section id="ai" eyebrow="AI assistant" title="Ask your CRM anything" subtitle="The assistant answers from your own inventory and pipeline — respecting your permissions and never touching another brokerage's data.">
      <div ref={ref} className="grid items-center gap-10 lg:grid-cols-2">
        <Reveal><ul className="space-y-5">{items.map(([I, t, b]) => <li key={t} className="flex gap-4"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary"><I className="size-5" /></span><div><p className="font-semibold">{t}</p><p className="text-[15px] text-fg-muted">{b}</p></div></li>)}</ul></Reveal>
        <Reveal delay={0.1}>
          <Window title="AI Assistant">
            <div className="min-h-[300px] space-y-4 bg-bg p-5" aria-live="polite">
              <div key={i} className="space-y-4">
                <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-fg">{CHAT[i].q}</motion.div>
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }} className="flex gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary"><Sparkles className="size-4" /></span>
                  <div className="max-w-[88%] rounded-2xl rounded-tl-md border border-border bg-surface px-4 py-3 text-sm leading-relaxed"><Typed text={CHAT[i].a} run={inView} /></div>
                </motion.div>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-fg-subtle"><span className="flex-1">Ask about flats, leads, visits…</span><Send className="size-4" /></div>
            </div>
          </Window>
        </Reveal>
      </div>
    </Section>
  );
}

const FLOW = [
  { icon: Zap, label: "When", title: "New enquiry arrives", tone: "var(--series-1)" },
  { icon: UserPlus, label: "Then", title: "Assign to an agent", tone: "var(--series-3)" },
  { icon: Mail, label: "Then", title: "Send the brochure", tone: "var(--series-2)" },
  { icon: CheckSquare, label: "Then", title: "Create a call task", tone: "var(--series-7)" },
  { icon: Clock, label: "Then", title: "Wait 2 days", tone: "var(--series-4)" },
  { icon: Bell, label: "Then", title: "Remind the agent", tone: "var(--series-5)" },
];
export function FlowDiagram() {
  const [active, setActive] = useState(0);
  useEffect(() => { const t = setInterval(() => setActive((a) => (a + 1) % (FLOW.length + 1)), 1100); return () => clearInterval(t); }, []);
  return (
    <ol className="flex flex-col items-stretch gap-0 md:flex-row md:items-center md:justify-between" aria-label="Example automation">
      {FLOW.map((n, i) => (
        <li key={n.title} className="flex flex-col items-center md:flex-1 md:flex-row">
          <motion.div animate={{ scale: active === i ? 1.04 : 1, boxShadow: active === i ? "0 8px 24px rgba(79,70,229,.2)" : "0 1px 2px rgba(0,0,0,.05)" }} className={cn("w-full rounded-xl border bg-surface p-3.5 text-left transition-colors md:w-auto md:min-w-[118px]", active === i ? "border-primary" : "border-border")}>
            <span className="mb-2 flex size-8 items-center justify-center rounded-lg" style={{ background: `color-mix(in srgb, ${n.tone} 15%, transparent)`, color: n.tone }}><n.icon className="size-4" /></span>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">{n.label}</p><p className="text-[13px] font-semibold leading-tight">{n.title}</p>
          </motion.div>
          {i < FLOW.length - 1 && (
            <div className="relative my-1 h-6 w-px bg-border md:mx-1 md:my-0 md:h-px md:w-5 md:flex-1">
              <motion.span className="absolute left-1/2 top-0 size-1.5 -translate-x-1/2 rounded-full bg-primary md:left-0 md:top-1/2 md:-translate-y-1/2 md:translate-x-0" animate={active === i ? { opacity: [0, 1, 0], y: [0, 24] } : { opacity: 0 }} transition={{ duration: 0.9 }} />
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

export function AutomationSection() {
  return (
    <Section id="automation" tone="subtle" eyebrow="Automation" title="Set it once. Let it run." subtitle="Build workflows visually. When an enquiry arrives → assign an agent → send the brochure → create a call task → wait → remind.">
      <Reveal><Card className="mx-auto max-w-5xl overflow-hidden p-6 sm:p-8"><FlowDiagram />
        <div className="mt-8 grid gap-3 border-t border-border pt-6 text-sm sm:grid-cols-3">
          {[["Triggers", "Enquiry created · Deal stage changed · Task completed · Form submitted"], ["Actions", "Send email · Create task · Assign user · Add tag · Change status · Webhook"], ["Safe by design", "Dry-run test mode, run history and loop protection built in"]].map(([t, b]) => <div key={t}><p className="font-semibold">{t}</p><p className="mt-1 text-fg-muted">{b}</p></div>)}
        </div>
      </Card></Reveal>
    </Section>
  );
}

const REV = Array.from({ length: 12 }, (_, i) => ({ m: ["Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"][i], revenue: [4, 6, 5.2, 8, 7.4, 10, 9.6, 12.5, 12, 15, 14.2, 18.5][i] * 100000 }));
export function AnalyticsSection() {
  return (
    <Section id="analytics" eyebrow="Analytics" title="Know exactly what sales are coming" subtitle="Live dashboards and a forecast you can trust — hover any chart for exact values.">
      <div className="grid gap-4 lg:grid-cols-3">
        <Reveal className="lg:col-span-2"><Card className="p-5"><p className="font-semibold">Sales over time</p><p className="mb-3 text-sm text-fg-muted">Deals closed, last 12 months</p><AreaTrend data={REV} xKey="m" series={[{ key: "revenue", label: "Sales" }]} format={(v) => formatMoneyCompact(v)} height={250} /></Card></Reveal>
        <Reveal delay={0.08}><Card className="h-full p-5"><p className="font-semibold">Deal funnel</p><p className="mb-4 text-sm text-fg-muted">Deals reaching each stage</p><FunnelBars steps={[{ label: "Enquiry", value: 64 }, { label: "Site visit", value: 41 }, { label: "Shortlisted", value: 27 }, { label: "Negotiation", value: 15 }, { label: "Closed", value: 9 }]} /></Card></Reveal>
        <Reveal delay={0.12} className="lg:col-span-3"><Card className="p-5"><p className="font-semibold">Sales forecast</p><p className="mb-3 text-sm text-fg-muted">Commit vs weighted vs best case</p>
          <BarsChart data={[{ m: "Nov", commit: 52, weighted: 60, best: 88 }, { m: "Dec", commit: 0, weighted: 37, best: 84 }, { m: "Jan", commit: 0, weighted: 22, best: 61 }, { m: "Feb", commit: 0, weighted: 12, best: 40 }].map((r) => ({ m: r.m, commit: r.commit * 1e5, weighted: r.weighted * 1e5, best: r.best * 1e5 }))} xKey="m" series={[{ key: "commit", label: "Commit" }, { key: "weighted", label: "Weighted" }, { key: "best", label: "Best case" }]} format={(v) => formatMoneyCompact(v)} height={220} /></Card></Reveal>
      </div>
    </Section>
  );
}
export { AlertTriangle, ChevronRight, Avatar, Container };
