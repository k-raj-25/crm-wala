import { cn } from "../lib/cn";

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return <kbd className={cn("inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-bg-subtle px-1 font-sans text-[11px] font-medium text-fg-muted", className)}>{children}</kbd>;
}
