"use client";
import { Building2, CalendarPlus, CheckSquare, ChevronDown, Handshake, Phone, Plus, StickyNote, UserRound, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button, Drawer, DropdownContent, DropdownItem, DropdownMenu, DropdownTrigger, Tooltip } from "@crm/ui";
import { FORMS, RecordForm } from "../forms/record-form";
import type { CreateKind } from "./ui-context";
import { useUI } from "./ui-context";
import { useAccess } from "@/lib/queries";

export const CREATE_ITEMS: { kind: CreateKind; label: string; icon: React.ElementType; perm: string; key: string }[] = [
  { kind: "lead", label: "New Lead", icon: Users, perm: "leads.create", key: "L" }, { kind: "contact", label: "New Contact", icon: UserRound, perm: "contacts.create", key: "C" },
  { kind: "company", label: "New Company", icon: Building2, perm: "companies.create", key: "O" }, { kind: "deal", label: "New Deal", icon: Handshake, perm: "deals.create", key: "D" },
  { kind: "task", label: "New Task", icon: CheckSquare, perm: "tasks.create", key: "T" }, { kind: "meeting", label: "New Meeting", icon: CalendarPlus, perm: "meetings.create", key: "M" },
  { kind: "note", label: "New Note", icon: StickyNote, perm: "notes.create", key: "N" }, { kind: "call", label: "Log Call", icon: Phone, perm: "meetings.create", key: "P" },
];

export function QuickCreateMenu({ variant = "button" }: { variant?: "button" | "fab" }) {
  const ui = useUI(); const { can } = useAccess();
  const items = CREATE_ITEMS.filter((i) => can(i.perm));
  if (!items.length) return null;
  return (
    <DropdownMenu>
      <Tooltip content="Quick create" shortcut="C" side="bottom">
        <DropdownTrigger asChild>
          {variant === "fab" ? <Button size="icon" className="size-14 rounded-full shadow-lg" aria-label="Quick create"><Plus className="!size-6" /></Button> : <Button aria-label="Quick create"><Plus /> <span className="hidden sm:inline">Create</span><ChevronDown className="hidden !size-3.5 opacity-70 sm:block" /></Button>}
        </DropdownTrigger>
      </Tooltip>
      <DropdownContent align="end" className="w-56">{items.map((i) => <DropdownItem key={i.kind} icon={<i.icon />} onSelect={() => ui.openCreate(i.kind)}>{i.label}</DropdownItem>)}</DropdownContent>
    </DropdownMenu>
  );
}

export function QuickCreateDrawer() {
  const ui = useUI(); const router = useRouter();
  const c = ui.create;
  const cfg = c ? FORMS[c.kind] : null;
  const href: Partial<Record<CreateKind, string>> = { lead: "leads", contact: "contacts", company: "companies", deal: "deals" };
  return (
    <Drawer open={!!c} onOpenChange={(o) => !o && ui.closeCreate()} title={cfg?.title ?? ""} description={c ? `Quick add — you'll stay right where you are.` : undefined}
      footer={c && <><Button variant="secondary" onClick={ui.closeCreate}>Cancel</Button><Button type="submit" form={`form-${c.kind}`}>{c.kind === "call" ? "Log call" : c.kind === "meeting" ? "Schedule" : c.kind === "note" ? "Add note" : `Create ${cfg!.noun}`}</Button></>}>
      {c && <RecordForm key={c.kind + JSON.stringify(c.defaults ?? {})} kind={c.kind} defaults={c.defaults} hideActions onView={href[c.kind] ? (rec) => router.push(`/app/${href[c.kind]}/${rec.id}`) : undefined} onSaved={() => ui.closeCreate()} />}
    </Drawer>
  );
}
