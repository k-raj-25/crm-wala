import * as React from "react";
import { cn } from "../lib/cn";
import { initials } from "../lib/format";

const HUES = [243, 199, 160, 28, 330, 270, 12, 190, 90, 300];
function hue(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0; return HUES[h % HUES.length]; }

export function Avatar({ name, src, size = 32, className, square }: { name?: string | null; src?: string | null; size?: number; className?: string; square?: boolean }) {
  const n = name ?? "";
  const h = hue(n || "x");
  return (
    <span className={cn("inline-flex shrink-0 select-none items-center justify-center overflow-hidden font-semibold", square ? "rounded-lg" : "rounded-full", className)}
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.38), background: `oklch(0.93 0.05 ${h})`, color: `oklch(0.42 0.14 ${h})` }} title={n} aria-label={n || undefined}>
      {src ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={src} alt="" className="size-full object-cover" /> : initials(n)}
    </span>
  );
}

export function AvatarStack({ people, max = 4, size = 28 }: { people: { name?: string | null; avatar_url?: string | null }[]; max?: number; size?: number }) {
  const shown = people.slice(0, max);
  return (
    <div className="flex -space-x-2">
      {shown.map((p, i) => <Avatar key={i} name={p.name} src={p.avatar_url} size={size} className="ring-2 ring-surface" />)}
      {people.length > max && <span className="inline-flex items-center justify-center rounded-full bg-bg-subtle text-[11px] font-medium text-fg-muted ring-2 ring-surface" style={{ width: size, height: size }}>+{people.length - max}</span>}
    </div>
  );
}
