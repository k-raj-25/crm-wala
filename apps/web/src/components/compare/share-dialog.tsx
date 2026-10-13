"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Mail, MessageCircle, Send, Share2 } from "lucide-react";
import * as React from "react";
import { ApiError, Button, Dialog, DialogContent, DialogFooter, Field, Input, Segmented, Textarea, useToast } from "@crm/ui";
import { AsyncSelect } from "@/components/forms/fields";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";

type Channel = "whatsapp" | "email";
type Who = "lead" | "contact";
type Person = { id: string; name?: string; first_name?: string; email?: string | null; phone?: string | null };

/** Fetches the comparison PDF as a file (used for download and the phone's own share sheet). */
export async function comparisonPdf(unitIds: string[], extra: { client_name?: string; title?: string; note?: string } = {}): Promise<File> {
  const res = await api.raw("POST", "/api/v1/comparisons/pdf", { unit_ids: unitIds, ...extra });
  if (!res.ok) {
    const e = (await res.json().catch(() => null))?.error ?? {};
    throw new ApiError(res.status, e.code ?? "error", e.message ?? "Couldn't make the PDF. Please try again.");
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "Flat comparison.pdf";
  return new File([await res.blob()], name, { type: "application/pdf" });
}

export function ShareComparison({ open, onOpenChange, unitIds, flatsLabel }: { open: boolean; onOpenChange: (o: boolean) => void; unitIds: string[]; flatsLabel: string }) {
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
  const [busy, setBusy] = React.useState<null | "send" | "file">(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [canShareFile, setCanShareFile] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setPerson(null); setName(""); setPhone(""); setEmail(""); setErr(null); setSubject("Flat comparison: {{first_name}}");
    setMessage(`Hi {{first_name}},\n\nAs discussed, here is a side-by-side comparison of ${flatsLabel}.\n\nHappy to arrange site visits for any of these.`);
    try { setCanShareFile(!!navigator.canShare?.({ files: [new File([""], "x.pdf", { type: "application/pdf" })] })); } catch { setCanShareFile(false); }
  }, [open, flatsLabel]);

  const first = (name.trim().split(/\s+/)[0] || "there");
  const merged = (s: string) => s.replace(/\{\{\s*first_name\s*\}\}/g, first);
  const pick = (id: string | null, item?: Record<string, unknown>) => {
    const p = id ? ({ id, ...(item ?? {}) } as Person) : null;
    setPerson(p);
    if (p) { setName(String(p.name ?? p.first_name ?? "")); setPhone(p.phone ?? ""); setEmail(p.email ?? ""); }
  };
  const rel = person ? (who === "lead" ? { lead_id: person.id } : { contact_id: person.id }) : {};

  const send = async () => {
    setErr(null);
    // open the WhatsApp tab inside the click, or the browser blocks it as a popup
    const win = channel === "whatsapp" ? window.open("about:blank", "_blank") : null;
    setBusy("send");
    try {
      const r = await api.post<{ whatsapp_url?: string; status?: string }>("/api/v1/comparisons/share", {
        unit_ids: unitIds, channel, client_name: name.trim() || undefined, ...rel,
        ...(channel === "whatsapp" ? { phone: phone.trim() || undefined, message: merged(message) } : { to: email.split(/[,;\s]+/).filter(Boolean), subject, message }),
      });
      if (channel === "whatsapp" && r.whatsapp_url) { if (win) win.location.href = r.whatsapp_url; else window.location.href = r.whatsapp_url; }
      toast.success(channel === "whatsapp" ? "WhatsApp is open with your message and the PDF link" : r.status === "scheduled" ? "Email scheduled" : "Comparison emailed with the PDF attached");
      qc.invalidateQueries({ queryKey: ["timeline"] }); qc.invalidateQueries({ queryKey: ["emails"] });
      onOpenChange(false);
    } catch (e) {
      win?.close();
      setErr(e instanceof ApiError ? (e.details ? String(Object.values(e.details)[0]) : e.message) : "Couldn't share. Please try again.");
    } finally { setBusy(null); }
  };

  const shareFile = async () => {
    setBusy("file"); setErr(null);
    try {
      const file = await comparisonPdf(unitIds, { client_name: name.trim() || undefined });
      await navigator.share({ files: [file], text: merged(message) });
    } catch (e) {
      if ((e as Error).name !== "AbortError") setErr((e as Error).message || "Couldn't open the share menu");
    } finally { setBusy(null); }
  };

  const ready = channel === "whatsapp" ? true : !!email.trim();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md" title="Share with a client" description="We'll turn this comparison into a PDF and send it.">
        <div className="space-y-4">
          <Segmented value={channel} onChange={(v) => setChannel(v)} className="w-full [&>*]:flex-1"
            options={[{ value: "whatsapp", label: "WhatsApp", icon: <MessageCircle /> }, ...(canEmail ? [{ value: "email" as Channel, label: "Email", icon: <Mail /> }] : [])]} />
          <Field label="Client">
            <div className="flex gap-2">
              <Segmented size="sm" value={who} onChange={(v) => { setWho(v); pick(null); }} options={[{ value: "lead", label: "Lead" }, { value: "contact", label: "Client" }]} />
              <div className="min-w-0 flex-1"><AsyncSelect key={who} value={person?.id ?? null} onChange={pick} endpoint={who === "lead" ? "/api/v1/leads" : "/api/v1/contacts"} placeholder={who === "lead" ? "Search leads…" : "Search clients…"} /></div>
            </div>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name on the PDF"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Client's name" maxLength={120} /></Field>
            {channel === "whatsapp"
              ? <Field label="WhatsApp number" hint="Leave empty to pick the chat in WhatsApp"><Input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" /></Field>
              : <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" /></Field>}
          </div>
          {channel === "email" && <Field label="Subject"><Input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={300} /></Field>}
          <Field label="Message" hint={channel === "whatsapp" ? "A link to the PDF is added at the end." : "The PDF is attached. {{first_name}} becomes the client's first name."}>
            <Textarea rows={channel === "whatsapp" ? 4 : 6} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={5000} />
          </Field>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter className="sm:items-center">
          {channel === "whatsapp" && canShareFile && <Button variant="secondary" onClick={shareFile} loading={busy === "file"} disabled={!!busy} className="sm:mr-auto"><Share2 /> Send the PDF file</Button>}
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={send} loading={busy === "send"} disabled={!ready || !!busy}>{channel === "whatsapp" ? <><MessageCircle /> Open WhatsApp</> : <><Send /> Send email</>}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
