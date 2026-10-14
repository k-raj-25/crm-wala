"use client";
import { ImagePlus, RotateCcw, Sparkles, X } from "lucide-react";
import * as React from "react";
import { Button, Dialog, DialogContent, DialogFooter, NativeSelect, Textarea, useToast } from "@crm/ui";
import { type AiProposal, fileToImage, useAiFeature, useAiStatus } from "@/lib/ai";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { ProposalList } from "./proposal-card";
import { VoiceInput, appendText } from "./lead-ai-bits";

const CAPTURE_SOURCES: [string, string][] = [["whatsapp", "WhatsApp"], ["walk_in", "Walk-in"], ["call", "Call"], ["referral", "Referral"], ["99acres", "99acres"], ["magicbricks", "MagicBricks"], ["housing", "Housing"], ["facebook_ads", "Facebook"], ["website", "Website"], ["other", "Other"]];
type Img = { media_type: string; data: string; name: string };
type CaptureOut = { fields: Record<string, unknown>; duplicates: unknown[]; proposals: AiProposal[] };

/** "Capture with AI": paste a message, add a visiting card photo or speak, and the assistant prepares the lead for approval. */
export function CaptureDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const status = useAiStatus(); const toast = useToast();
  const [text, setText] = React.useState(""); const [images, setImages] = React.useState<Img[]>([]); const [source, setSource] = React.useState("");
  const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null); const [out, setOut] = React.useState<CaptureOut | null>(null);
  const file = React.useRef<HTMLInputElement>(null);
  const photos = !!status.data?.photos;
  const reset = () => { setText(""); setImages([]); setSource(""); setErr(null); setOut(null); };
  const close = () => { onOpenChange(false); setTimeout(reset, 200); };
  const addPhotos = async (files: FileList | null) => {
    if (!files) return;
    for (const f of Array.from(files).slice(0, 3 - images.length)) { try { const i = await fileToImage(f); setImages((s) => [...s, { ...i, name: f.name }].slice(0, 3)); } catch (e) { toast.error("Couldn't add that photo", (e as Error).message); } }
    if (file.current) file.current.value = "";
  };
  const read = async () => {
    setBusy(true); setErr(null);
    try { setOut(await api.post<CaptureOut>("/api/v1/ai/capture", { text: text.trim() || undefined, images: images.map(({ media_type, data }) => ({ media_type, data })), source: source || undefined })); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent size="lg" title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Capture with AI</span>} description="Paste an enquiry, add a photo or speak. You check everything before it's saved.">
        {out ? (
          <div className="space-y-3">
            {out.proposals.length ? <ProposalList items={out.proposals} /> : <p className="rounded-lg bg-surface-2 px-3 py-3 text-[13px] text-fg-muted">I couldn't find a name or phone number in that. Add a little more and try again.</p>}
            <DialogFooter><Button variant="secondary" onClick={reset}><RotateCcw /> Start over</Button><Button variant="ghost" onClick={close}>Close</Button></DialogFooter>
          </div>
        ) : (
          <div className="space-y-3">
            <Textarea rows={7} autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a WhatsApp message, an email or portal enquiry…" aria-label="Enquiry text" />
            <VoiceInput onText={(t) => setText((s) => appendText(s, t))} />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" variant="secondary" disabled={!photos || images.length >= 3} onClick={() => file.current?.click()}><ImagePlus /> Add photo</Button>
              <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" multiple className="hidden" onChange={(e) => addPhotos(e.target.files)} />
              {!photos && <span className="text-xs text-fg-subtle">Reading photos needs your workspace's own AI key (Settings, AI).</span>}
              {photos && !images.length && <span className="text-xs text-fg-subtle">Visiting card, screenshot or a filled form</span>}
              {images.map((im, i) => <span key={i} className="relative"><img src={`data:${im.media_type};base64,${im.data}`} alt={im.name} className="size-12 rounded-md border border-border object-cover" /><button type="button" aria-label="Remove photo" onClick={() => setImages((s) => s.filter((_, j) => j !== i))} className="absolute -right-1.5 -top-1.5 rounded-full border border-border bg-surface p-0.5 shadow-xs"><X className="size-3" /></button></span>)}
            </div>
            <div className="flex items-center gap-2"><label htmlFor="cap-src" className="text-xs font-medium text-fg-muted">Came from</label><NativeSelect id="cap-src" className="h-8 w-44 text-[13px]" value={source} onChange={(e) => setSource(e.target.value)}><option value="">Not sure</option>{CAPTURE_SOURCES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect></div>
            {err && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{err}</p>}
            <DialogFooter><Button variant="secondary" onClick={close}>Cancel</Button><Button onClick={read} loading={busy} disabled={!text.trim() && !images.length}><Sparkles /> Read it</Button></DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Button for the Leads page header. Shows only when capture is on and the person can add leads. */
export function CaptureButton() {
  const on = useAiFeature("capture"); const { can } = useAccess(); const [open, setOpen] = React.useState(false);
  if (!on || !can("leads.create")) return null;
  return <><Button variant="soft" onClick={() => setOpen(true)}><Sparkles /> Capture with AI</Button><CaptureDialog open={open} onOpenChange={setOpen} /></>;
}
