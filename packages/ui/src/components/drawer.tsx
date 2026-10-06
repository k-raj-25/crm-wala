"use client";
import { X } from "lucide-react";
import { Dialog as D } from "radix-ui";
import * as React from "react";
import { cn } from "../lib/cn";
import { useMediaQuery } from "../lib/hooks";
import { Button } from "./button";

/** Right-side drawer on desktop, bottom sheet on mobile. Used for quick create / quick edit so users keep their context. */
export function Drawer({ open, onOpenChange, title, description, children, footer, width = 480 }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: React.ReactNode; description?: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode; width?: number;
}) {
  const mobile = useMediaQuery("(max-width: 767px)");
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="anim-overlay fixed inset-0 z-50 bg-[var(--overlay)]" />
        <D.Content
          className={cn("fixed z-50 flex flex-col bg-surface shadow-lg focus:outline-none", mobile ? "anim-sheet inset-x-0 bottom-0 max-h-[92vh] rounded-t-2xl border-t border-border" : "anim-drawer inset-y-0 right-0 w-full border-l border-border")}
          style={mobile ? undefined : { maxWidth: width }}>
          <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
            <div className="min-w-0">
              <D.Title className="truncate text-lg font-semibold tracking-tight">{title}</D.Title>
              {description ? <D.Description className="mt-0.5 text-sm text-fg-muted">{description}</D.Description> : <D.Description className="sr-only">Panel</D.Description>}
            </div>
            <D.Close asChild><Button variant="ghost" size="icon-sm" aria-label="Close"><X /></Button></D.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
          {footer && <div className="flex items-center justify-end gap-2 border-t border-border bg-surface-2 px-6 py-3.5">{footer}</div>}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
