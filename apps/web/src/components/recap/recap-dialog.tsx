"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Camera, Copy, ExternalLink, Hand, ImagePlus, MessageCircle, Plus, Search, X } from "lucide-react";
import * as React from "react";
import { ApiError, Button, Dialog, DialogContent, DialogFooter, Field, Input, Skeleton, Spinner, Textarea, timeAgo, useDebounce, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useCompare } from "@/lib/compare";
import type { Unit } from "@/lib/realestate";
import { flatWhere } from "../compare/flat-picker";

export type Recap = {
  id: string; url: string; meeting_id: string | null; message: string | null; sent_at: string | null; sent_via: string | null; views: number; last_viewed_at: string | null;
  flats: { id: string; number: string; where: string }[]; photos: { id: string; filename: string }[]; buyer: { type: string; id: string; name: string } | null;
  hold_requests: { unit_id: string; at: string; name: string | null; note: string | null }[];
};
type Target = { meeting_id?: string; lead_id?: string; contact_id?: string; deal_id?: string };
const MAX_FLATS = 6, MAX_PHOTOS = 12;

const fileUrl = (r: Recap, id: string) => `/api/v1/public/recaps/${r.url.split("/v/")[1]}/files/${id}`;

/** Phone photos are 3–8 MB; the family opens the page on mobile data, so shrink to 1600px JPEG before uploading. */
async function shrink(f: File): Promise<File> {
  if (!f.type.startsWith("image/") || f.type === "image/gif") return f;
  try {
    const bmp = await createImageBitmap(f);
    const scale = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas"); c.width = Math.round(bmp.width * scale); c.height = Math.round(bmp.height * scale);
    c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise<Blob | null>((ok) => c.toBlob(ok, "image/jpeg", 0.82));
    return blob && blob.size < f.size ? new File([blob], f.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : f;
  } catch { return f; }
}

/** Build and send the visit recap: flats seen, photos, a note, then one tap to WhatsApp. Changes save as you go. */
export function RecapDialog({ open, onOpenChange, target }: { open: boolean; onOpenChange: (o: boolean) => void; target: Target }) {
  const toast = useToast(); const qc = useQueryClient(); const tray = useCompare();
  const [rec, setRec] = React.useState<Recap | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState("");
  const [q, setQ] = React.useState(""); const dq = useDebounce(q, 200);
  const [found, setFound] = React.useState<Unit[]>([]);
  const [uploading, setUploading] = React.useState(0);
  const [sending, setSending] = React.useState(false);
  const [note, setNote] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const key = JSON.stringify(target);

  React.useEffect(() => {
    if (!open) return;
    setRec(null); setErr(null); setNote(null); setQ("");
    api.post<Recap>("/api/v1/visit-recaps", target).then((r) => { setRec(r); setMessage(r.message ?? ""); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Couldn't start the recap. Please try again."));
  }, [open, key]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (!open || !dq.trim()) { setFound([]); return; }
    let live = true;
    api.page<Unit>("/api/v1/units", { q: dq, per_page: 8, sort: "floor,number" }).then((p) => live && setFound(p.data)).catch(() => {});
    return () => { live = false; };
  }, [dq, open]);

  const save = async (patch: Partial<{ unit_ids: string[]; photo_ids: string[]; message: string }>) => {
    if (!rec) return null;
    try { const r = await api.patch<Recap>(`/api/v1/visit-recaps/${rec.id}`, patch); setRec(r); return r; }
    catch (e) { toast.error("Couldn't save", (e as Error).message); return null; }
  };
  const flatIds = rec?.flats.map((f) => f.id) ?? [];
  const addFlats = (ids: string[]) => {
    const next = [...new Set([...flatIds, ...ids])];
    if (next.length > MAX_FLATS) toast.error(`A recap can show up to ${MAX_FLATS} flats`);
    save({ unit_ids: next.slice(0, MAX_FLATS) }); setQ("");
  };
  const fromTray = tray.filter((f) => !flatIds.includes(f.id));

  const upload = async (files: FileList | null) => {
    if (!rec || !files?.length) return;
    const room = MAX_PHOTOS - rec.photos.length;
    const list = Array.from(files).slice(0, room);
    if (files.length > room) toast.error(`Up to ${MAX_PHOTOS} photos`, "The extra ones weren't added.");
    setUploading(list.length);
    const ids: string[] = [];
    for (const f of list) {
      try {
        const fd = new FormData(); fd.append("file", await shrink(f));
        if (rec.buyer) fd.append(`${rec.buyer.type}_id`, rec.buyer.id);
        ids.push((await api.upload<{ id: string }>("/api/v1/files", fd)).id);
      } catch (e) { toast.error(`Couldn't upload ${f.name}`, (e as Error).message); }
      setUploading((n) => n - 1);
    }
    if (ids.length) await save({ photo_ids: [...rec.photos.map((p) => p.id), ...ids] });
    if (fileRef.current) fileRef.current.value = "";
  };

  const send = async () => {
    if (!rec) return;
    // open the WhatsApp tab inside the click, or the browser blocks it as a popup; closed again if the CRM sends it itself
    const win = window.open("about:blank", "_blank");
    setSending(true); setNote(null);
    try {
      if (message !== (rec.message ?? "")) await api.patch(`/api/v1/visit-recaps/${rec.id}`, { message });
      const r = await api.post<{ status: "sent" | "link"; reason?: string; whatsapp_url?: string; recap: Recap }>(`/api/v1/visit-recaps/${rec.id}/send`);
      setRec(r.recap);
      qc.invalidateQueries({ queryKey: ["timeline"] }); qc.invalidateQueries({ queryKey: ["visit-recaps"] });
      if (r.status === "sent") { win?.close(); toast.success(`Recap sent on WhatsApp to ${r.recap.buyer?.name ?? "the buyer"}`); onOpenChange(false); return; }
      if (win && r.whatsapp_url) win.location.href = r.whatsapp_url; else if (r.whatsapp_url) window.location.href = r.whatsapp_url;
      setNote(r.reason ?? null);
      toast.success("WhatsApp is open with the recap link");
    } catch (e) {
      win?.close();
      setErr(e instanceof ApiError ? e.message : "Couldn't send. Please try again.");
    } finally { setSending(false); }
  };

  const copy = async () => { if (!rec) return; try { await navigator.clipboard.writeText(rec.url); toast.success("Link copied"); } catch { toast.error("Couldn't copy", rec.url); } };
  const heldFlat = (id: string) => rec?.flats.find((f) => f.id === id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" title={rec?.buyer ? `Visit recap for ${rec.buyer.name}` : "Visit recap"}
        description="One WhatsApp link with the flats they saw, your photos, prices, a comparison and a Hold button. Their family can open it at home too.">
        {!rec ? (err ? <p role="alert" className="text-sm text-danger">{err}</p> : <div className="space-y-3"><Skeleton className="h-10 w-full" /><Skeleton className="h-24 w-full" /><Skeleton className="h-20 w-full" /></div>) : (
          <div className="space-y-5">
            {(rec.views > 0 || rec.hold_requests.length > 0) && (
              <div className="space-y-1.5 rounded-lg bg-bg-subtle p-3 text-[13px]">
                {rec.views > 0 && <p>Opened {rec.views} time{rec.views === 1 ? "" : "s"}{rec.last_viewed_at ? `, last ${timeAgo(rec.last_viewed_at)}` : ""}.</p>}
                {rec.hold_requests.map((h) => <p key={h.at} className="flex items-start gap-1.5 font-medium text-warning"><Hand className="mt-0.5 size-3.5 shrink-0" />{h.name ?? "They"} asked to hold Flat {heldFlat(h.unit_id)?.number ?? ""} {timeAgo(h.at)}{h.note ? `: “${h.note}”` : ""}</p>)}
              </div>
            )}

            <Field label="Flats they saw" hint={rec.flats.length ? undefined : "Add the flats you showed. They get prices and a side-by-side comparison."}>
              <div className="space-y-2">
                {rec.flats.length > 0 && <ul className="flex flex-wrap gap-2">{rec.flats.map((f) => (
                  <li key={f.id} className="flex items-center gap-1.5 rounded-lg border border-border bg-surface py-1 pl-2.5 pr-1 text-sm"><span className="font-medium">Flat {f.number}</span><span className="text-xs text-fg-muted">{f.where}</span>
                    <Button variant="ghost" size="icon-xs" aria-label={`Remove flat ${f.number}`} onClick={() => save({ unit_ids: flatIds.filter((x) => x !== f.id) })}><X /></Button></li>))}</ul>}
                {rec.flats.length < MAX_FLATS && (
                  <div className="relative">
                    <Input icon={<Search />} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Add a flat: number or size, e.g. 801 or 3 BHK" aria-label="Search flats" />
                    {found.length > 0 && <ul className="absolute inset-x-0 top-full z-20 mt-1 max-h-60 overflow-auto rounded-lg border border-border bg-surface shadow-lg">{found.map((u) => (
                      <li key={u.id}><button type="button" disabled={flatIds.includes(u.id)} onClick={() => addFlats([u.id])} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-surface-hover disabled:opacity-50">
                        <span><b>Flat {u.number}</b> <span className="text-fg-muted">{u.bhk ?? ""}</span></span><span className="truncate text-xs text-fg-muted">{flatWhere(u)}</span></button></li>))}</ul>}
                  </div>
                )}
                {fromTray.length > 0 && rec.flats.length < MAX_FLATS && <Button variant="ghost" size="xs" onClick={() => addFlats(fromTray.map((f) => f.id))}><Plus /> Add {fromTray.length} flat{fromTray.length === 1 ? "" : "s"} from your comparison list</Button>}
              </div>
            </Field>

            <Field label="Photos you took" hint="The balcony view, the kitchen, the sample flat. They're shrunk for mobile data.">
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                {rec.photos.map((p) => (
                  <div key={p.id} className="group relative aspect-square overflow-hidden rounded-lg border border-border bg-bg-subtle">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={fileUrl(rec, p.id)} alt={p.filename} className="size-full object-cover" />
                    <button type="button" aria-label="Remove photo" onClick={() => save({ photo_ids: rec.photos.filter((x) => x.id !== p.id).map((x) => x.id) })}
                      className="absolute right-1 top-1 flex size-6 items-center justify-center rounded-full bg-black/60 text-white"><X className="size-3.5" /></button>
                  </div>))}
                {Array.from({ length: uploading }).map((_, i) => <div key={`u${i}`} className="flex aspect-square items-center justify-center rounded-lg border border-dashed border-border"><Spinner className="size-5 text-fg-muted" /></div>)}
                {rec.photos.length + uploading < MAX_PHOTOS && (
                  <button type="button" onClick={() => fileRef.current?.click()} className="flex aspect-square flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-border-strong text-xs text-fg-muted hover:bg-surface-hover">
                    {rec.photos.length ? <ImagePlus className="size-5" /> : <Camera className="size-5" />}{rec.photos.length ? "Add" : "Add photos"}
                  </button>
                )}
              </div>
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={(e) => upload(e.target.files)} />
            </Field>

            <Field label="Your message" hint="The link to the recap is added at the end.">
              <Textarea rows={5} value={message} onChange={(e) => setMessage(e.target.value)} onBlur={() => message !== (rec.message ?? "") && save({ message })} maxLength={2000} />
            </Field>
            {note && <p className="rounded-lg bg-warning-soft p-3 text-[13px] text-fg">{note}</p>}
            {err && <p role="alert" className="text-sm text-danger">{err}</p>}
          </div>
        )}
        <DialogFooter className="sm:items-center">
          {rec && <div className="flex gap-1 sm:mr-auto">
            <Button variant="ghost" size="sm" onClick={copy}><Copy /> Copy link</Button>
            <Button variant="ghost" size="sm" asChild><a href={`${rec.url}?preview=1`} target="_blank" rel="noreferrer"><ExternalLink /> Preview</a></Button>
          </div>}
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Close</Button>
          <Button onClick={send} loading={sending} disabled={!rec || sending || uploading > 0 || (!rec.flats.length && !rec.photos.length)}><MessageCircle /> {rec?.sent_at ? "Send again" : "Send on WhatsApp"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
