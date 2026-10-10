"use client";
import { motion } from "framer-motion";
import { ArrowRight, Play, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@crm/ui";
import { BuildingHero } from "./building-preview";
import { DemoDialog } from "./demo-dialog";
import { Container } from "./primitives";

export function Hero() {
  const [demo, setDemo] = useState(false);
  return (
    <section className="relative overflow-hidden pb-16 pt-32 sm:pb-24 sm:pt-40">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[620px]" aria-hidden
        style={{ background: "radial-gradient(60% 50% at 50% 0%, color-mix(in srgb, var(--primary) 16%, transparent), transparent 70%)" }} />
      <Container>
        <div className="mx-auto max-w-3xl text-center">
          <motion.a href="#ai" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-1.5 text-[13px] font-medium text-fg-muted shadow-xs transition-colors hover:text-fg">
            <Sparkles className="size-3.5 text-primary" /> Built only for real estate — no more bloated CRMs <ArrowRight className="size-3.5" />
          </motion.a>
          <motion.h1 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05, duration: 0.6 }} className="text-balance text-[40px] font-semibold leading-[1.05] tracking-tight sm:text-[64px]">
            See every flat you sell.{" "}
            <span className="bg-gradient-to-r from-primary to-[#9b5cff] bg-clip-text text-transparent">In one glance.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12, duration: 0.6 }} className="mx-auto mt-6 max-w-2xl text-pretty text-lg text-fg-muted sm:text-xl">
            The CRM for realtors who are tired of complicated CRMs. Look at the building, see what is vacant, held, sold or rented, and get on with the call. No filters, no spreadsheets.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.6 }} className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button asChild size="lg" className="w-full sm:w-auto"><Link href="/signup">Start Free Trial <ArrowRight /></Link></Button>
            <Button variant="secondary" size="lg" className="w-full sm:w-auto" onClick={() => setDemo(true)}><Play className="fill-current" /> Watch Demo</Button>
          </motion.div>
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }} className="mt-4 text-sm text-fg-subtle">3-day free trial <span className="mx-1.5">•</span> No long-term commitment</motion.p>
        </div>
        <motion.div initial={{ opacity: 0, y: 40, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ delay: 0.3, duration: 0.8, ease: [0.16, 1, 0.3, 1] }} className="relative mx-auto mt-14 max-w-5xl sm:mt-20">
          <div className="absolute -inset-x-6 -inset-y-4 -z-10 rounded-[2rem] bg-gradient-to-b from-primary/15 to-transparent blur-2xl" aria-hidden />
          <BuildingHero />
        </motion.div>
      </Container>
      <DemoDialog open={demo} onOpenChange={setDemo} />
    </section>
  );
}
