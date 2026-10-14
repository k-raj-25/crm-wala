"use client";
import { Flame, MessageCircle, RotateCcw, Sparkles } from "lucide-react";
import * as React from "react";
import { Badge, Button, Dialog, DialogContent, DialogFooter, Input, Textarea } from "@crm/ui";
import { type AiProposal, useAiFeature } from "@/lib/ai";
import { api } from "@/lib/api";
import { ProposalList } from "./proposal-card";
import { WaMessage } from "./lead-ai-bits";

type Out = { summary: string; reply: string; language?: string; hot: boolean; signals: string[]; proposals: AiProposal[]; phone: string | null };
const GOALS = ["Book a site visit", "Share price list", "Negotiate"];

/** Paste-based WhatsApp helper: reads the chat, sums it up, drafts a reply and suggests updates to the lead. */
export function LeadWhatsApp({ leadId, phone }: { leadId: string; phone?: string | null }) {
  const on = useAiFeature("whatsapp");
  const [open, setOpen] = React.useState(false); const [chat, setChat] = React.useState(""); const [goal, setGoal] = React.useState("");
  const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null); const [out, setOut] = React.useState<Out | null>(null); const [reply, setReply] = React.useState("");
  if (!on) return null;
  const reset = () => { setChat(""); setGoal(""); setErr(null); setOut(null); setReply(""); };
  const close = () => { setOpen(false); setTimeout(reset, 200); };
  const go = async () => {
    setBusy(true); setErr(null);
    try { const r = await api.post<Out>("/api/v1/ai/whatsapp-assist", { conversation: chat.trim(), lead_id: leadId, goal: goal.trim() || undefined }); setOut(r); setReply(r.reply ?? ""); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}><MessageCircle /> <span className="hidden sm:inline">WhatsApp helper</span></Button>
      <Dialog open={open} onOpenChange={(o) => (o ? setOpen(true) : close())}>
        <DialogContent size="lg" title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> WhatsApp helper</span>} description="Paste the chat (or just the last few messages). I'll sum it up and draft your reply.">
          {out ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-border bg-surface-2 p-3">
                <div className="mb-1 flex flex-wrap items-center gap-2"><span className="text-xs font-medium text-fg-muted">Summary</span>{out.hot && <Badge tone="danger"><Flame className="size-3" /> Hot lead</Badge>}</div>
                <p className="whitespace-pre-wrap text-[13px]">{out.summary}</p>
                {out.hot && out.signals?.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{out.signals.map((s) => <Badge key={s} tone="warning">{s}</Badge>)}</div>}
              </div>
              <WaMessage value={reply} onChange={setReply} phone={out.phone ?? phone} label="Suggested reply" rows={5} />
              {out.proposals?.length > 0 && <div className="space-y-2"><p className="text-xs font-medium text-fg-muted">Update the lead</p><ProposalList items={out.proposals} compact /></div>}
              <DialogFooter><Button variant="secondary" onClick={reset}><RotateCcw /> Start over</Button><Button variant="ghost" onClick={close}>Close</Button></DialogFooter>
            </div>
          ) : (
            <div className="space-y-3">
              <Textarea rows={9} autoFocus value={chat} onChange={(e) => setChat(e.target.value)} aria-label="WhatsApp chat" placeholder="Paste the WhatsApp chat here. In WhatsApp, use More, Export chat, or select and copy the messages." />
              <div>
                <label htmlFor="wa-goal" className="mb-1.5 block text-xs font-medium text-fg-muted">What do you want from this reply? (optional)</label>
                <Input id="wa-goal" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="e.g. book a site visit" />
                <div className="mt-2 flex flex-wrap gap-1.5">{GOALS.map((g) => <button key={g} type="button" aria-pressed={goal === g.toLowerCase()} onClick={() => setGoal(goal === g.toLowerCase() ? "" : g.toLowerCase())} className={goal === g.toLowerCase() ? "rounded-full border border-primary bg-primary-soft px-2.5 py-1 text-xs font-medium text-primary" : "rounded-full border border-border px-2.5 py-1 text-xs font-medium text-fg-muted hover:bg-surface-hover"}>{g}</button>)}</div>
              </div>
              {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{err}</p>}
              <DialogFooter><Button variant="secondary" onClick={close}>Cancel</Button><Button onClick={go} loading={busy} disabled={!chat.trim()}><Sparkles /> Help me reply</Button></DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
