"use client";
import { Check, Pencil, X } from "lucide-react";
import * as React from "react";
import { Input, NativeSelect, Textarea, cn } from "@crm/ui";

/** Click-to-edit value. Saves on Enter/blur, cancels on Esc. */
export function InlineField({ label, value, display, onSave, type = "text", options, editable = true, multiline, placeholder = "Add…", mono }: {
  label: string; value: string | number | null | undefined; display?: React.ReactNode; onSave: (v: string | null) => Promise<unknown> | unknown; type?: string; options?: [string, string][]; editable?: boolean; multiline?: boolean; placeholder?: string; mono?: boolean;
}) {
  const [editing, setEditing] = React.useState(false);
  const [v, setV] = React.useState(String(value ?? ""));
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (!editing) setV(String(value ?? "")); }, [value, editing]);
  const commit = async () => {
    if (v === String(value ?? "")) { setEditing(false); return; }
    setBusy(true);
    try { await onSave(v.trim() === "" ? null : v.trim()); setEditing(false); } catch { /* parent toasts; keep editing */ } finally { setBusy(false); }
  };
  const key = (e: React.KeyboardEvent) => { if (e.key === "Escape") { setEditing(false); setV(String(value ?? "")); } if (e.key === "Enter" && !multiline) { e.preventDefault(); commit(); } };
  return (
    <div className="group grid grid-cols-[110px_1fr] items-start gap-3 py-2 text-sm">
      <dt className="pt-1.5 text-[13px] text-fg-muted">{label}</dt>
      <dd className="min-w-0">
        {editing ? (
          <div className="flex items-start gap-1.5">
            {options ? <NativeSelect autoFocus value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={key} disabled={busy}><option value="">—</option>{options.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect>
              : multiline ? <Textarea autoFocus rows={3} value={v} onChange={(e) => setV(e.target.value)} onKeyDown={key} onBlur={commit} disabled={busy} />
              : <Input autoFocus type={type} value={v} onChange={(e) => setV(e.target.value)} onKeyDown={key} onBlur={commit} disabled={busy} className="h-8" />}
            <button onMouseDown={(e) => e.preventDefault()} onClick={commit} aria-label="Save" className="mt-1 rounded p-1 text-success hover:bg-success-soft"><Check className="size-4" /></button>
            <button onMouseDown={(e) => e.preventDefault()} onClick={() => { setEditing(false); setV(String(value ?? "")); }} aria-label="Cancel" className="mt-1 rounded p-1 text-fg-subtle hover:bg-surface-hover"><X className="size-4" /></button>
          </div>
        ) : (
          <button type="button" disabled={!editable} onClick={() => setEditing(true)} className={cn("-mx-2 flex min-h-8 w-[calc(100%+16px)] items-center justify-between gap-2 rounded-md px-2 py-1 text-left transition-colors", editable && "hover:bg-bg-subtle")} aria-label={`Edit ${label}`}>
            <span className={cn("min-w-0 break-words", !value && !display && "text-fg-subtle", mono && "tabular", multiline && "whitespace-pre-line")}>{display ?? (value || placeholder)}</span>
            {editable && <Pencil className="size-3 shrink-0 text-fg-subtle opacity-0 transition-opacity group-hover:opacity-100" />}
          </button>
        )}
      </dd>
    </div>
  );
}
