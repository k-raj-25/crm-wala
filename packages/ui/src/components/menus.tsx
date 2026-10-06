"use client";
import { Check, ChevronDown, ChevronRight } from "lucide-react";
import { DropdownMenu as DM, Popover as P, Select as S, Tabs as T } from "radix-ui";
import * as React from "react";
import { cn } from "../lib/cn";

/* ---------- Dropdown menu ---------- */
export const DropdownMenu = DM.Root;
export const DropdownTrigger = DM.Trigger;
export const DropdownSub = DM.Sub;

const item = "relative flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm outline-none transition-colors data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-surface-hover [&_svg]:size-4 [&_svg]:text-fg-subtle";

export function DropdownContent({ className, align = "end", children, sideOffset = 6, ...p }: DM.DropdownMenuContentProps) {
  return (
    <DM.Portal>
      <DM.Content align={align} sideOffset={sideOffset} className={cn("anim-pop z-[80] min-w-[200px] rounded-lg border border-border bg-surface p-1.5 shadow-lg", className)} {...p}>{children}</DM.Content>
    </DM.Portal>
  );
}
export function DropdownItem({ className, danger, icon, shortcut, children, ...p }: DM.DropdownMenuItemProps & { danger?: boolean; icon?: React.ReactNode; shortcut?: string }) {
  return (
    <DM.Item className={cn(item, danger && "text-danger data-[highlighted]:bg-danger-soft [&_svg]:text-danger", className)} {...p}>
      {icon}<span className="flex-1">{children}</span>{shortcut && <span className="text-xs text-fg-subtle">{shortcut}</span>}
    </DM.Item>
  );
}
export function DropdownCheckItem({ className, children, ...p }: DM.DropdownMenuCheckboxItemProps) {
  return (
    <DM.CheckboxItem className={cn(item, "pl-8", className)} {...p}>
      <DM.ItemIndicator className="absolute left-2.5"><Check className="size-4 text-primary" /></DM.ItemIndicator>{children}
    </DM.CheckboxItem>
  );
}
export const DropdownLabel = ({ children }: { children: React.ReactNode }) => <DM.Label className="px-2.5 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-fg-subtle">{children}</DM.Label>;
export const DropdownSeparator = () => <DM.Separator className="-mx-1.5 my-1.5 h-px bg-border" />;
export function DropdownSubTrigger({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return <DM.SubTrigger className={cn(item, "justify-between")}>{icon}<span className="flex-1">{children}</span><ChevronRight className="!size-3.5" /></DM.SubTrigger>;
}
export function DropdownSubContent({ children }: { children: React.ReactNode }) {
  return <DM.Portal><DM.SubContent sideOffset={6} className="anim-pop z-[80] min-w-[180px] rounded-lg border border-border bg-surface p-1.5 shadow-lg">{children}</DM.SubContent></DM.Portal>;
}

/* ---------- Popover ---------- */
export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverAnchor = P.Anchor;
export function PopoverContent({ className, align = "start", sideOffset = 8, ...p }: P.PopoverContentProps) {
  return <P.Portal><P.Content align={align} sideOffset={sideOffset} className={cn("anim-pop z-[80] rounded-lg border border-border bg-surface p-4 shadow-lg focus:outline-none", className)} {...p} /></P.Portal>;
}

/* ---------- Select ---------- */
export type Option = { value: string; label: React.ReactNode; hint?: string };
export function Select({ value, onValueChange, options, placeholder = "Select…", className, disabled, id, invalid, size = "md" }: {
  value?: string | null; onValueChange: (v: string) => void; options: Option[]; placeholder?: string; className?: string; disabled?: boolean; id?: string; invalid?: boolean; size?: "sm" | "md";
}) {
  return (
    <S.Root value={value ?? undefined} onValueChange={onValueChange} disabled={disabled}>
      <S.Trigger id={id} aria-invalid={invalid || undefined}
        className={cn("flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface px-3 text-left text-sm shadow-xs transition-[border-color,box-shadow] hover:border-border-strong focus:border-primary focus:outline-none focus:ring-4 focus:ring-[var(--ring)] disabled:opacity-60 data-[placeholder]:text-fg-subtle aria-[invalid=true]:border-danger", size === "sm" ? "h-8 text-[13px]" : "h-9", className)}>
        <S.Value placeholder={placeholder} /><S.Icon><ChevronDown className="size-4 text-fg-subtle" /></S.Icon>
      </S.Trigger>
      <S.Portal>
        <S.Content position="popper" sideOffset={6} className="anim-pop z-[90] max-h-72 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-border bg-surface p-1.5 shadow-lg">
          <S.Viewport>
            {options.map((o) => (
              <S.Item key={o.value} value={o.value} className="relative flex cursor-pointer select-none items-center rounded-md py-2 pl-8 pr-3 text-sm outline-none data-[highlighted]:bg-surface-hover">
                <S.ItemIndicator className="absolute left-2.5"><Check className="size-4 text-primary" /></S.ItemIndicator>
                <S.ItemText>{o.label}</S.ItemText>{o.hint && <span className="ml-auto pl-3 text-xs text-fg-subtle">{o.hint}</span>}
              </S.Item>
            ))}
          </S.Viewport>
        </S.Content>
      </S.Portal>
    </S.Root>
  );
}

/* ---------- Tabs ---------- */
export const Tabs = T.Root;
export function TabsList({ className, ...p }: T.TabsListProps) {
  return <T.List className={cn("hide-scrollbar flex gap-1 overflow-x-auto border-b border-border", className)} {...p} />;
}
export function TabsTrigger({ className, children, count, ...p }: T.TabsTriggerProps & { count?: number }) {
  return (
    <T.Trigger className={cn("relative -mb-px flex shrink-0 items-center gap-2 whitespace-nowrap border-b-2 border-transparent px-3 py-2.5 text-sm font-medium text-fg-muted outline-none transition-colors hover:text-fg data-[state=active]:border-primary data-[state=active]:text-fg", className)} {...p}>
      {children}{count !== undefined && count > 0 && <span className="rounded-full bg-bg-subtle px-1.5 text-xs text-fg-muted">{count}</span>}
    </T.Trigger>
  );
}
export const TabsContent = ({ className, ...p }: T.TabsContentProps) => <T.Content className={cn("outline-none animate-fade-in", className)} {...p} />;

/* ---------- Segmented control ---------- */
export function Segmented<V extends string>({ value, onChange, options, size = "md", className }: { value: V; onChange: (v: V) => void; options: { value: V; label: React.ReactNode; icon?: React.ReactNode }[]; size?: "sm" | "md"; className?: string }) {
  return (
    <div role="tablist" className={cn("inline-flex rounded-md bg-bg-subtle p-0.5", className)}>
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={cn("flex items-center gap-1.5 rounded-[7px] px-3 font-medium transition-all [&_svg]:size-3.5", size === "sm" ? "h-7 text-xs" : "h-8 text-[13px]", value === o.value ? "bg-surface text-fg shadow-xs" : "text-fg-muted hover:text-fg")}>
          {o.icon}{o.label}
        </button>
      ))}
    </div>
  );
}
