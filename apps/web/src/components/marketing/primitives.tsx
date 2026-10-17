"use client";
import { animate, motion, useInView, useMotionValue, useTransform } from "framer-motion";
import { useEffect, useRef } from "react";
import { cn } from "@crm/ui";

export const Container = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("mx-auto w-full max-w-6xl px-5 sm:px-8", className)} {...p} />;

/** `display` is a big faint word set behind the heading, the way the glass reference writes "Pricing" behind its cards. */
export function Section({ id, index, eyebrow, title, subtitle, children, className, tone, display }: { id?: string; index?: string; eyebrow?: string; title: React.ReactNode; subtitle?: React.ReactNode; children?: React.ReactNode; className?: string; tone?: "subtle"; display?: string }) {
  return (
    <section id={id} className={cn("scroll-mt-20 py-20 sm:py-28", tone === "subtle" && "bg-gradient-to-b from-transparent via-bg-subtle to-transparent", className)}>
      <Container>
        <Reveal className="relative isolate mx-auto max-w-2xl text-center">
          {display && <span aria-hidden className="display-word absolute left-1/2 top-0 -z-10 -translate-x-1/2 -translate-y-[38%] text-[88px] sm:text-[176px]">{display}</span>}
          {eyebrow && <p className="mb-4 inline-flex items-center gap-2.5 text-[12px] font-medium text-fg-muted">{index && <span className="tabular font-semibold text-fg">{index}</span>}{index && <span className="h-px w-5 bg-border-strong" />}{eyebrow}</p>}
          <h2 className="text-balance text-3xl font-semibold tracking-[-0.02em] sm:text-[44px] sm:leading-[1.1]">{title}</h2>
          {subtitle && <p className="mx-auto mt-4 max-w-xl text-pretty text-[15px] leading-relaxed text-fg-muted sm:text-base">{subtitle}</p>}
        </Reveal>
        {children && <div className="mt-14">{children}</div>}
      </Container>
    </section>
  );
}

export function Reveal({ children, className, delay = 0, y = 18 }: { children: React.ReactNode; className?: string; delay?: number; y?: number }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.5, delay, ease: [0.16, 1, 0.3, 1] }}>
      {children}
    </motion.div>
  );
}

export function CountUp({ to, prefix = "", suffix = "", duration = 1.4, decimals = 0, format }: { to: number; prefix?: string; suffix?: string; duration?: number; decimals?: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => `${prefix}${format ? format(v) : v.toLocaleString("en-IN", { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}${suffix}`);
  useEffect(() => { if (inView) { const c = animate(mv, to, { duration, ease: "easeOut" }); return () => c.stop(); } }, [inView, to, duration, mv]);
  return <motion.span ref={ref} className="tabular">{text}</motion.span>;
}

/** Window chrome used for product mockups. */
export function Window({ children, className, title = "app.crmwala.com" }: { children: React.ReactNode; className?: string; title?: string }) {
  return (
    <div className={cn("glass overflow-hidden rounded-[18px] border border-border bg-surface shadow-lg", className)}>
      <div className="flex items-center gap-2 border-b border-border bg-surface-2 px-4 py-2.5">
        <span className="size-2.5 shrink-0 rounded-full bg-[#ff5f57]" /><span className="size-2.5 shrink-0 rounded-full bg-[#febc2e]" /><span className="size-2.5 shrink-0 rounded-full bg-[#28c840]" />
        <span className="mx-auto min-w-0 truncate rounded-full bg-bg-subtle px-4 py-1 text-[11px] text-fg-subtle sm:px-12">{title}</span><span className="hidden w-12 sm:block" />
      </div>
      {children}
    </div>
  );
}
