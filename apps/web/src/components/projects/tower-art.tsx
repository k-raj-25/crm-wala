"use client";
import { motion } from "framer-motion";
import * as React from "react";
import { useTheme } from "@crm/ui";
import { STATUS, STATUS_ORDER } from "@/lib/realestate";
import type { Building, CountMap, TowerLite, UnitStatus } from "@/lib/realestate";
import { Sky, fitsSpot, isSpotting } from "./building";
import type { Spot } from "./building";

const fill = (s: UnitStatus, dark: boolean) => (dark ? STATUS[s].bgDark : STATUS[s].bg);

/** A little drawing of the tower with every flat as a lit window. Doubles as a map: tap a floor to jump to it. */
export function TowerArt({ data, spot, onPickFloor, className }: { data: Building; spot: Spot; onPickFloor?: (floor: number) => void; className?: string }) {
  const { resolved } = useTheme();
  const dark = resolved === "dark";
  const [hot, setHot] = React.useState<number | null>(null);
  const rows = data.floors.length;
  const cols = Math.max(data.summary.units_per_floor ?? 4, 1);
  const spotting = isSpotting(spot);
  const rowH = Math.max(Math.min(230 / rows, 17), 4);
  const bodyH = rows * rowH;
  const bw = Math.min(Math.max(cols * 26 + 16, 96), 176);
  const x0 = (240 - bw) / 2;
  const ground = 300;
  const top = ground - bodyH;
  const gap = cols > 8 ? 1 : 2.5;
  const ww = (bw - 14 - gap * (cols - 1)) / cols;
  return (
    <Sky className={className}>
      <svg viewBox="0 0 240 330" className="block w-full" role="img" aria-label={`${data.tower.name} overview. Tap a floor to jump to it.`}>
        <rect x="0" y={ground} width="240" height="30" fill="var(--ground)" />
        <g fill="#16a34a"><circle cx="24" cy={ground - 6} r="13" /><circle cx="40" cy={ground - 2} r="10" /><circle cx="214" cy={ground - 6} r="13" /><circle cx="198" cy={ground - 2} r="10" /></g>
        <g fill="#7c4a24"><rect x="22" y={ground} width="4" height="9" /><rect x="212" y={ground} width="4" height="9" /></g>
        <rect x={x0 - 3} y={top - 8} width={bw + 6} height={bodyH + 8} rx="4" fill="var(--frame)" stroke="var(--frame-edge)" />
        <rect x={x0 + bw * 0.18} y={top - 20} width={bw * 0.22} height="12" rx="2" fill="var(--slab)" />
        <line x1={x0 + bw * 0.78} y1={top - 8} x2={x0 + bw * 0.78} y2={top - 32} stroke="var(--slab-edge)" strokeWidth="2" strokeLinecap="round" />
        <circle cx={x0 + bw * 0.78} cy={top - 33} r="2.6" fill="#ef4444" style={{ animation: "beacon 1.8s ease-in-out infinite" }} />
        {data.floors.map((f, ri) => {
          const y = top + ri * rowH;
          return (
            <motion.g key={f.floor} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min((rows - ri) * 0.025, 0.9) }}>
              {f.units.map((u, ci) => (
                <rect key={u.id} x={x0 + 7 + ci * (ww + gap)} y={y + 0.9} width={ww} height={Math.max(rowH - 1.8, 2)} rx="1.2" fill={fill(u.status, dark)} opacity={spotting && !fitsSpot(u, spot) ? 0.16 : 1} />
              ))}
              <rect x={x0 - 3} y={y} width={bw + 6} height={rowH} fill={hot === f.floor ? "rgba(250,204,21,.28)" : "transparent"} stroke={hot === f.floor ? "rgba(250,204,21,.9)" : "none"} strokeWidth="1"
                className={onPickFloor ? "cursor-pointer" : undefined} onPointerEnter={() => setHot(f.floor)} onPointerLeave={() => setHot(null)} onClick={() => onPickFloor?.(f.floor)}>
                <title>{f.floor === 0 ? "Ground floor" : `Floor ${f.floor}`}</title>
              </rect>
            </motion.g>
          );
        })}
        <rect x={x0 + bw / 2 - 9} y={ground - 14} width="18" height="14" rx="2" fill="#0f172a" opacity="0.55" />
      </svg>
    </Sky>
  );
}

