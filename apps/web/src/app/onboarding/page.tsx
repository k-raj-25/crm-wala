"use client";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, BarChart3, Briefcase, Building, Check, CircleDollarSign, FileSpreadsheet, Handshake, Home, Layers, Mail, PlugZap, Rocket, Repeat, Sparkles, User, Users, UsersRound, Wrench, Zap, Target, Globe } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Field, Input, Logo, NativeSelect, Progress, ThemeToggle, cn, humanDuration, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { INDUSTRIES } from "@/lib/constants";
import { keys, useMe } from "@/lib/queries";
import type { Me } from "@/lib/types";

const MODELS = [["agent", "Independent agent", User], ["brokerage", "Brokerage / agency", Building], ["channel_partner", "Channel partner", Handshake], ["developer", "Developer sales team", Layers], ["property_manager", "Rentals & property management", Home], ["real_estate", "Something else in real estate", Sparkles]] as const;
const SIZES = [["1", "Just me"], ["2-5", "2–5"], ["6-10", "6–10"], ["11-25", "11–25"], ["26-50", "26–50"], ["51-200", "51–200"], ["201+", "200+"]] as const;
const GOALS = [["manage_leads", "Keep track of enquiries", "Every buyer and renter, with their budget and follow-ups", Users], ["track_inventory", "Know what's available", "See every flat — vacant, held, sold or rented — at a glance", Home], ["track_deals", "Track deals", "A visual pipeline from enquiry to closed", Target], ["automate_followups", "Never miss a follow-up", "Reminders and auto-assignment for new enquiries", Repeat], ["analyze_revenue", "See what's selling", "Sales, pipeline and team reports", BarChart3]] as const;
const IMPORTS = [["project", "Add my first project", "Draw a tower and see its flats straight away", Building], ["csv", "Import leads from a CSV", "From 99acres, MagicBricks, Housing.com or a spreadsheet", FileSpreadsheet], ["scratch", "Start from scratch", "Begin with a clean workspace", Rocket], ["integrations", "Connect Gmail & calendar", "Send email and sync visits", PlugZap]] as const;
const STEPS = ["Business", "What you do", "Team size", "Goals", "First step"];

function Choice({ selected, onClick, icon: Icon, title, description, multi }: { selected: boolean; onClick: () => void; icon: React.ElementType; title: string; description?: string; multi?: boolean }) {
  return (
    <motion.button type="button" whileTap={{ scale: 0.98 }} onClick={onClick} aria-pressed={selected}
      className={cn("relative flex items-start gap-3.5 rounded-xl border bg-surface p-4 text-left transition-all", selected ? "border-primary bg-primary-soft/50 shadow-sm ring-1 ring-primary" : "border-border hover:border-border-strong hover:shadow-sm")}>
      <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-lg", selected ? "bg-primary text-primary-fg" : "bg-bg-subtle text-fg-muted")}><Icon className="size-5" /></span>
      <span className="min-w-0"><span className="block font-semibold">{title}</span>{description && <span className="mt-0.5 block text-[13px] text-fg-muted">{description}</span>}</span>
      {selected && <span className={cn("absolute right-3 top-3 flex size-5 items-center justify-center bg-primary text-primary-fg", multi ? "rounded-md" : "rounded-full")}><Check className="size-3" strokeWidth={3} /></span>}
    </motion.button>
  );
}

