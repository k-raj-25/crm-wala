"use client";
import { Copy, FileAudio, Mic, MicOff, Send } from "lucide-react";
import * as React from "react";
import { Button, Segmented, Textarea, cn, useToast } from "@crm/ui";
import { isMasked } from "@/components/records/phone-field";
import { useAiStatus, useDictation, waLink } from "@/lib/ai";
import { api } from "@/lib/api";

export type DictLang = "en-IN" | "hi-IN";

/** Mic dictation with English / Hindi, plus "Upload voice note" when the workspace's AI can transcribe audio. Text goes to onText. */
export function VoiceInput({ onText, className }: { onText: (t: string) => void; className?: string }) {
  const status = useAiStatus(); const toast = useToast();
  const [lang, setLang] = React.useState<DictLang>("en-IN"); const [busy, setBusy] = React.useState(false);
  const dict = useDictation(onText); const file = React.useRef<HTMLInputElement>(null);
  const upload = async (f?: File | null) => {
    if (!f) return; setBusy(true);
    try { const fd = new FormData(); fd.append("file", f); const r = await api.upload<{ text: string }>("/api/v1/ai/transcribe", fd); r.text?.trim() ? onText(r.text.trim()) : toast.error("Couldn't hear anything in that voice note"); }
    catch (e) { toast.error("Couldn't read the voice note", (e as Error).message); } finally { setBusy(false); if (file.current) file.current.value = ""; }
  };
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant={dict.on ? "danger-soft" : "secondary"} onClick={() => (dict.on ? dict.stop() : dict.start(lang))}>{dict.on ? <><MicOff /> Stop</> : <><Mic /> Dictate</>}</Button>
        <Segmented size="sm" value={lang} onChange={(v) => { setLang(v); if (dict.on) { dict.stop(); setTimeout(() => dict.start(v), 150); } }} options={[{ value: "en-IN", label: "English" }, { value: "hi-IN", label: "Hindi" }]} />
        {status.data?.audio_files && <><Button type="button" size="sm" variant="ghost" loading={busy} onClick={() => file.current?.click()}><FileAudio /> Upload voice note</Button><input ref={file} type="file" accept="audio/*" className="hidden" onChange={(e) => upload(e.target.files?.[0])} /></>}
        {dict.on && <span className="inline-flex items-center gap-1.5 text-xs text-danger"><span className="size-2 animate-pulse rounded-full bg-danger" /> Listening…</span>}
      </div>
      {dict.error && <p className="text-xs text-danger">{dict.error}</p>}
    </div>
  );
}

/** Appends a dictated phrase to existing text with a space or new line. */
export const appendText = (cur: string, t: string) => (cur.trim() ? cur.replace(/\s+$/, "") + (/[.!?।]$/.test(cur.trim()) ? " " : ". ") + t : t);

/** An editable WhatsApp message with Copy and Send on WhatsApp. */
export function WaMessage({ value, onChange, phone, label = "WhatsApp message", rows = 4 }: { value: string; onChange: (v: string) => void; phone?: string | null; label?: string; rows?: number }) {
  const toast = useToast(); const id = React.useId();
  return (
    <div className="rounded-xl border border-border bg-surface-2 p-3">
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-fg-muted">{label}</label>
      <Textarea id={id} rows={rows} value={value} onChange={(e) => onChange(e.target.value)} className="bg-surface" />
      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" disabled={!value.trim()} onClick={() => { navigator.clipboard?.writeText(value); toast.success("Copied"); }}><Copy /> Copy</Button>
        {phone && isMasked(phone) ? <span className="self-center text-xs text-fg-subtle">Copy it into the record's WhatsApp tab to send.</span> : phone ? <Button size="sm" variant="soft" disabled={!value.trim()} asChild><a href={waLink(phone, value)} target="_blank" rel="noreferrer"><Send /> Send on WhatsApp</a></Button> : <span className="self-center text-xs text-fg-subtle">Add a phone number to send it on WhatsApp.</span>}
      </div>
    </div>
  );
}
