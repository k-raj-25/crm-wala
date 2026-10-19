"use client";
import { AnimatePresence, motion } from "framer-motion";
import { Maximize2, Plus, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { Badge, Button, Kbd, cn, useHotkey } from "@crm/ui";
import { MODE_LABEL, useAiFeature, useAiStatus } from "@/lib/ai";
import { Composer, Messages, pageContext, useAiChat } from "./chat";

export function ModeBadge({ className }: { className?: string }) {
  const s = useAiStatus().data;
  if (!s) return null;
  return <Badge tone={s.mode === "basic" ? "warning" : "primary"} className={className} title={s.model ? `${s.provider_label} · ${s.model}` : s.provider_label}>{MODE_LABEL[s.mode]}</Badge>;
}

const LEAD = ["Log a call: interested, call back Sunday", "Remind me to follow up tomorrow 11am", "Suggest flats for this lead"];
const PROJECT = ["Which flats here are still available?", "Who might want the flats in this project?", "How do I add a tower?"];
const GENERIC = ["What should I do first today?", "Show leads not called in 3 days", "Which source brought the most site visits this month?"];
const chips = (path: string) => /^\/app\/leads\/[0-9a-f-]{36}/.test(path) ? LEAD : /^\/app\/projects\/[0-9a-f-]{36}/.test(path) ? PROJECT : GENERIC;

/** Floating assistant: a ✨ button bottom right that opens a small chat which knows the page you're on. ⌘J / Ctrl+J toggles it. */
export function AiDock() {
  const on = useAiFeature("chat"); const path = usePathname(); const s = useAiStatus().data;
  const [open, setOpen] = React.useState(false); const chat = useAiChat();
  const hidden = !on || path.startsWith("/app/ai");
  useHotkey("mod+j", (e) => { if (hidden) return; e.preventDefault(); setOpen((o) => !o); }, [hidden]);
  React.useEffect(() => { if (!open) return; const f = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false); window.addEventListener("keydown", f); return () => window.removeEventListener("keydown", f); }, [open]);
  React.useEffect(() => { if (hidden) setOpen(false); }, [hidden]);
  if (hidden) return null;
  const send = (m: string) => chat.send(m, pageContext(path));
  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.section initial={{ y: 16, scale: 0.98 }} animate={{ y: 0, scale: 1 }} exit={{ opacity: 0, transition: { duration: 0 } }} transition={{ duration: 0.16 }} role="dialog" aria-label="Assistant"
            className="fixed inset-x-3 bottom-[96px] top-20 z-50 flex flex-col overflow-hidden glass-pop rounded-2xl border border-border shadow-lg md:inset-x-auto md:bottom-24 md:right-6 md:top-auto md:h-[min(640px,calc(100dvh-8rem))] md:w-[400px]">
            <header className="flex items-center gap-2 border-b border-border px-4 py-3">
              <Sparkles className="size-4 text-primary" /><h2 className="text-sm font-semibold">Assistant</h2><ModeBadge />
              <div className="ml-auto flex items-center gap-0.5">
                <Button size="icon-sm" variant="ghost" aria-label="New chat" title="New chat" onClick={chat.reset} disabled={!chat.msgs.length}><Plus /></Button>
                <Button size="icon-sm" variant="ghost" asChild><Link href="/app/ai" aria-label="Open full page" title="Open full page" onClick={() => setOpen(false)}><Maximize2 /></Link></Button>
                <Button size="icon-sm" variant="ghost" aria-label="Close" onClick={() => setOpen(false)}><X /></Button>
              </div>
            </header>
            {s?.mode === "basic" && <p className="border-b border-border bg-warning-soft px-4 py-1.5 text-xs text-warning">Basic mode.{s.can_manage && <> <Link href="/app/settings/ai" className="font-semibold underline" onClick={() => setOpen(false)}>Connect your AI key</Link> for full answers.</>}</p>}
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
              {chat.msgs.length === 0 ? (
                <div className="flex h-full flex-col justify-end gap-2">
                  <p className="mb-1 text-sm text-fg-muted">Ask anything or tell me what to do. I show every change before it happens.</p>
                  {chips(path).map((c) => <button key={c} onClick={() => send(c)} className="rounded-xl border border-border bg-surface px-3 py-2 text-left text-[13px] hover:border-primary/40 hover:bg-primary-soft/40">{c}</button>)}
                </div>
              ) : <Messages msgs={chat.msgs} busy={chat.busy} compact />}
            </div>
            <div className="border-t border-border bg-surface-2 p-2.5"><Composer onSend={send} busy={chat.busy} autoFocus placeholder="Ask or tell me what to do…" /></div>
          </motion.section>
        )}
      </AnimatePresence>
      <button onClick={() => setOpen((o) => !o)} aria-label={open ? "Close assistant" : "Open assistant (Ctrl+J)"} aria-expanded={open} title="Assistant (⌘J / Ctrl+J)"
        className={cn("group fixed bottom-[148px] right-4 z-40 flex size-12 items-center justify-center rounded-full shadow-lg transition-all hover:scale-105 md:bottom-6 md:right-6", open ? "bg-surface text-fg ring-1 ring-border" : "bg-primary text-primary-fg")}>
        {open ? <X className="size-5" /> : <Sparkles className="size-5" />}
        <span className="pointer-events-none absolute right-full mr-2 hidden items-center gap-1 whitespace-nowrap rounded-md bg-surface px-2 py-1 text-xs text-fg-muted opacity-0 shadow-sm ring-1 ring-border transition-opacity group-hover:opacity-100 md:flex">Assistant <Kbd>⌘</Kbd><Kbd>J</Kbd></span>
      </button>
    </>
  );
}
