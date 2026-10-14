"use client";
import { Copy, Send, Sparkles } from "lucide-react";
import * as React from "react";
import { Button, Dialog, DialogContent, DialogFooter, Field, Input, NativeSelect, Segmented, Textarea, useToast } from "@crm/ui";
import { api } from "@/lib/api";

type Kind = "description" | "whatsapp" | "portal";
const KINDS: { value: Kind; label: string }[] = [{ value: "description", label: "Description" }, { value: "whatsapp", label: "WhatsApp" }, { value: "portal", label: "Portal listing" }];
const LANGS = ["English", "Hindi", "Hinglish", "Marathi", "Gujarati", "Tamil", "Telugu", "Kannada", "Bengali", "Punjabi"];

/** Writes a brochure description, WhatsApp broadcast or 99acres-style listing for a project or a flat. */
export function ListingWriter({ open, onOpenChange, projectId, unitId, label }: { open: boolean; onOpenChange: (o: boolean) => void; projectId?: string | null; unitId?: string | null; label?: string }) {
  const toast = useToast();
  const [kind, setKind] = React.useState<Kind>("whatsapp"); const [lang, setLang] = React.useState("English"); const [notes, setNotes] = React.useState("");
  const [text, setText] = React.useState(""); const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { setText(""); }, [projectId, unitId, kind]);
  const generate = async () => {
    setBusy(true);
    try { const r = await api.post<{ text: string }>("/api/v1/ai/listing", { kind, project_id: projectId || undefined, unit_id: unitId || undefined, language: lang.toLowerCase(), notes: notes.trim() || undefined }); setText(r.text); }
    catch (e) { toast.error("Couldn't write the listing", (e as Error).message); } finally { setBusy(false); }
  };
  const copy = async () => { try { await navigator.clipboard.writeText(text); toast.success("Copied"); } catch { toast.error("Couldn't copy. Select the text and copy it."); } };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Write listing</span>} description={label ? `For ${label}` : "Ready-to-share text from your project details"}>
        <div className="space-y-4">
          <Segmented value={kind} onChange={setKind} options={KINDS} />
          <div className="grid gap-3 sm:grid-cols-[180px_1fr]">
            <Field label="Language"><NativeSelect value={lang} onChange={(e) => setLang(e.target.value)}>{LANGS.map((l) => <option key={l}>{l}</option>)}</NativeSelect></Field>
            <Field label="Anything to highlight? (optional)"><Input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} placeholder="Highlight metro, Vastu" /></Field>
          </div>
          {text ? <Field label="Your text (edit freely)"><Textarea rows={kind === "whatsapp" ? 8 : 10} value={text} onChange={(e) => setText(e.target.value)} /></Field>
            : <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-fg-muted">{busy ? "Writing…" : "Pick the kind and language, then press Generate."}</p>}
        </div>
        <DialogFooter>
          {text && <Button variant="secondary" onClick={copy}><Copy /> Copy</Button>}
          {text && kind === "whatsapp" && <Button variant="secondary" asChild><a href={`https://wa.me/?text=${encodeURIComponent(text)}`} target="_blank" rel="noreferrer noopener"><Send /> Share on WhatsApp</a></Button>}
          <Button loading={busy} onClick={generate}><Sparkles /> {text ? "Write again" : "Generate"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
