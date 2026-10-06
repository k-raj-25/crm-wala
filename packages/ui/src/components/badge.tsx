import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "../lib/cn";

const badge = cva("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium leading-5", {
  variants: {
    tone: {
      neutral: "bg-bg-subtle text-fg-muted",
      primary: "bg-primary-soft text-primary",
      success: "bg-success-soft text-success",
      warning: "bg-warning-soft text-warning",
      danger: "bg-danger-soft text-danger",
      info: "bg-info-soft text-info",
      outline: "border border-border text-fg-muted",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, dot, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge> & { dot?: boolean }) {
  return (
    <span className={cn(badge({ tone }), className)} {...props}>
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {props.children}
    </span>
  );
}

/** Colored chip with a user-defined hex (tags, statuses). Keeps text readable via color-mix. */
export function ColorChip({ color = "#6366f1", children, className }: { color?: string | null; children: React.ReactNode; className?: string }) {
  const c = color || "#6366f1";
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", className)}
      style={{ background: `color-mix(in srgb, ${c} 14%, transparent)`, color: `color-mix(in srgb, ${c} 75%, var(--fg))` }}>
      <span className="size-1.5 rounded-full" style={{ background: c }} aria-hidden />{children}
    </span>
  );
}
