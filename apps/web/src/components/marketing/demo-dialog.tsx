"use client";
import { AnimatePresence, motion } from "framer-motion";
import { Pause, Play } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Dialog, DialogContent, Progress } from "@crm/ui";
import { BuildingHero } from "./building-preview";
import { FlowDiagram } from "./sections-b";

const STEPS = [
  { title: "See the whole building", body: "Every flat is a window, coloured by its status. Vacant, listed, held, booked, sold or rented — you see it before you read a word.", node: <BuildingHero /> },
  { title: "Automate the busywork", body: "When an enquiry arrives, assign it, send the brochure and create the call task — all without lifting a finger.", node: <div className="rounded-2xl border border-border bg-surface p-6"><FlowDiagram /></div> },
];

/** Auto-playing guided tour (no video asset needed). */
export function DemoDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [p, setP] = useState(0);
  useEffect(() => { if (open) { setI(0); setP(0); setPlaying(true); } }, [open]);
  useEffect(() => {
    if (!open || !playing) return;
    const t = setInterval(() => setP((v) => { if (v >= 100) { setI((x) => (x + 1) % STEPS.length); return 0; } return v + 2; }), 120);
    return () => clearInterval(t);
  }, [open, playing]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="xl" title="See CRM Wala in 30 seconds" description="A quick guided tour of the product.">
        <AnimatePresence mode="wait">
          <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
            {STEPS[i].node}
            <div className="mt-5"><h3 className="text-lg font-semibold">{STEPS[i].title}</h3><p className="mt-1 text-sm text-fg-muted">{STEPS[i].body}</p></div>
          </motion.div>
        </AnimatePresence>
        <div className="mt-5 flex items-center gap-3">
          <Button variant="ghost" size="icon-sm" onClick={() => setPlaying((v) => !v)} aria-label={playing ? "Pause tour" : "Play tour"}>{playing ? <Pause /> : <Play />}</Button>
          <div className="flex flex-1 gap-1.5">{STEPS.map((_, k) => <button key={k} aria-label={`Step ${k + 1}`} onClick={() => { setI(k); setP(0); }} className="flex-1"><Progress value={k < i ? 100 : k === i ? p : 0} /></button>)}</div>
          <Button asChild><Link href="/signup">Start free trial</Link></Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
