"use client";
import { Sparkles } from "lucide-react";
import * as React from "react";
import { Button, Input, Popover, PopoverContent, PopoverTrigger } from "@crm/ui";
import { useAiFeature } from "@/lib/ai";
import { api } from "@/lib/api";

/** "Ask AI" beside the leads search: plain words in, list filters out. */
export function AskAiSearch({ onApply }: { onApply: (params: Record<string, string>, label: string) => void }) {
  const on = useAiFeature("search");
  const [open, setOpen] = React.useState(false); const [q, setQ] = React.useState(""); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  if (!on) return null;
  const go = async (e: React.FormEvent) => {
    e.preventDefault(); if (q.trim().length < 2) return; setBusy(true); setErr(null);
    try { const r = await api.post<{ params: Record<string, string>; label: string }>("/api/v1/ai/parse-search", { query: q.trim(), entity: "leads" }); onApply(Object.fromEntries(Object.entries(r.params ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => [k, String(v)])), r.label || q.trim()); setOpen(false); setQ(""); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setErr(null); }}>
      <PopoverTrigger asChild><Button variant="soft" size="md"><Sparkles /> Ask AI</Button></PopoverTrigger>
      <PopoverContent align="start" className="w-[420px] max-w-[calc(100vw-24px)]">
        <form onSubmit={go} className="space-y-2.5">
          <label htmlFor="ask-ai" className="block text-xs font-medium text-fg-muted">Describe the leads you want to see</label>
          <Input id="ask-ai" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. 3BHK buyers in Sector 62 under 1.5 Cr not contacted in 10 days" />
          {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{err}</p>}
          <div className="flex justify-end"><Button type="submit" size="sm" loading={busy} disabled={q.trim().length < 2}><Sparkles /> Show leads</Button></div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
