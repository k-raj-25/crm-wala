"use client";
import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Logo, ThemeToggle, cn } from "@crm/ui";
import { Container } from "./primitives";

const LINKS = [["Features", "#features"], ["AI", "#ai"], ["Automation", "#automation"], ["Pricing", "#pricing"], ["FAQ", "#faq"]];

export function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on(); window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className={cn("fixed inset-x-0 top-0 z-40 transition-all duration-200", scrolled || open ? "border-b border-border bg-bg/80 backdrop-blur-xl" : "border-b border-transparent")}>
      <Container className="flex h-16 items-center justify-between">
        <Link href="/" aria-label="CRM Wala home"><Logo /></Link>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {LINKS.map(([l, h]) => <a key={h} href={h} className="rounded-md px-3 py-2 text-sm font-medium text-fg-muted transition-colors hover:text-fg">{l}</a>)}
        </nav>
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          <Button asChild variant="ghost" className="hidden sm:inline-flex"><Link href="/login">Sign in</Link></Button>
          <Button asChild className="hidden sm:inline-flex"><Link href="/signup">Start free trial</Link></Button>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>{open ? <X /> : <Menu />}</Button>
        </div>
      </Container>
      {open && (
        <div className="animate-fade-in border-t border-border bg-bg md:hidden">
          <Container className="flex flex-col gap-1 py-4">
            {LINKS.map(([l, h]) => <a key={h} href={h} onClick={() => setOpen(false)} className="rounded-md px-3 py-2.5 text-[15px] font-medium text-fg-muted hover:bg-surface-hover">{l}</a>)}
            <div className="mt-2 grid grid-cols-2 gap-2"><Button asChild variant="secondary"><Link href="/login">Sign in</Link></Button><Button asChild><Link href="/signup">Start free trial</Link></Button></div>
          </Container>
        </div>
      )}
    </header>
  );
}
