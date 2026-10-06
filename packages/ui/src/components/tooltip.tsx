"use client";
import { Tooltip as T } from "radix-ui";
import * as React from "react";
import { cn } from "../lib/cn";
import { Kbd } from "./kbd";

export const TooltipProvider = ({ children }: { children: React.ReactNode }) => <T.Provider delayDuration={250} skipDelayDuration={150}>{children}</T.Provider>;

export function Tooltip({ content, shortcut, children, side = "top" }: { content: React.ReactNode; shortcut?: string; children: React.ReactElement; side?: "top" | "right" | "bottom" | "left" }) {
  if (!content) return children;
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content side={side} sideOffset={6} className={cn("anim-pop z-[100] flex items-center gap-2 rounded-md bg-fg px-2.5 py-1.5 text-xs font-medium text-bg shadow-md")}>
          {content}{shortcut && <Kbd className="border-white/20 bg-white/10 text-inherit">{shortcut}</Kbd>}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
