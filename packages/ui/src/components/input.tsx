"use client";
import * as React from "react";
import { cn } from "../lib/cn";
import { Select } from "./menus";
import type { Option } from "./menus";

const base =
  "w-full rounded-md border border-border bg-surface px-3 text-sm text-fg shadow-xs transition-[border-color,box-shadow] duration-150 placeholder:text-fg-subtle hover:border-border-strong focus:border-primary focus:outline-none focus:ring-4 focus:ring-[var(--ring)] disabled:cursor-not-allowed disabled:bg-bg-subtle disabled:opacity-70 aria-[invalid=true]:border-danger aria-[invalid=true]:focus:ring-[color-mix(in_srgb,var(--danger)_25%,transparent)]";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { icon?: React.ReactNode; invalid?: boolean }>(
  ({ className, icon, invalid, ...props }, ref) => (
    <div className="relative w-full">
      {icon && <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle [&_svg]:size-4">{icon}</span>}
      <input ref={ref} aria-invalid={invalid || undefined} className={cn(base, "h-9", icon && "pl-9", className)} {...props} />
    </div>
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }>(({ className, invalid, ...props }, ref) => (
  <textarea ref={ref} aria-invalid={invalid || undefined} className={cn(base, "min-h-[84px] resize-y py-2 leading-relaxed", className)} {...props} />
));
Textarea.displayName = "Textarea";

const EMPTY = "__empty__"; // Radix Select forbids an empty-string item value

function flattenOptions(children: React.ReactNode): Option[] {
  const out: Option[] = [];
  const walk = (nodes: React.ReactNode) => React.Children.forEach(nodes, (c) => {
    if (!React.isValidElement(c)) return;
    const props = c.props as { value?: string | number; disabled?: boolean; children?: React.ReactNode };
    if (c.type === "option") {
      const label = props.children;
      out.push({ value: String(props.value ?? (typeof label === "string" ? label : React.Children.toArray(label).join(""))), label, disabled: props.disabled });
    } else walk(props.children); // fragments, groups, mapped arrays
  });
  walk(children);
  return out;
}

type NativeSelectProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "size" | "onChange" | "value" | "defaultValue"> & {
  invalid?: boolean; size?: "sm" | "md"; defaultOpen?: boolean; value?: string | number | null; defaultValue?: string | number; onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
};

/** Drop-in for a native <select> (same <option> children, same onChange(e.target.value)) that renders the app's own dropdown,
 *  so every select looks and behaves the same, in light and dark. Works controlled, uncontrolled and with react-hook-form's register(). */
export const NativeSelect = React.forwardRef<HTMLInputElement, NativeSelectProps>(function NativeSelect(
  { className, invalid, children, value, defaultValue, onChange, name, disabled, id, autoFocus, size, onKeyDown, defaultOpen, ...rest }, ref) {
  const options = flattenOptions(children);
  const [inner, setInner] = React.useState(String(defaultValue ?? ""));
  const current = value !== undefined ? String(value ?? "") : inner;
  const known = options.some((o) => o.value === current);
  const emit = (v: string) => {
    if (value === undefined) setInner(v);
    onChange?.({ target: { value: v, name: name ?? "" }, currentTarget: { value: v, name: name ?? "" } } as unknown as React.ChangeEvent<HTMLSelectElement>);
  };
  return (
    <>
      <Select id={id} className={className} invalid={invalid} disabled={disabled} autoFocus={autoFocus} defaultOpen={defaultOpen} size={size} ariaLabel={rest["aria-label"]}
        onKeyDown={onKeyDown as React.KeyboardEventHandler<HTMLButtonElement> | undefined}
        value={known ? (current === "" ? EMPTY : current) : undefined} onValueChange={(v) => emit(v === EMPTY ? "" : v)}
        options={options.map((o) => ({ ...o, value: o.value === "" ? EMPTY : o.value }))} />
      {(name || ref) && <input type="hidden" ref={ref} name={name} value={current} readOnly />}
    </>
  );
});
NativeSelect.displayName = "NativeSelect";

export function Label({ className, children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1.5 block text-[13px] font-medium text-fg", className)} {...props}>{children}</label>;
}

/** Label + control + hint/error, wired for a11y via aria-describedby. */
export function Field({ label, hint, error, required, children, className, htmlFor }: {
  label?: React.ReactNode; hint?: React.ReactNode; error?: string; required?: boolean; children: React.ReactNode; className?: string; htmlFor?: string;
}) {
  const id = React.useId();
  const fid = htmlFor ?? id;
  const child = React.isValidElement(children)
    ? React.cloneElement(children as React.ReactElement<Record<string, unknown>>, { id: fid, invalid: !!error || undefined, "aria-describedby": error ? `${fid}-err` : hint ? `${fid}-hint` : undefined })
    : children;
  return (
    <div className={className}>
      {label && <Label htmlFor={fid}>{label}{required && <span className="ml-0.5 text-danger" aria-hidden>*</span>}</Label>}
      {child}
      {error ? <p id={`${fid}-err`} role="alert" className="mt-1.5 text-xs text-danger">{error}</p> : hint ? <p id={`${fid}-hint`} className="mt-1.5 text-xs text-fg-subtle">{hint}</p> : null}
    </div>
  );
}
