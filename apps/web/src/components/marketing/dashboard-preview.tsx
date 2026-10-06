"use client";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { CheckCircle2, Flame, Home, Kanban, ListChecks, Sparkles, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Avatar, cn } from "@crm/ui";
import { CountUp, Window } from "./primitives";

const REV = [18, 24, 21, 30, 28, 36, 33, 44, 41, 52, 49, 63];
function Area() {
  const w = 300, h = 90;
  const pts = REV.map((v, i) => [(i / (REV.length - 1)) * w, h - (v / 70) * h]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-full w-full" preserveAspectRatio="none" aria-hidden>
      <defs><linearGradient id="pv" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--series-1)" stopOpacity=".3" /><stop offset="1" stopColor="var(--series-1)" stopOpacity="0" /></linearGradient></defs>
      <motion.path d={`${line} L${w},${h} L0,${h} Z`} fill="url(#pv)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8, duration: 0.8 }} />
      <motion.path d={line} fill="none" stroke="var(--series-1)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.4, ease: "easeOut" }} />
    </svg>
  );
}

type Card = { id: string; name: string; value: string; who: string };
const COLS = ["Qualified", "Proposal", "Negotiation", "Won"];
const INITIAL: Record<string, Card[]> = {
  Qualified: [{ id: "a", name: "Orbit — Compliance", value: "₹12L", who: "Priya S." }, { id: "b", name: "Lumen — Admissions", value: "₹4.5L", who: "Rohit V." }],
  Proposal: [{ id: "c", name: "Vertex — Outreach", value: "₹31L", who: "Aarav M." }],
  Negotiation: [{ id: "d", name: "Zenith — Fleet CRM", value: "₹18.5L", who: "Aarav M." }],
  Won: [],
};

function MiniBoard() {
  const [cols, setCols] = useState(INITIAL);
  const [won, setWon] = useState(false);
  useEffect(() => {
    const seq = [["Negotiation", "Won", "d"], ["Proposal", "Negotiation", "c"], ["Qualified", "Proposal", "a"]] as const;
    let i = 0;
    const t = setInterval(() => {
      const [from, to, id] = seq[i % seq.length];
      if (i % seq.length === 0 && i > 0) { setCols(INITIAL); setWon(false); i++; return; }
      setCols((c) => { const card = c[from].find((x) => x.id === id); if (!card) return c; return { ...c, [from]: c[from].filter((x) => x.id !== id), [to]: [...c[to], card] }; });
      if (to === "Won") { setWon(true); setTimeout(() => setWon(false), 2200); }
      i++;
    }, 2600);
    return () => clearInterval(t);
  }, []);
  return (
    <LayoutGroup>
      <div className="relative grid grid-cols-4 gap-2">
        {COLS.map((c) => (
          <div key={c} className="min-h-[132px] rounded-lg bg-bg-subtle/70 p-1.5">
            <p className="mb-1.5 flex items-center justify-between px-1 text-[10px] font-semibold uppercase tracking-wide text-fg-subtle"><span>{c}</span><span>{cols[c].length}</span></p>
            <div className="space-y-1.5">
              {cols[c].map((d) => (
                <motion.div layout layoutId={d.id} key={d.id} transition={{ type: "spring", stiffness: 420, damping: 34 }} className={cn("rounded-md border bg-surface p-2 shadow-xs", c === "Won" ? "border-success/40" : "border-border")}>
                  <p className="truncate text-[11px] font-medium">{d.name}</p>
                  <div className="mt-1.5 flex items-center justify-between"><span className="tabular text-[11px] font-semibold text-primary">{d.value}</span><Avatar name={d.who} size={16} /></div>
                </motion.div>
              ))}
            </div>
          </div>
        ))}
        <AnimatePresence>
          {won && (
            <motion.div initial={{ opacity: 0, y: 10, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6 }} className="absolute -top-3 right-0 flex items-center gap-1.5 rounded-full bg-success px-3 py-1 text-[11px] font-semibold text-white shadow-lg">
              <CheckCircle2 className="size-3.5" /> Deal won · ₹18.5L 🎉
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </LayoutGroup>
  );
}

export function DashboardPreview({ className }: { className?: string }) {
  const kpis = [
    { label: "Revenue", node: <CountUp to={16.9} prefix="₹" suffix="L" decimals={1} />, delta: "+172%", tone: "text-success" },
    { label: "Pipeline", node: <CountUp to={2.56} prefix="₹" suffix="Cr" decimals={2} />, delta: "15 deals", tone: "text-fg-subtle" },
    { label: "Win rate", node: <CountUp to={75} suffix="%" />, delta: "+8.3 pts", tone: "text-success" },
  ];
  return (
    <Window className={className}>
      <div className="grid grid-cols-[52px_1fr] bg-bg sm:grid-cols-[168px_1fr]">
        <aside className="hidden flex-col gap-1 border-r border-border bg-surface p-3 sm:flex">
          {[[Home, "Home", true], [Users, "Leads"], [Kanban, "Pipeline"], [ListChecks, "Tasks"], [Sparkles, "AI Assistant"]].map(([Icon, label, active]) => {
            const I = Icon as typeof Home;
            return <div key={label as string} className={cn("flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs font-medium", active ? "bg-primary-soft text-primary" : "text-fg-muted")}><I className="size-3.5" />{label as string}</div>;
          })}
        </aside>
        <aside className="flex flex-col items-center gap-3 border-r border-border bg-surface py-3 sm:hidden">{[Home, Users, Kanban, ListChecks].map((I, i) => <I key={i} className={cn("size-4", i === 0 ? "text-primary" : "text-fg-subtle")} />)}</aside>
        <div className="min-w-0 space-y-3 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div><p className="text-sm font-semibold">Good morning, Aarav 👋</p><p className="text-[11px] text-fg-muted">Here's what needs your attention today</p></div>
            <span className="hidden rounded-full bg-warning-soft px-2.5 py-1 text-[11px] font-medium text-warning sm:block">Trial ends in 2 days</span>
          </div>
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="rounded-xl border border-primary/20 bg-gradient-to-br from-primary-soft to-surface p-3">
            <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-primary"><Flame className="size-3.5" /> Today's focus</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[["5", "follow-ups"], ["2", "meetings"], ["3", "deals need attention"], ["1", "overdue task"]].map(([n, l], i) => (
                <motion.div key={l} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.35 + i * 0.08 }} className="rounded-lg bg-surface/80 px-2.5 py-2 shadow-xs"><p className="tabular text-lg font-semibold leading-none">{n}</p><p className="mt-1 text-[10px] text-fg-muted">{l}</p></motion.div>
              ))}
            </div>
          </motion.div>
          <div className="grid grid-cols-3 gap-2">
            {kpis.map((k, i) => (
              <motion.div key={k.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 + i * 0.08 }} className="rounded-xl border border-border bg-surface p-2.5 sm:p-3">
                <p className="text-[10px] text-fg-muted sm:text-[11px]">{k.label}</p><p className="mt-0.5 text-base font-semibold sm:text-xl">{k.node}</p><p className={cn("text-[10px]", k.tone)}>{k.delta}</p>
              </motion.div>
            ))}
          </div>
          <div className="grid gap-2 md:grid-cols-[1fr_1.35fr]">
            <div className="rounded-xl border border-border bg-surface p-3"><p className="mb-1 text-[11px] font-medium">Revenue over time</p><div className="h-[110px]"><Area /></div></div>
            <div className="rounded-xl border border-border bg-surface p-3"><p className="mb-2 text-[11px] font-medium">Sales pipeline</p><MiniBoard /></div>
          </div>
        </div>
      </div>
    </Window>
  );
}
