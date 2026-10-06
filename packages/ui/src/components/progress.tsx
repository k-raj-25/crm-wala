import { cn } from "../lib/cn";

export function Progress({ value, max = 100, tone = "primary", className, label }: { value: number; max?: number; tone?: "primary" | "success" | "warning" | "danger"; className?: string; label?: string }) {
  const pct = Math.max(0, Math.min(100, max ? (value / max) * 100 : 0));
  const color = { primary: "bg-primary", success: "bg-success", warning: "bg-warning", danger: "bg-danger" }[tone];
  return (
    <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label} className={cn("h-1.5 w-full overflow-hidden rounded-full bg-bg-subtle", className)}>
      <div className={cn("h-full rounded-full transition-[width] duration-500 ease-out", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}
