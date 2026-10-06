"use client";
import { X } from "lucide-react";
import { Dialog as D } from "radix-ui";
import * as React from "react";
import { cn } from "../lib/cn";
import { Button } from "./button";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({ className, children, title, description, size = "md", hideClose }: {
  className?: string; children: React.ReactNode; title: React.ReactNode; description?: React.ReactNode; size?: "sm" | "md" | "lg" | "xl"; hideClose?: boolean;
}) {
  const w = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" }[size];
  return (
    <D.Portal>
      <D.Overlay className="anim-overlay fixed inset-0 z-50 bg-[var(--overlay)] backdrop-blur-[2px]" />
      <D.Content className={cn("anim-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[min(88vh,820px)] w-[calc(100vw-24px)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-border bg-surface shadow-lg focus:outline-none", w, className)}>
        <div className="flex items-start justify-between gap-4 px-6 pb-2 pt-5">
          <div>
            <D.Title className="text-lg font-semibold tracking-tight">{title}</D.Title>
            {description ? <D.Description className="mt-1 text-sm text-fg-muted">{description}</D.Description> : <D.Description className="sr-only">{typeof title === "string" ? title : "Dialog"}</D.Description>}
          </div>
          {!hideClose && <D.Close asChild><Button variant="ghost" size="icon-sm" aria-label="Close" className="-mr-2 -mt-1"><X /></Button></D.Close>}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6 pt-2">{children}</div>
      </D.Content>
    </D.Portal>
  );
}

export function DialogFooter({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}>{children}</div>;
}
