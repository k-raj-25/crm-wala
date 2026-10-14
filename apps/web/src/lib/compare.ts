"use client";
import * as React from "react";

/** The flats a user is lining up to compare. Lives in the browser (survives page changes and reloads) and is shared by
 *  every screen: the tower, the flat drawer, the floating tray and the comparison page all read and write the same list. */
export type CompareFlat = { id: string; number: string; where: string };

export const MAX_COMPARE = 6;
const KEY = "crm-compare";
let items: CompareFlat[] | null = null;
const subs = new Set<() => void>();

function read(): CompareFlat[] {
  if (items) return items;
  try { items = JSON.parse(localStorage.getItem(KEY) ?? "[]"); } catch { items = []; }
  if (!Array.isArray(items)) items = [];
  return items;
}
function write(next: CompareFlat[]) {
  items = next;
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch {}
  subs.forEach((f) => f());
}
const EMPTY: CompareFlat[] = [];

export const compare = {
  /** Adds the flat; returns false when the list is already full. */
  add(f: CompareFlat) { const cur = read(); if (cur.some((x) => x.id === f.id)) return true; if (cur.length >= MAX_COMPARE) return false; write([...cur, f]); return true; },
  remove(id: string) { write(read().filter((x) => x.id !== id)); },
  /** Adds or removes; returns "added" | "removed" | "full". */
  toggle(f: CompareFlat): "added" | "removed" | "full" { if (read().some((x) => x.id === f.id)) { compare.remove(f.id); return "removed"; } return compare.add(f) ? "added" : "full"; },
  set(next: CompareFlat[]) { write(next.slice(0, MAX_COMPARE)); },
  clear() { write([]); },
};

if (typeof window !== "undefined") {
  // another tab changed the list
  window.addEventListener("storage", (e) => { if (e.key === KEY) { items = null; subs.forEach((f) => f()); } });
}

export function useCompare(): CompareFlat[] {
  return React.useSyncExternalStore((cb) => { subs.add(cb); return () => subs.delete(cb); }, read, () => EMPTY);
}
