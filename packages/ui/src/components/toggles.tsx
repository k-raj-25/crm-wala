"use client";
import { Check, Minus } from "lucide-react";
import { Checkbox as C, Switch as S } from "radix-ui";
import * as React from "react";
import { cn } from "../lib/cn";

export function Checkbox({ checked, onCheckedChange, className, ...p }: { checked: boolean | "indeterminate"; onCheckedChange?: (c: boolean) => void; className?: string; "aria-label"?: string; disabled?: boolean; id?: string }) {
  return (
    <C.Root checked={checked} onCheckedChange={(v) => onCheckedChange?.(v === true)} className={cn("flex size-[18px] shrink-0 items-center justify-center rounded-[5px] border border-border-strong bg-surface transition-all hover:border-primary data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary", className)} {...p}>
      <C.Indicator className="text-primary-fg">{checked === "indeterminate" ? <Minus className="size-3" strokeWidth={3} /> : <Check className="size-3" strokeWidth={3} />}</C.Indicator>
    </C.Root>
  );
}

export function Switch({ checked, onCheckedChange, ...p }: { checked: boolean; onCheckedChange: (c: boolean) => void; disabled?: boolean; "aria-label"?: string; id?: string }) {
  return (
    <S.Root checked={checked} onCheckedChange={onCheckedChange} className="relative h-5 w-9 shrink-0 rounded-full bg-border-strong transition-colors data-[state=checked]:bg-primary disabled:opacity-50" {...p}>
      <S.Thumb className="block size-4 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform duration-150 data-[state=checked]:translate-x-[18px]" />
    </S.Root>
  );
}
