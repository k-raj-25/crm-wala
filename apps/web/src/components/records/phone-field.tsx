"use client";
import { Eye, Lock, Phone } from "lucide-react";
import * as React from "react";
import { Button, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { InlineField } from "./inline-field";

/** The server masks numbers (`+91 ••••• •••10`) for members who can't see them. */
export const isMasked = (v: unknown): boolean => typeof v === "string" && v.includes("•");

/** A phone number in a list or card: a call link when it's real, plain text with a lock when it's hidden. */
export function PhoneText({ value, className }: { value: string | null | undefined; className?: string }) {
  if (!value) return null;
  if (isMasked(value)) return <span className={className} title="Hidden by your workspace owner"><Lock className="mr-1 inline size-3 align-[-1px]" />{value}</span>;
  return <a href={`tel:${value}`} className={className}><Phone className="mr-1 inline size-3 align-[-1px]" />{value}</a>;
}

/** The Phone row on a record page. Hidden numbers can't be edited; members allowed to reveal get a logged "Show" button. */
export function PhoneField({ plural, id, value, editable, onSave }: { plural: "leads" | "contacts" | "companies"; id: string; value: string | null; editable: boolean; onSave: (v: string | null) => Promise<unknown> | unknown }) {
  const { can } = useAccess(); const toast = useToast();
  const [shown, setShown] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => setShown(null), [id, value]);
  if (!isMasked(value)) return <InlineField label="Phone" type="tel" value={value} onSave={onSave} editable={editable} />;
  const reveal = async () => {
    setBusy(true);
    try { setShown((await api.post<{ phone: string | null }>(`/api/v1/${plural}/${id}/reveal-phone`, {})).phone); }
    catch (e) { toast.error("Couldn't show the number", (e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="grid grid-cols-[110px_1fr] items-center gap-3 py-2 text-sm">
      <dt className="text-[13px] text-fg-muted">Phone</dt>
      <dd className="flex min-w-0 items-center gap-2">
        {shown ? <a href={`tel:${shown}`} className="tabular hover:text-primary">{shown}</a>
          : <span className="tabular text-fg-muted" title="Phone numbers are hidden by your workspace owner. Use WhatsApp or log a call from here."><Lock className="mr-1 inline size-3 align-[-1px]" />{value}</span>}
        {!shown && can("phones.reveal") && <Button size="xs" variant="ghost" loading={busy} onClick={reveal} title="Your workspace owner can see who viewed each number"><Eye /> Show</Button>}
      </dd>
    </div>
  );
}
