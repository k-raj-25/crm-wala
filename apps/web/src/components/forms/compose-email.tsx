"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Clock, FileText, MailCheck, Send, Sparkles, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { ApiError, Button, Dialog, DialogContent, DialogFooter, Field, Input, Popover, PopoverContent, PopoverTrigger, Textarea, Switch, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import type { EmailMsg } from "@/lib/types";
import { fromLocalInput, toLocalInput } from "./fields";

type Tpl = { id: string; name: string; subject: string; body: string };
export function ComposeEmail({ open, onOpenChange, defaults }: { open: boolean; onOpenChange: (o: boolean) => void; defaults?: Record<string, unknown> }) {
  const qc = useQueryClient(); const toast = useToast(); const { has, can } = useAccess();
  const [to, setTo] = React.useState(""); const [subject, setSubject] = React.useState(""); const [body, setBody] = React.useState("");
  const [track, setTrack] = React.useState(true); const [schedule, setSchedule] = React.useState(false); const [when, setWhen] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null); const [drafting, setDrafting] = React.useState(false);
  React.useEffect(() => { if (open) { setTo((defaults?.to as string) ?? ""); setSubject((defaults?.subject as string) ?? ""); setBody((defaults?.body as string) ?? ""); setSchedule(false); setWhen(null); setErr(null); } }, [open, defaults]);
  const tpls = useQuery({ queryKey: ["email-templates"], enabled: open, queryFn: () => api.get<Tpl[]>("/api/v1/emails/templates") });
  const sender = useQuery({ queryKey: ["email-sender"], enabled: open, queryFn: () => api.get<{ mode: string; address: string; verified: boolean }>("/api/v1/emails/sender") });
  const unverified = sender.data ? !sender.data.verified : false;
  const [resent, setResent] = React.useState(false); const [resending, setResending] = React.useState(false);
  const resend = async () => {
    setResending(true);
    try { await api.post("/api/v1/auth/resend-verification"); setResent(true); } catch (e) { toast.error("Couldn't send the link", (e as Error).message); } finally { setResending(false); }
  };
  const rel = { lead_id: defaults?.lead_id, contact_id: defaults?.contact_id, company_id: defaults?.company_id, deal_id: defaults?.deal_id };

  const draft = async () => {
    const ent = rel.contact_id ? ["contact", rel.contact_id] : rel.lead_id ? ["lead", rel.lead_id] : rel.deal_id ? ["deal", rel.deal_id] : null;
    if (!ent) { toast.error("Open a contact, lead or deal first", "The AI drafts emails from a record's context."); return; }
    setDrafting(true);
    try { const r = await api.post<{ subject: string; body: string }>("/api/v1/ai/email-draft", { entity: ent[0], id: ent[1], goal: "follow_up" }); setSubject(r.subject); setBody(r.body); }
    catch (e) { toast.error("Couldn't draft email", (e as Error).message); } finally { setDrafting(false); }
  };
  const send = async () => {
    setBusy(true); setErr(null);
    try {
      const addrs = to.split(/[,;\s]+/).filter(Boolean);
      const r = await api.post<EmailMsg>("/api/v1/emails/send", { to: addrs, subject, body, track, scheduled_at: schedule ? when : null, ...Object.fromEntries(Object.entries(rel).filter(([, v]) => v)) });
      qc.invalidateQueries({ queryKey: ["emails"] }); qc.invalidateQueries({ queryKey: ["timeline"] });
      toast.success(schedule ? "Email scheduled" : r.status === "failed" ? "Saved, but delivery failed" : "Email sent");
      onOpenChange(false);
    } catch (e) { setErr(e instanceof ApiError ? (e.details ? Object.values(e.details)[0] : e.message) : "Couldn't send"); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" title="New email" description="Emails go out in your name. Replies come to you.">
        <div className="space-y-4">
          {unverified && (
            <div role="alert" className="flex gap-3 rounded-lg border border-warning/30 bg-warning-soft p-3.5 text-sm text-warning">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div className="flex-1">
                <p className="font-medium">Verify your email to start sending</p>
                <p className="mt-0.5 text-[13px] opacity-90">Emails are sent in your name, so we first need to confirm {sender.data?.address} is yours. Open the link we emailed you.</p>
                <Button type="button" variant="secondary" size="xs" className="mt-2" onClick={resend} loading={resending} disabled={resent}><MailCheck /> {resent ? "Link sent - check your inbox" : "Resend verification email"}</Button>
              </div>
            </div>
          )}
          {sender.data && !unverified && (
            <p className="flex items-start gap-2 rounded-lg bg-bg-subtle px-3.5 py-2.5 text-[13px] text-fg-muted">
              <MailCheck className="mt-0.5 size-4 shrink-0 text-success" />
              {sender.data.mode === "platform"
                ? <span>Sent as <b className="font-medium text-fg">your name via CRM Wala</b>; replies go to <b className="font-medium text-fg">{sender.data.address}</b>. To send from your own address, <Link href="/app/integrations" className="text-primary hover:underline" onClick={() => onOpenChange(false)}>connect your Gmail or Outlook</Link>.</span>
                : <span>Sending from your own {sender.data.mode === "gmail" ? "Gmail" : "Outlook"} account, <b className="font-medium text-fg">{sender.data.address}</b>.</span>}
            </p>
          )}
          <Field label="To" error={err && /to/i.test(err) ? err : undefined}><Input value={to} onChange={(e) => setTo(e.target.value)} placeholder="name@company.com" autoFocus={!to} /></Field>
          <Field label="Subject"><Input value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>
          <div>
            <div className="mb-1.5 flex items-center justify-between"><label htmlFor="mail-body" className="text-[13px] font-medium">Message</label>
              <div className="flex items-center gap-1">
                <Popover><PopoverTrigger asChild><Button type="button" variant="ghost" size="xs"><FileText /> Templates</Button></PopoverTrigger>
                  <PopoverContent align="end" className="w-72 p-1.5">{tpls.data?.length ? tpls.data.map((t) => <button key={t.id} className="block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-surface-hover" onClick={() => { setSubject(t.subject); setBody(t.body); }}><span className="font-medium">{t.name}</span><span className="block truncate text-xs text-fg-subtle">{t.subject}</span></button>) : <p className="px-3 py-4 text-center text-sm text-fg-subtle">No templates yet. Save one from Settings → Email.</p>}</PopoverContent></Popover>
                {has("ai_assistant") && can("ai.use") && <Button type="button" variant="soft" size="xs" onClick={draft} loading={drafting}><Sparkles /> Write with AI</Button>}
              </div></div>
            <Textarea id="mail-body" rows={9} value={body} onChange={(e) => setBody(e.target.value)} placeholder={"Hi {{first_name}},\n\n…"} />
            <p className="mt-1.5 text-xs text-fg-subtle">Merge fields: {"{{first_name}} {{company}} {{sender_name}}"}</p>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg bg-bg-subtle px-4 py-3 text-sm">
            {has("email_tracking") && <label className="flex items-center gap-2.5"><Switch checked={track} onCheckedChange={setTrack} aria-label="Track opens" />Track opens</label>}
            <label className="flex items-center gap-2.5"><Switch checked={schedule} onCheckedChange={(v) => { setSchedule(v); if (v && !when) setWhen(new Date(Date.now() + 3600e3).toISOString()); }} aria-label="Schedule send" /><Clock className="size-4 text-fg-subtle" />Schedule</label>
            {schedule && <Input type="datetime-local" className="w-56" value={toLocalInput(when)} onChange={(e) => setWhen(fromLocalInput(e.target.value))} aria-label="Send time" />}
          </div>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={send} loading={busy} disabled={!to.trim() || !subject.trim() || !body.trim() || unverified}><Send />{schedule ? "Schedule" : "Send"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
export { X };
