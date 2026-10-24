"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, Link2, Mail, MessageCircle, Send, Share2 } from "lucide-react";
import * as React from "react";
import { ApiError, Button, Dialog, DialogContent, DialogFooter, Field, Input, Segmented, Switch, Textarea, useToast } from "@crm/ui";
import { AsyncSelect } from "@/components/forms/fields";
import { isMasked } from "@/components/records/phone-field";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import type { Project } from "@/lib/realestate";

type Channel = "whatsapp" | "email" | "link";
type Who = "lead" | "contact";
type Person = { id: string; name?: string; first_name?: string; email?: string | null; phone?: string | null };
type ShareOut = { url: string; whatsapp_url?: string; status?: string };

/** "Share" on the project page: one public page with the society's photos, layouts, floor plans and brochure, sent as a link. */
export function ShareSocietyButton({ p }: { p: Project }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)} aria-label="Share with a client"><Share2 /> <span className="hidden sm:inline">Share</span></Button>
      <ShareSocietyDialog open={open} onOpenChange={setOpen} p={p} />
    </>
  );
}

function ShareSocietyDialog({ open, onOpenChange, p }: { open: boolean; onOpenChange: (o: boolean) => void; p: Project }) {
  const toast = useToast(); const qc = useQueryClient(); const { can } = useAccess();
  const canEmail = can("emails.create");
  const [channel, setChannel] = React.useState<Channel>("whatsapp");
  const [who, setWho] = React.useState<Who>("lead");
  const [person, setPerson] = React.useState<Person | null>(null);
  const [name, setName] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [subject, setSubject] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [prices, setPrices] = React.useState(true);
  const [link, setLink] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setPerson(null); setName(""); setPhone(""); setEmail(""); setErr(null); setLink(null); setCopied(false); setPrices(true);
    setSubject(`${p.name}: photos, floor plans and brochure`);
    setMessage(`Hi {{first_name}}, here are the details of ${p.name}: photos, layouts, floor plans and the brochure.`);
  }, [open, p.name]);
  React.useEffect(() => { setLink(null); setCopied(false); }, [person, prices]); // a different client or price choice makes a different link

  const first = name.trim().split(/\s+/)[0] || "there";
  const merged = (s: string) => s.replace(/\{\{\s*first_name\s*\}\}/g, first);
  const pick = (id: string | null, item?: Record<string, unknown>) => {
    const x = id ? ({ id, ...(item ?? {}) } as Person) : null;
    setPerson(x);
    if (x) { setName(String(x.first_name ?? x.name ?? "")); setPhone(isMasked(x.phone) ? "" : x.phone ?? ""); setEmail(x.email ?? ""); }
  };
  const rel = person ? (who === "lead" ? { lead_id: person.id } : { contact_id: person.id }) : {};

  const post = (body: Record<string, unknown>) => api.post<ShareOut>(`/api/v1/projects/${p.id}/share`, { ...rel, hide_prices: !prices, client_name: name.trim() || undefined, ...body });
  const fail = (e: unknown) => setErr(e instanceof ApiError ? (e.details ? String(Object.values(e.details)[0]) : e.message) : "Couldn't share. Please try again.");

  const copy = async () => {
    setErr(null); setBusy(true);
    try {
      const url = link ?? (await post({ channel: "link" })).url;
      setLink(url);
      try { await navigator.clipboard.writeText(url); setCopied(true); toast.success("Link copied", "Paste it in any chat or email."); } catch { /* the link is on screen to copy by hand */ }
      if (person) qc.invalidateQueries({ queryKey: ["timeline"] });
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const send = async () => {
    setErr(null);
    // open the WhatsApp tab inside the click, or the browser blocks it as a popup
    const win = channel === "whatsapp" ? window.open("about:blank", "_blank") : null;
    setBusy(true);
    try {
      const r = await post(channel === "whatsapp" ? { channel, phone: phone.trim() || undefined, message: merged(message) } : { channel, to: email.split(/[,;\s]+/).filter(Boolean), subject, message });
      if (channel === "whatsapp" && r.whatsapp_url) { if (win) win.location.href = r.whatsapp_url; else window.location.href = r.whatsapp_url; }
      toast.success(channel === "whatsapp" ? "WhatsApp is open with your message and the link" : r.status === "scheduled" ? "Email scheduled" : "Email sent with the link");
      qc.invalidateQueries({ queryKey: ["timeline"] }); qc.invalidateQueries({ queryKey: ["emails"] });
      onOpenChange(false);
    } catch (e) { win?.close(); fail(e); } finally { setBusy(false); }
  };

  const nativeShare = async () => {
    if (!link) return;
    try { await navigator.share({ title: p.name, text: merged(message), url: link }); } catch { /* closed */ }
  };
  const canNativeShare = typeof navigator !== "undefined" && !!navigator.share;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md" title="Share this society" description="Your client gets a page with photos, layouts, floor plans and the brochure. No login needed.">
        <div className="space-y-4">
          <Segmented value={channel} onChange={(v) => { setChannel(v); setErr(null); }} className="w-full [&>*]:flex-1"
            options={[{ value: "whatsapp", label: "WhatsApp", icon: <MessageCircle /> }, ...(canEmail ? [{ value: "email" as Channel, label: "Email", icon: <Mail /> }] : []), { value: "link", label: "Copy link", icon: <Link2 /> }]} />
          <Field label="Client" hint={channel === "link" ? "Optional. Pick one and you'll be told when they open the page." : "We'll note it on their timeline and tell you when they open the page."}>
            <div className="flex gap-2">
              <Segmented size="sm" value={who} onChange={(v) => { setWho(v); pick(null); }} options={[{ value: "lead", label: "Lead" }, { value: "contact", label: "Client" }]} />
              <div className="min-w-0 flex-1"><AsyncSelect key={who} value={person?.id ?? null} onChange={pick} endpoint={who === "lead" ? "/api/v1/leads" : "/api/v1/contacts"} placeholder={who === "lead" ? "Search leads…" : "Search clients…"} /></div>
            </div>
          </Field>
          {channel !== "link" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Client's name" maxLength={120} /></Field>
              {channel === "whatsapp"
                ? <Field label="WhatsApp number" hint="Leave empty to pick the chat in WhatsApp"><Input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" /></Field>
                : <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" /></Field>}
            </div>
          )}
          {channel === "email" && <Field label="Subject"><Input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={300} /></Field>}
          {channel !== "link" && (
            <Field label="Message" hint={channel === "whatsapp" ? "The link is added at the end." : "{{first_name}} becomes the client's first name. The link is added at the end."}>
              <Textarea rows={channel === "whatsapp" ? 3 : 5} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={5000} />
            </Field>
          )}
          <label className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface-2/60 px-3 py-2.5">
            <span><span className="block text-sm font-medium">Show prices</span><span className="block text-xs text-fg-muted">Starting price and price per layout, from today's stock</span></span>
            <Switch checked={prices} onCheckedChange={setPrices} aria-label="Show prices" />
          </label>
          {channel === "link" && link && (
            <div className="flex gap-2">
              <Input readOnly value={link} onFocus={(e) => e.currentTarget.select()} aria-label="Link to the society page" className="font-mono text-xs" />
              <Button asChild variant="secondary" size="icon" aria-label="Open the page"><a href={link} target="_blank" rel="noopener noreferrer"><ExternalLink /></a></Button>
            </div>
          )}
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter className="sm:items-center">
          {channel === "link" && link && canNativeShare && <Button variant="secondary" onClick={nativeShare} className="sm:mr-auto"><Share2 /> Share…</Button>}
          <Button variant="secondary" onClick={() => onOpenChange(false)}>{channel === "link" && link ? "Done" : "Cancel"}</Button>
          {channel === "link"
            ? <Button onClick={copy} loading={busy}>{copied ? <><Check /> Copied</> : <><Copy /> Copy link</>}</Button>
            : <Button onClick={send} loading={busy} disabled={channel === "email" && !email.trim()}>{channel === "whatsapp" ? <><MessageCircle /> Open WhatsApp</> : <><Send /> Send email</>}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
