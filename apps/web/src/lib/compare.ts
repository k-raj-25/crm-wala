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

/** Societies (projects) lined up to compare, with what to send for each: which layouts and which photos.
 *  `sizes` / `photos` stay null until the user changes them, so the defaults follow the project (all layouts, first photos). */
export type CompareSociety = { id: string; name: string; where: string; sizes: string[] | null; photos: string[] | null };

export const MAX_SOCIETIES = 4;
export const DEFAULT_PHOTOS = 4;
const SKEY = "crm-compare-societies";
let sItems: CompareSociety[] | null = null;
const sSubs = new Set<() => void>();
const SEMPTY: CompareSociety[] = [];

function sRead(): CompareSociety[] {
  if (sItems) return sItems;
  try { sItems = JSON.parse(localStorage.getItem(SKEY) ?? "[]"); } catch { sItems = []; }
  if (!Array.isArray(sItems)) sItems = [];
  return sItems;
}
function sWrite(next: CompareSociety[]) {
  sItems = next;
  try { localStorage.setItem(SKEY, JSON.stringify(next)); } catch {}
  sSubs.forEach((f) => f());
}

export const societyCompare = {
  has(id: string) { return sRead().some((x) => x.id === id); },
  /** Adds or removes; returns "added" | "removed" | "full". */
  toggle(s: Pick<CompareSociety, "id" | "name" | "where">): "added" | "removed" | "full" {
    const cur = sRead();
    if (cur.some((x) => x.id === s.id)) { sWrite(cur.filter((x) => x.id !== s.id)); return "removed"; }
    if (cur.length >= MAX_SOCIETIES) return "full";
    sWrite([...cur, { ...s, sizes: null, photos: null }]); return "added";
  },
  remove(id: string) { sWrite(sRead().filter((x) => x.id !== id)); },
  update(id: string, patch: Partial<CompareSociety>) { sWrite(sRead().map((x) => (x.id === id ? { ...x, ...patch } : x))); },
  set(next: CompareSociety[]) { sWrite(next.slice(0, MAX_SOCIETIES)); },
  clear() { sWrite([]); },
};

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => { if (e.key === SKEY) { sItems = null; sSubs.forEach((f) => f()); } });
}

export function useSocietyCompare(): CompareSociety[] {
  return React.useSyncExternalStore((cb) => { sSubs.add(cb); return () => sSubs.delete(cb); }, sRead, () => SEMPTY);
}
