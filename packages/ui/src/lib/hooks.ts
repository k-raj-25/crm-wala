"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export function useDebounce<T>(value: T, delay = 250) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

export function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial);
  const loaded = useRef(false);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw !== null) setValue(JSON.parse(raw));
    } catch {}
    loaded.current = true;
  }, [key]);
  const set = useCallback((next: T | ((p: T) => T)) => {
    setValue((prev) => {
      const v = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
      try { localStorage.setItem(key, JSON.stringify(v)); } catch {}
      return v;
    });
  }, [key]);
  return [value, set] as const;
}

export function useMediaQuery(query: string) {
  const [m, setM] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setM(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return m;
}

function isTyping(t: EventTarget | null) {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
}

/** Global hotkey. `mod` = Cmd on macOS / Ctrl elsewhere. Single-key hotkeys are ignored while typing. */
export function useHotkey(combo: string, handler: (e: KeyboardEvent) => void, deps: unknown[] = []) {
  useEffect(() => {
    const parts = combo.toLowerCase().split("+");
    const key = parts[parts.length - 1];
    const wantMod = parts.includes("mod"), wantShift = parts.includes("shift");
    const fn = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (wantMod !== mod || (wantShift && !e.shiftKey)) return;
      if (!wantMod && (isTyping(e.target) || e.altKey)) return;
      if (e.key.toLowerCase() === key) { handler(e); }
    };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [combo, ...deps]);
}

/** Two-key chord like "g" then "l". */
export function useChord(first: string, map: Record<string, () => void>) {
  useEffect(() => {
    let armed = false, timer: ReturnType<typeof setTimeout>;
    const fn = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      const k = e.key.toLowerCase();
      if (!armed && k === first) { armed = true; timer = setTimeout(() => (armed = false), 900); return; }
      if (armed) { armed = false; clearTimeout(timer); map[k]?.(); }
    };
    window.addEventListener("keydown", fn);
    return () => { window.removeEventListener("keydown", fn); clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [first]);
}