/** Deterministic pseudo-random in [0,1) so the skyline doesn't flicker between renders. */
const rnd = (i: number, seed: number) => { const x = Math.sin(i * 12.9898 + seed * 78.233) * 43758.5453; return x - Math.floor(x); };

function pickStatus(counts: CountMap, r: number): UnitStatus {
  const total = STATUS_ORDER.reduce((n, s) => n + (counts[s] ?? 0), 0) || 1;
  let acc = 0;
  for (const s of STATUS_ORDER) { acc += (counts[s] ?? 0) / total; if (r <= acc) return s; }
  return "vacant";
}

/** Project card artwork: one silhouette per tower (height follows its real floor count), windows lit in the project's real mix of statuses. */
export function ProjectSkyline({ towers, counts, className }: { towers: TowerLite[]; counts: CountMap; className?: string }) {
  const { resolved } = useTheme();
  const dark = resolved === "dark";
  const list = towers.slice(0, 5);
  const maxF = Math.max(...list.map((t) => t.floors + (t.has_ground ? 1 : 0)), 4);
  const bw = list.length > 3 ? 52 : list.length > 1 ? 74 : 100;
  const total = list.length * bw + (list.length - 1) * 12;
  const x0 = (320 - total) / 2;
  return (
    <Sky className={className}>
      <svg viewBox="0 0 320 150" className="block w-full" aria-hidden>
        <rect x="0" y="128" width="320" height="22" fill="var(--ground)" />
        {list.length === 0 && <text x="160" y="96" textAnchor="middle" fontSize="12" fill="var(--fg-subtle)">No towers yet</text>}
        {list.map((t, ti) => {
          const floors = t.floors + (t.has_ground ? 1 : 0);
          const h = 40 + (floors / maxF) * 78;
          const x = x0 + ti * (bw + 12);
          const rowsN = Math.min(floors, 12);
          const cols = bw > 70 ? 4 : 3;
          const rh = (h - 12) / rowsN;
          return (
            <motion.g key={t.id} initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: ti * 0.1, type: "spring", stiffness: 160, damping: 20 }}>
              <rect x={x} y={128 - h} width={bw} height={h} rx="3" fill="var(--frame)" stroke="var(--frame-edge)" />
              <rect x={x + bw * 0.2} y={128 - h - 6} width={bw * 0.25} height="6" rx="1.5" fill="var(--slab)" />
              {Array.from({ length: rowsN }).map((_, r) =>
                Array.from({ length: cols }).map((__, c) => (
                  <rect key={`${r}-${c}`} x={x + 5 + c * ((bw - 10) / cols)} y={128 - h + 6 + r * rh} width={(bw - 10) / cols - 2} height={Math.max(rh - 2.4, 2)} rx="1" fill={fill(pickStatus(t.summary.counts, rnd(r * 7 + c + ti * 31, ti + 1)), dark)} />
                )))}
            </motion.g>
          );
        })}
      </svg>
    </Sky>
  );
}

/** One thin bar: how the project's flats divide between the statuses. */
export function StatusBar({ counts, className, height = 8 }: { counts: CountMap; className?: string; height?: number }) {
  const { resolved } = useTheme();
  const total = STATUS_ORDER.reduce((n, s) => n + (counts[s] ?? 0), 0);
  return (
    <div className={className} role="img" aria-label={STATUS_ORDER.filter((s) => counts[s]).map((s) => `${counts[s]} ${STATUS[s].label}`).join(", ")}>
      <div className="flex w-full gap-px overflow-hidden rounded-full bg-bg-subtle" style={{ height }}>
        {total > 0 && STATUS_ORDER.filter((s) => counts[s]).map((s) => (
          <motion.span key={s} initial={{ width: 0 }} animate={{ width: `${((counts[s] ?? 0) / total) * 100}%` }} transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }} style={{ background: resolved === "dark" ? STATUS[s].bgDark : STATUS[s].bg }} />
        ))}
      </div>
    </div>
  );
}
