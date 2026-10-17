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
        style={{ background: "radial-gradient(42% 38% at 50% 0%, rgba(124, 108, 240, 0.22), transparent 70%), radial-gradient(20% 18% at 50% 6%, rgba(242, 200, 121, 0.10), transparent 70%)" }} />
      <Container>
        <div className="mx-auto max-w-3xl text-center">
          <motion.a href="#ai" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-7 inline-flex items-center gap-2 rounded-full border border-border bg-white/[0.03] px-3.5 py-1.5 text-[12px] font-medium text-fg-muted backdrop-blur transition-colors hover:border-border-strong hover:text-fg">
            <Sparkles className="accent size-3.5" /> Built only for real estate — no more bloated CRMs <ArrowRight className="size-3.5" />
          </motion.a>
          <motion.h1 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05, duration: 0.6 }} className="text-balance text-[40px] font-semibold leading-[1.04] tracking-[-0.035em] sm:text-[68px]">
            See every flat you sell.{" "}
            <span className="bg-gradient-to-r from-[#ece8ff] via-[#b6a8ff] to-[#f2c879] bg-clip-text text-transparent">In one glance.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12, duration: 0.6 }} className="mx-auto mt-6 max-w-xl text-pretty text-base leading-relaxed text-fg-muted sm:text-lg">
            The CRM for realtors who are tired of complicated CRMs. Look at the building, see what is vacant, held, sold or rented, and get on with the call. No filters, no spreadsheets.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.6 }} className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button asChild size="lg" className="w-full rounded-full sm:w-auto"><Link href="/signup">Start Free Trial <ArrowRight /></Link></Button>
            <Button variant="secondary" size="lg" className="w-full rounded-full bg-white/[0.03] sm:w-auto" onClick={() => setDemo(true)}><Play className="fill-current" /> Watch Demo</Button>
          </motion.div>
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }} className="mt-4 text-sm text-fg-subtle">3-day free trial <span className="mx-1.5">•</span> No long-term commitment</motion.p>
        </div>
        <motion.div initial={{ opacity: 0, y: 40, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ delay: 0.3, duration: 0.8, ease: [0.16, 1, 0.3, 1] }} className="relative mx-auto mt-14 max-w-5xl sm:mt-20">
          <div className="absolute -inset-x-10 -top-10 bottom-1/3 -z-10 rounded-[3rem] bg-[radial-gradient(60%_60%_at_50%_30%,rgba(91,63,209,0.35),transparent_70%)] blur-2xl" aria-hidden />
          <BuildingHero />
        </motion.div>
      </Container>
      <DemoDialog open={demo} onOpenChange={setDemo} />
    </section>
  );
}
