"use client";
import { AlertTriangle } from "lucide-react";
import * as React from "react";
import { Button } from "./button";
import { Dialog, DialogContent, DialogFooter } from "./dialog";
import { Field, Input, Textarea } from "./input";

/** Destructive-action guard. Optionally requires typing a phrase and/or giving a reason (stored in audit logs). */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "Confirm", tone = "danger", typeToConfirm, requireReason, onConfirm }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description: React.ReactNode; confirmLabel?: string; tone?: "danger" | "primary";
  typeToConfirm?: string; requireReason?: boolean; onConfirm: (ctx: { reason: string; typed: string }) => Promise<unknown> | unknown;
}) {
  const [typed, setTyped] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => { if (open) { setTyped(""); setReason(""); setError(null); } }, [open]);
  const ok = (!typeToConfirm || typed.trim().toLowerCase() === typeToConfirm.toLowerCase()) && (!requireReason || reason.trim().length > 2);
  const go = async () => {
    setBusy(true); setError(null);
    try { await onConfirm({ reason, typed }); onOpenChange(false); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} size="sm" hideClose>
        <div className="flex gap-3">
          <span className={tone === "danger" ? "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-danger-soft text-danger" : "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary"}><AlertTriangle className="size-4" /></span>
          <div className="text-sm text-fg-muted">{description}</div>
        </div>
        {(requireReason || typeToConfirm) && (
          <div className="mt-4 space-y-3">
            {requireReason && <Field label="Reason" hint="Recorded in the audit log."><Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} /></Field>}
            {typeToConfirm && <Field label={<>Type <strong className="font-semibold text-fg">{typeToConfirm}</strong> to confirm</>}><Input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" /></Field>}
          </div>
        )}
        {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={go} disabled={!ok} loading={busy}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
