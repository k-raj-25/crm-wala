"use client";
import { motion } from "framer-motion";
import { Check, Eye, EyeOff, ShieldCheck } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Button, Input, Logo, ThemeToggle, cn } from "@crm/ui";
import { BuildingHero } from "../marketing/building-preview";

export function AuthShell({ title, subtitle, children, footer, wide }: { title: string; subtitle?: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode; wide?: boolean }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="flex flex-col px-5 py-6 sm:px-10">
        <div className="flex items-center justify-between"><Link href="/" aria-label="Home"><Logo /></Link><ThemeToggle /></div>
        <div className="mx-auto flex w-full flex-1 flex-col justify-center py-10" style={{ maxWidth: wide ? 520 : 400 }}>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
            <h1 className="text-[28px] font-semibold tracking-tight">{title}</h1>
            {subtitle && <p className="mt-2 text-[15px] text-fg-muted">{subtitle}</p>}
            <div className="mt-8">{children}</div>
            {footer && <div className="mt-6 text-center text-sm text-fg-muted">{footer}</div>}
          </motion.div>
        </div>
        <p className="flex items-center justify-center gap-1.5 text-xs text-fg-subtle"><ShieldCheck className="size-3.5" /> Encrypted connection · Your data is isolated to your workspace</p>
      </div>
      <aside className="relative hidden overflow-hidden bg-gradient-to-br from-[#312e81] via-[#4338ca] to-[#6d28d9] p-12 lg:flex lg:flex-col lg:justify-center" aria-hidden>
        <div className="pointer-events-none absolute inset-0 opacity-40" style={{ background: "radial-gradient(600px 300px at 10% 0%, rgba(255,255,255,.35), transparent), radial-gradient(500px 300px at 100% 100%, rgba(167,139,250,.5), transparent)" }} />
        <div className="relative">
          <h2 className="max-w-md text-balance text-3xl font-semibold tracking-tight text-white">See every flat you sell — and know exactly what to do next.</h2>
          <ul className="mt-5 space-y-2 text-white/80">{["Every tower, floor and flat in one picture", "Hold flats for clients with a countdown", "3-day free trial, no card required"].map((t) => <li key={t} className="flex items-center gap-2"><Check className="size-4 text-emerald-300" />{t}</li>)}</ul>
          <div className="pointer-events-none mt-10 w-[135%] origin-top-left scale-[0.78] opacity-95"><BuildingHero /></div>
        </div>
      </aside>
    </div>
  );
}

export const PasswordInput = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>((props, ref) => {
  const [show, setShow] = React.useState(false);
  return (
    <div className="relative">
      <Input ref={ref} {...props} type={show ? "text" : "password"} className="pr-10" />
      <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-fg-subtle hover:text-fg">{show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
    </div>
  );
});
PasswordInput.displayName = "PasswordInput";

export function passwordScore(pw: string) {
  let s = 0;
  if (pw.length >= 10) s++; if (pw.length >= 14) s++; if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++; if (/\d/.test(pw)) s++; if (/[^A-Za-z0-9]/.test(pw)) s++;
  return Math.min(s, 4);
}
export function StrengthMeter({ value }: { value: string }) {
  const s = value ? passwordScore(value) : 0;
  const labels = ["Too short", "Weak", "Okay", "Good", "Strong"];
  const colors = ["bg-border", "bg-danger", "bg-warning", "bg-success", "bg-success"];
  return (
    <div className="mt-2" aria-live="polite">
      <div className="flex gap-1">{[0, 1, 2, 3].map((i) => <span key={i} className={cn("h-1 flex-1 rounded-full transition-colors", i < s ? colors[s] : "bg-border")} />)}</div>
      {value && <p className="mt-1 text-xs text-fg-subtle">{labels[s]} · use 10+ characters with letters and numbers</p>}
    </div>
  );
}

export function GoogleButton({ label = "Continue with Google" }: { label?: string }) {
  return (
    <Button asChild variant="secondary" size="lg" className="w-full">
      <a href="/api/v1/auth/google/start">
        <svg viewBox="0 0 24 24" className="!size-[18px]" aria-hidden><path fill="#4285F4" d="M22.5 12.2c0-.8-.1-1.5-.2-2.2H12v4.3h5.9a5 5 0 0 1-2.2 3.3v2.7h3.5c2.1-1.9 3.3-4.7 3.3-8.1z" /><path fill="#34A853" d="M12 23c3 0 5.4-1 7.2-2.7l-3.5-2.7c-1 .7-2.2 1-3.7 1-2.8 0-5.2-1.9-6-4.5H2.4v2.8A11 11 0 0 0 12 23z" /><path fill="#FBBC05" d="M6 14.1a6.6 6.6 0 0 1 0-4.2V7.1H2.4a11 11 0 0 0 0 9.8L6 14.1z" /><path fill="#EA4335" d="M12 5.4c1.6 0 3 .6 4.2 1.6l3.1-3.1A11 11 0 0 0 2.4 7.1L6 9.9c.8-2.6 3.2-4.5 6-4.5z" /></svg>
        {label}
      </a>
    </Button>
  );
}

export function OrDivider() {
  return <div className="my-5 flex items-center gap-3 text-xs text-fg-subtle"><span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" /></div>;
}
