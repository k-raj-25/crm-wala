"use client";
import { Mic, Phone, RotateCcw, Sparkles, MapPin } from "lucide-react";
import * as React from "react";
import { Button, Dialog, DialogContent, DialogFooter, Input, Segmented, Textarea } from "@crm/ui";
import { type AiProposal, useAiFeature } from "@/lib/ai";
import { api } from "@/lib/api";
import { ProposalCard } from "./proposal-card";
import { VoiceInput, WaMessage, appendText } from "./lead-ai-bits";

type Out = { proposal: AiProposal; whatsapp_message: string | null; phone: string | null };
const nowLocal = () => { const d = new Date(); const p = (n: number) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };

/** "Log by voice": say how the visit or call went, the assistant prepares the log, follow-up and a thank-you message. */
export function LeadVoiceLog({ leadId, phone }: { leadId: string; phone?: string | null }) {
  const on = useAiFeature("visit_log");
  const [open, setOpen] = React.useState(false); const [kind, setKind] = React.useState<"visit" | "call">("visit");
  const [text, setText] = React.useState(""); const [when, setWhen] = React.useState(""); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  const [out, setOut] = React.useState<Out | null>(null); const [msg, setMsg] = React.useState("");
  if (!on) return null;
  const reset = () => { setText(""); setWhen(""); setErr(null); setOut(null); setMsg(""); };
  const close = () => { setOpen(false); setTimeout(reset, 200); };
  const prepare = async () => {
    setBusy(true); setErr(null);
    try { const r = await api.post<Out>("/api/v1/ai/visit-log", { lead_id: leadId, text: text.trim(), kind, when: when ? new Date(when).toISOString() : undefined }); setOut(r); setMsg(r.whatsapp_message ?? ""); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}><Mic /> <span className="hidden sm:inline">Log by voice</span></Button>
      <Dialog open={open} onOpenChange={(o) => (o ? setOpen(true) : close())}>
        <DialogContent size="lg" title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Log by voice</span>} description="Tell me how it went, in English or Hindi. I'll prepare the log and the next step for you to check.">
          {out ? (
            <div className="space-y-3">
              <ProposalCard p={out.proposal} />
              {!!out.whatsapp_message && <WaMessage value={msg} onChange={setMsg} phone={out.phone ?? phone} label="Thank-you message" />}
              <DialogFooter><Button variant="secondary" onClick={reset}><RotateCcw /> Start over</Button><Button variant="ghost" onClick={close}>Close</Button></DialogFooter>
            </div>
          ) : (
            <div className="space-y-3">
              <Segmented value={kind} onChange={setKind} options={[{ value: "visit", label: "Site visit", icon: <MapPin /> }, { value: "call", label: "Call", icon: <Phone /> }]} />
              <VoiceInput onText={(t) => setText((s) => appendText(s, t))} />
              <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} aria-label="What happened" placeholder={kind === "visit" ? "e.g. Visited Tower B with wife, liked the 12th floor 3BHK, wants a better price, call back Saturday" : "e.g. Spoke for 5 minutes, budget is now 1.4 Cr, wants to see the site on Sunday"} />
              <div className="flex flex-wrap items-center gap-2"><label htmlFor="vl-when" className="text-xs font-medium text-fg-muted">When</label><Input id="vl-when" type="datetime-local" className="h-8 w-auto text-[13px]" value={when} max={nowLocal()} onChange={(e) => setWhen(e.target.value)} /><span className="text-xs text-fg-subtle">{when ? "" : "Leave empty for just now"}</span></div>
              {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{err}</p>}
              <DialogFooter><Button variant="secondary" onClick={close}>Cancel</Button><Button onClick={prepare} loading={busy} disabled={text.trim().length < 3}><Sparkles /> Prepare</Button></DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