export default function Onboarding() {
  const router = useRouter(); const qc = useQueryClient(); const toast = useToast();
  const { data: me, isLoading, isError } = useMe();
  const [step, setStep] = useState(0); const [dir, setDir] = useState(1); const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ company_name: "", website: "", industry: "", sales_model: "", company_size: "", goals: [] as string[], import_choice: "" });

  useEffect(() => { if (isError) router.replace("/login?next=/onboarding"); }, [isError, router]);
  useEffect(() => {
    if (!me?.workspace) return;
    const w = me.workspace;
    setF((p) => ({ ...p, company_name: w.name, website: w.website ?? "", industry: w.industry ?? "", sales_model: w.sales_model ?? "", company_size: w.company_size ?? "", goals: w.goals ?? [] }));
  }, [me?.workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const valid = [!!f.company_name.trim(), !!f.sales_model, !!f.company_size, f.goals.length > 0, !!f.import_choice][step];
  const go = (d: number) => { setDir(d); setStep((s) => Math.max(0, Math.min(STEPS.length - 1, s + d))); };
  const trialLeft = me?.subscription?.access.seconds_left;

  const finish = async () => {
    setBusy(true);
    try {
      const w = await api.post<Me["workspace"]>("/api/v1/workspace/onboarding", { ...f, complete: true, website: f.website || undefined, industry: f.industry || undefined });
      qc.setQueryData<Me>(keys.me, (m) => (m ? { ...m, workspace: w } : m));
      const dest = { project: "/app/projects?new=1", scratch: "/app", csv: "/app/settings/data?import=leads", integrations: "/app/integrations" }[f.import_choice] ?? "/app";
      toast.success("Your workspace is ready", "Let's fill your first building.");
      router.replace(dest);
    } catch (e) { toast.error("Couldn't save", (e as Error).message); setBusy(false); }
  };
  if (isLoading || !me) return <div className="flex min-h-dvh items-center justify-center"><div className="skeleton h-8 w-48" /></div>;

  const panels = [
    <div key="0" className="space-y-5"><Field label="Agency or company name" required><Input value={f.company_name} onChange={(e) => setF({ ...f, company_name: e.target.value })} autoFocus /></Field>
      <Field label="Website" hint="Optional"><Input icon={<Globe />} value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} placeholder="https://youragency.com" /></Field>
      <Field label="You are a…"><NativeSelect value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })}><option value="">Select…</option>{INDUSTRIES.map((i) => <option key={i}>{i}</option>)}</NativeSelect></Field></div>,
    <div key="1" className="grid gap-3 sm:grid-cols-2">{MODELS.map(([k, l, I]) => <Choice key={k} selected={f.sales_model === k} onClick={() => setF({ ...f, sales_model: k })} icon={I} title={l} />)}</div>,
    <div key="2" className="grid grid-cols-2 gap-3 sm:grid-cols-3">{SIZES.map(([k, l]) => <Choice key={k} selected={f.company_size === k} onClick={() => setF({ ...f, company_size: k })} icon={k === "1" ? User : UsersRound} title={l} description={k === "1" ? "Solo" : "people"} />)}</div>,
    <div key="3" className="grid gap-3 sm:grid-cols-2">{GOALS.map(([k, l, d, I]) => <Choice multi key={k} selected={f.goals.includes(k)} onClick={() => setF({ ...f, goals: f.goals.includes(k) ? f.goals.filter((x) => x !== k) : [...f.goals, k] })} icon={I} title={l} description={d} />)}</div>,
    <div key="4" className="grid gap-3 sm:grid-cols-2">{IMPORTS.map(([k, l, d, I]) => <Choice key={k} selected={f.import_choice === k} onClick={() => setF({ ...f, import_choice: k })} icon={I} title={l} description={d} />)}</div>,
  ];
  const titles = [["Tell us about your agency", "This helps us tailor your workspace."], ["What do you do?", "Pick the one that fits best."], ["How large is your team?", "We'll set sensible defaults."], ["What do you want to accomplish?", "Choose all that apply."], ["Where would you like to start?", "You can always do the others later."]];

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between px-5 py-4 sm:px-10"><Logo /><div className="flex items-center gap-3">{trialLeft ? <span className="hidden rounded-full bg-primary-soft px-3 py-1 text-xs font-medium text-primary sm:block">Your free trial has started · {humanDuration(trialLeft)} left</span> : null}<ThemeToggle /></div></header>
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-5 pb-10 pt-4 sm:pt-10">
        <div className="mb-8">
          <div className="mb-3 flex items-center justify-between text-sm"><span className="font-medium text-fg-muted">Step {step + 1} of {STEPS.length} · {STEPS[step]}</span><span className="text-fg-subtle">{Math.round(((step + 1) / STEPS.length) * 100)}%</span></div>
          <Progress value={step + 1} max={STEPS.length} label="Onboarding progress" />
        </div>
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div key={step} custom={dir} initial={{ opacity: 0, x: dir * 28 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: dir * -28 }} transition={{ duration: 0.22 }}>
            <h1 className="text-balance text-[28px] font-semibold tracking-tight">{titles[step][0]}</h1>
            <p className="mb-7 mt-1.5 text-fg-muted">{titles[step][1]}</p>
            {panels[step]}
          </motion.div>
        </AnimatePresence>
        <div className="mt-auto flex items-center justify-between pt-10">
          <Button variant="ghost" onClick={() => go(-1)} disabled={step === 0 || busy}><ArrowLeft /> Back</Button>
          {step < STEPS.length - 1 ? <Button size="lg" onClick={() => go(1)} disabled={!valid}>Continue <ArrowRight /></Button> : <Button size="lg" onClick={finish} disabled={!valid} loading={busy}>Finish setup <Rocket /></Button>}
        </div>
      </main>
    </div>
  );
}
