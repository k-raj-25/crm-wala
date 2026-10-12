"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Mic, MicOff, Sparkles } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { BarsChart, Button, LineTrend, cn, formatMoneyCompact, useToast } from "@crm/ui";
import { Markdown } from "@/components/markdown";
import { type AiChart, type AiProposal, useDictation } from "@/lib/ai";
import { api } from "@/lib/api";
import { ProposalList } from "./proposal-card";

export type ChatMsg = { role: "user" | "assistant"; content: string; sources?: { label: string; url: string; type: string }[]; charts?: AiChart[]; proposals?: AiProposal[] };
export type PageCtx = { path: string; entity?: string; id?: string; label?: string };

/** The page the person is looking at, so "move this lead to Interested" knows which lead. */
export function pageContext(pathname: string, label?: string): PageCtx {
  const m = pathname.match(/^\/app\/(leads|contacts|deals|companies|projects)\/([0-9a-f-]{36})/);
  const types: Record<string, string> = { leads: "lead", contacts: "contact", deals: "deal", companies: "company", projects: "project" };
  const unit = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("unit") : null;
  if (unit && m?.[1] === "projects") return { path: pathname, entity: "unit", id: unit, label };
  return m ? { path: pathname, entity: types[m[1]], id: m[2], label } : { path: pathname, label };
}

export function useAiChat() {
  const qc = useQueryClient(); const toast = useToast();
  const [id, setId] = React.useState<string | null>(null); const [msgs, setMsgs] = React.useState<ChatMsg[]>([]); const [busy, setBusy] = React.useState(false);
  const send = async (m: string, page?: PageCtx) => {
    if (!m.trim() || busy) return false; setBusy(true);
    const history = msgs; setMsgs((p) => [...p, { role: "user", content: m }]);
    try {
      const r = await api.post<{ conversation_id: string; answer: string; sources: ChatMsg["sources"]; charts?: AiChart[]; proposals?: AiProposal[] }>("/api/v1/ai/chat", { message: m, conversation_id: id, page });
      setId(r.conversation_id); setMsgs((p) => [...p, { role: "assistant", content: r.answer, sources: r.sources, charts: r.charts, proposals: r.proposals }]);
      qc.invalidateQueries({ queryKey: ["ai-usage"] }); qc.invalidateQueries({ queryKey: ["ai-convs"] }); return true;
    } catch (e) { setMsgs(history); toast.error("The assistant couldn't answer", (e as Error).message); return false; } finally { setBusy(false); }
  };
  const open = async (cid: string) => { const c = await api.get<{ messages: ChatMsg[] }>(`/api/v1/ai/conversations/${cid}`); setId(cid); setMsgs(c.messages); };
  const reset = () => { setId(null); setMsgs([]); };
  return { id, msgs, busy, send, open, reset };
}

export function ChartView({ c }: { c: AiChart }) {
  const fmt = c.format === "money" ? (v: number) => formatMoneyCompact(v) : c.format === "percent" ? (v: number) => `${v}%` : undefined;
  const series = (c.series ?? []).filter(Boolean);
  if (!c.data?.length || !series.length) return null;
  return <div className="rounded-xl border border-border bg-surface p-3">{c.title && <p className="mb-2 text-xs font-semibold text-fg-muted">{c.title}</p>}
    {c.type === "line" ? <LineTrend data={c.data} xKey={c.x} series={series} height={200} format={fmt} /> : <BarsChart data={c.data} xKey={c.x} series={series} height={Math.max(180, Math.min(320, c.data.length * 28))} format={fmt} horizontal={c.data.length > 6} />}</div>;
}

export function Messages({ msgs, busy, compact }: { msgs: ChatMsg[]; busy: boolean; compact?: boolean }) {
  const end = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);
  return (
    <ul className={cn("mx-auto max-w-3xl", compact ? "space-y-4" : "space-y-6")}>
      {msgs.map((m, i) => m.role === "user" ? <li key={i} className="flex justify-end"><p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-fg">{m.content}</p></li> : (
        <li key={i} className="flex gap-3">{!compact && <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary"><Sparkles className="size-4" /></span>}
          <div className="min-w-0 flex-1 space-y-2.5">{m.content && <div className={cn("rounded-2xl rounded-tl-md border border-border bg-surface", compact ? "px-3.5 py-2.5 text-sm" : "px-5 py-4")}><Markdown>{m.content}</Markdown></div>}
            {m.charts?.map((c, k) => <ChartView key={k} c={c} />)}
            <ProposalList items={m.proposals} compact={compact} />
            {!!m.sources?.length && <div className="flex flex-wrap gap-1.5">{m.sources.map((s, k) => <Link key={k} href={s.url} className="rounded-full border border-border px-2.5 py-0.5 text-xs text-fg-muted hover:border-primary/40 hover:text-primary">{s.label}</Link>)}</div>}</div></li>))}
      {busy && <li className="flex gap-3">{!compact && <span className="flex size-8 items-center justify-center rounded-full bg-primary-soft text-primary"><Sparkles className="size-4" /></span>}<div className="flex items-center gap-1 rounded-2xl border border-border px-5 py-4" aria-label="Thinking">{[0, 1, 2].map((d) => <span key={d} className="size-2 animate-bounce rounded-full bg-fg-subtle" style={{ animationDelay: `${d * 120}ms` }} />)}</div></li>}
      <div ref={end} />
    </ul>
  );
}

/** Text box with a microphone. Enter sends, Shift+Enter adds a line. */
export function Composer({ onSend, busy, placeholder = "Ask or tell me what to do…", autoFocus }: { onSend: (t: string) => Promise<boolean> | void; busy: boolean; placeholder?: string; autoFocus?: boolean }) {
  const [text, setText] = React.useState("");
  const dict = useDictation((t) => setText((s) => (s ? s + " " : "") + t));
  const submit = async () => { const t = text.trim(); if (!t || busy) return; dict.stop(); setText(""); const ok = await onSend(t); if (ok === false) setText(t); };
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <div className="flex items-end gap-1.5 rounded-xl border border-border bg-surface p-2 shadow-xs focus-within:border-primary focus-within:ring-4 focus-within:ring-[var(--ring)]">
        <textarea value={text} autoFocus={autoFocus} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} rows={1} placeholder={dict.on ? "Listening… speak now" : placeholder} aria-label="Message" className="max-h-32 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-fg-subtle" />
        {dict.supported && <Button type="button" size="icon" variant={dict.on ? "danger" : "ghost"} aria-label={dict.on ? "Stop dictation" : "Dictate"} onClick={() => dict.on ? dict.stop() : dict.start()}>{dict.on ? <MicOff /> : <Mic />}</Button>}
        <Button type="submit" size="icon" disabled={!text.trim() || busy} aria-label="Send"><ArrowUp /></Button>
      </div>
      {dict.error && <p className="mt-1 text-xs text-danger">{dict.error}</p>}
    </form>
  );
}
