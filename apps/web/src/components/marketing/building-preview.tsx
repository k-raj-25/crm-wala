"use client";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "@crm/ui";
import { STATUS, STATUS_ORDER } from "@/lib/realestate";
import type { UnitStatus } from "@/lib/realestate";
import { Sky } from "@/components/projects/building";
import { Window } from "./primitives";

const FLOORS = 8, PER = 4;
const START: UnitStatus[] = "vvsv rvvo vsrv vvhv rvvs ovrv vsvr rvov".replace(/ /g, "").split("").map((c) => ({ v: "vacant", s: "for_sale", r: "rented", o: "self_occupied", h: "on_hold" } as Record<string, UnitStatus>)[c]);
const CLIENTS = ["the Mehta family", "Priya S.", "Mr. Kapoor", "Anita & Raj", "Dr. Rao", "Sana K."];
const STEPS: Partial<Record<UnitStatus, [UnitStatus, string]>> = { vacant: ["for_sale", "listed for sale"], for_sale: ["on_hold", "held for"], on_hold: ["booked", "booked by"], booked: ["sold", "sold to"] };
const num = (i: number) => { const f = FLOORS - Math.floor(i / PER); return `${f}0${(i % PER) + 1}`; };

/** The hero visual: a tower whose flats change status on their own, with a live feed. Purely illustrative, no data fetched. */
export function BuildingHero() {
  const { resolved } = useTheme();
  const dark = resolved === "dark";
  const reduce = useReducedMotion();
  const [st, setSt] = useState<UnitStatus[]>(START);
  const [feed, setFeed] = useState<{ id: number; text: string; status: UnitStatus }[]>([]);
  const [pulse, setPulse] = useState<number | null>(null);
  const n = useRef(0); const seed = useRef(7);
  useEffect(() => {
    if (reduce) return;
    const rand = () => { seed.current = (seed.current * 9301 + 49297) % 233280; return seed.current / 233280; };
    const t = setInterval(() => {
      setSt((cur) => {
        const movable = cur.map((s, i) => [s, i] as const).filter(([s]) => STEPS[s]);
        const [from, i] = movable[Math.floor(rand() * movable.length)];
        const [to, verb] = STEPS[from]!;
        const who = CLIENTS[Math.floor(rand() * CLIENTS.length)];
        const text = `Unit ${num(i)} ${to === "for_sale" ? verb : `${verb} ${who}`}`;
        setPulse(i);
        setFeed((f) => [{ id: n.current++, text, status: to }, ...f].slice(0, 4));
        const next = [...cur]; next[i] = to; return next;
      });
    }, 1900);
    return () => clearInterval(t);
  }, [reduce]);
  const counts = st.reduce<Partial<Record<UnitStatus, number>>>((a, s) => ({ ...a, [s]: (a[s] ?? 0) + 1 }), {});
  return (
    <Window title="app.crmwala.com/projects/tower-d-13">
      <div className="grid gap-0 bg-bg lg:grid-cols-[1.35fr_1fr]">
        <Sky className="p-4 sm:p-6">
          <div className="mx-auto max-w-[420px]">
            <div className="mx-auto h-7 w-24 rounded-t-md bg-[var(--slab)]" />
            <div className="rounded-sm border border-[var(--frame-edge)] bg-[var(--frame)] p-2">
              {Array.from({ length: FLOORS }).map((_, r) => (
                <div key={r} className="grid grid-cols-[34px_1fr] items-center gap-2 border-b-4 border-[var(--slab)] py-[3px] last:border-b-0">
                  <span className="text-right text-[10px] font-semibold text-fg-muted">{String(FLOORS - r).padStart(2, "0")}</span>
                  <div className="grid grid-cols-4 gap-1.5">
                    {Array.from({ length: PER }).map((__, c) => {
                      const i = r * PER + c; const s = st[i]; const m = STATUS[s]; const Icon = m.icon;
                      return (
                        <motion.div key={`${i}-${s}`} initial={pulse === i ? { scale: 1.18 } : false} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 380, damping: 16 }}
                          className="relative flex h-9 items-center justify-between rounded-md px-1.5 text-[11px] font-semibold sm:h-10"
                          style={{ background: dark ? m.bgDark : m.bg, color: m.ink, boxShadow: "inset 0 -4px 0 rgba(0,0,0,.18)", backgroundImage: "linear-gradient(160deg, rgba(255,255,255,.28), rgba(255,255,255,0) 55%)" }}>
                          {num(i)}<Icon className="size-3 opacity-90" aria-hidden />
                        </motion.div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
            <div className="h-2 rounded-b-md bg-[var(--ground)]" />
          </div>
        </Sky>
        <div className="flex flex-col gap-5 border-t border-border p-5 lg:border-l lg:border-t-0">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Tower D-13 · live</p>
            <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5">
              {STATUS_ORDER.filter((s) => counts[s]).map((s) => (
                <li key={s} className="flex items-center gap-2 text-sm"><span className="size-2.5 rounded-full" style={{ background: dark ? STATUS[s].bgDark : STATUS[s].bg }} /><motion.span key={counts[s]} initial={{ y: -4, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="tabular font-semibold">{counts[s]}</motion.span><span className="text-fg-muted">{STATUS[s].label}</span></li>
              ))}
            </ul>
          </div>
          <div className="min-h-[170px] flex-1">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">Just now</p>
            <ul className="space-y-2" aria-live="polite">
              <AnimatePresence initial={false}>
                {feed.map((f) => {
                  const m = STATUS[f.status]; const Icon = m.icon;
                  return (
                    <motion.li key={f.id} layout initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="flex items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2 text-[13px]">
                      <span className="grid size-6 shrink-0 place-items-center rounded-md" style={{ background: dark ? m.bgDark : m.bg, color: m.ink }}><Icon className="size-3.5" /></span>{f.text}
                    </motion.li>
                  );
                })}
              </AnimatePresence>
              {!feed.length && <li className="text-[13px] text-fg-subtle">Watching the tower…</li>}
            </ul>
          </div>
        </div>
      </div>
    </Window>
  );
}
