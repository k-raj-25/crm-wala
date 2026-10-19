"use client";
import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Logo, ThemeToggle, cn } from "@crm/ui";
import { Container } from "./primitives";

const LINKS = [["Building view", "#product"], ["Features", "#features"], ["AI", "#ai"], ["Automation", "#automation"], ["Pricing", "#pricing"], ["FAQ", "#faq"]];

export function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on(); window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className="fixed inset-x-0 top-3 z-40 px-3 sm:top-4">
      <div data-refract className={cn("glass mx-auto flex h-14 [--lg-blur:8] max-w-5xl items-center justify-between rounded-full border border-border pl-5 pr-2 transition-[background-color,box-shadow] duration-200", scrolled || open ? "bg-[var(--surface-pop)] shadow-lg" : "bg-[var(--nav-idle)] shadow-sm")}>
        <Link href="/" aria-label="CRM Wala home"><Logo /></Link>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {LINKS.map(([l, h]) => <a key={h} href={h} className="rounded-full px-3 py-1.5 text-[13px] font-medium text-fg-muted transition-colors hover:bg-surface-hover hover:text-fg">{l}</a>)}
        </nav>
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          <Button asChild variant="ghost" className="hidden sm:inline-flex"><Link href="/login">Sign in</Link></Button>
          <Button asChild className="hidden sm:inline-flex"><Link href="/signup">Start free trial</Link></Button>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>{open ? <X /> : <Menu />}</Button>
        </div>
      </div>
      {open && (
        <div className="glass-pop animate-fade-in mx-auto mt-2 max-w-5xl rounded-3xl border border-border shadow-lg md:hidden">
          <Container className="flex flex-col gap-1 py-4">
            {LINKS.map(([l, h]) => <a key={h} href={h} onClick={() => setOpen(false)} className="rounded-md px-3 py-2.5 text-[15px] font-medium text-fg-muted hover:bg-surface-hover">{l}</a>)}
            <div className="mt-2 grid grid-cols-2 gap-2"><Button asChild variant="secondary"><Link href="/login">Sign in</Link></Button><Button asChild><Link href="/signup">Start free trial</Link></Button></div>
          </Container>
        </div>
      )}
    </header>
  );
}
