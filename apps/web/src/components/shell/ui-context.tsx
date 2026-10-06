"use client";
import * as React from "react";

export type CreateKind = "lead" | "contact" | "company" | "deal" | "task" | "meeting" | "note" | "call";
type UI = {
  openCreate: (kind: CreateKind, defaults?: Record<string, unknown>) => void;
  openCommand: (initial?: string) => void; commandInitial: string;
  openCompose: (defaults?: { to?: string; contact_id?: string; lead_id?: string; deal_id?: string; company_id?: string; subject?: string; body?: string }) => void;
  openShortcuts: () => void;
  create: { kind: CreateKind; defaults?: Record<string, unknown> } | null;
  closeCreate: () => void;
  command: boolean; setCommand: (b: boolean) => void;
  compose: { defaults: Record<string, unknown> } | null; closeCompose: () => void;
  shortcuts: boolean; setShortcuts: (b: boolean) => void;
};
const Ctx = React.createContext<UI | null>(null);
export const useUI = () => { const c = React.useContext(Ctx); if (!c) throw new Error("useUI outside provider"); return c; };

export function UIProvider({ children }: { children: React.ReactNode }) {
  const [create, setCreate] = React.useState<UI["create"]>(null);
  const [command, setCommand] = React.useState(false);
  const [commandInitial, setCommandInitial] = React.useState("");
  const [compose, setCompose] = React.useState<UI["compose"]>(null);
  const [shortcuts, setShortcuts] = React.useState(false);
  const v = React.useMemo<UI>(() => ({
    openCreate: (kind, defaults) => setCreate({ kind, defaults }), closeCreate: () => setCreate(null), create,
    openCommand: (initial) => { setCommandInitial(initial ?? ""); setCommand(true); }, commandInitial, command, setCommand,
    openCompose: (d) => setCompose({ defaults: d ?? {} }), closeCompose: () => setCompose(null), compose,
    openShortcuts: () => setShortcuts(true), shortcuts, setShortcuts,
  }), [create, command, compose, shortcuts]);
  return <Ctx.Provider value={v}>{children}</Ctx.Provider>;
}
