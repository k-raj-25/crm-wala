"use client";
import * as React from "react";
import { cn } from "../lib/cn";

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

export const NativeSelect = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }>(({ className, invalid, children, ...props }, ref) => (
  <select ref={ref} aria-invalid={invalid || undefined} className={cn(base, "h-9 appearance-none bg-[length:16px] bg-[right_10px_center] bg-no-repeat pr-8", className)}
    style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23878aa0' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }} {...props}>
    {children}
  </select>
));
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
