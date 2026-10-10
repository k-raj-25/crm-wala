"use client";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import * as React from "react";
import { cn, useTheme } from "@crm/ui";
import { STATUS, STATUS_ORDER, floorLabel, holdLeft, money, priceLine } from "@/lib/realestate";
import type { Building, UnitMini, UnitStatus } from "@/lib/realestate";

export type Spot = { statuses: UnitStatus[]; bhk: string | null; q: string };
export const NO_SPOT: Spot = { statuses: [], bhk: null, q: "" };
export const isSpotting = (s: Spot) => s.statuses.length > 0 || !!s.bhk || !!s.q.trim();
export const fitsSpot = (u: UnitMini, s: Spot) => {
  if (s.statuses.length && !s.statuses.includes(u.status)) return false;
  if (s.bhk && u.bhk !== s.bhk) return false;
  const q = s.q.trim().toLowerCase();
  return !q || u.number.toLowerCase().includes(q) || (u.bhk ?? "").toLowerCase().includes(q) || (u.facing ?? "").toLowerCase().includes(q);
};

function tileStyle(status: UnitStatus, dark: boolean): React.CSSProperties {
  const s = STATUS[status];
  const bg = dark ? s.bgDark : s.bg;
  return {
    color: s.ink,
    backgroundColor: bg,
    // glass: a light-to-dark wash, one window mullion, and a darker balcony ledge along the bottom
    backgroundImage: `linear-gradient(to right, transparent calc(50% - .5px), rgba(255,255,255,.28) calc(50% - .5px) calc(50% + .5px), transparent calc(50% + .5px)), linear-gradient(160deg, rgba(255,255,255,${status === "vacant" ? 0.45 : 0.22}) 0%, rgba(255,255,255,0) 48%, rgba(0,0,0,.14) 100%)`,
    boxShadow: "inset 0 -5px 0 rgba(0,0,0,.18)",
  };
}

const UnitTile = React.memo(function UnitTile({ u, dark, dim, hit, compact, delay, animate, onOpen, onHover }: {
  u: UnitMini; dark: boolean; dim: boolean; hit: boolean; compact: boolean; delay: number; animate: boolean; onOpen: (id: string) => void; onHover: (u: UnitMini | null, el: HTMLElement | null) => void;
}) {
  const s = STATUS[u.status];
  const Icon = s.icon;
  const left = u.status === "on_hold" ? holdLeft(u.hold_until) : null;
  return (
    <motion.button
      type="button"
      initial={animate ? { opacity: 0, y: 14, scale: 0.9 } : false}
      animate={{ opacity: dim ? 0.2 : 1, y: 0, scale: hit ? 1.04 : 1, filter: dim ? "saturate(.2)" : "saturate(1)" }}
      transition={{ delay: animate ? delay : 0, type: "spring", stiffness: 420, damping: 30 }}
      whileHover={dim ? undefined : { y: -3, scale: 1.06 }}
      whileTap={{ scale: 0.97 }}
      onClick={() => onOpen(u.id)}
      onPointerEnter={(e) => e.pointerType === "mouse" && !dim && onHover(u, e.currentTarget)}
      onPointerLeave={() => onHover(null, null)}
      onFocus={(e) => onHover(u, e.currentTarget)}
      onBlur={() => onHover(null, null)}
      aria-label={`Unit ${u.number}${u.bhk ? `, ${u.bhk}` : ""}, ${s.label}${u.sale_price ? `, ${money(u.sale_price)}` : ""}`}
      data-unit={u.id}
      style={tileStyle(u.status, dark)}
      className={cn("relative flex min-w-0 flex-col justify-between overflow-hidden rounded-[7px] text-left outline-none ring-offset-2 ring-offset-transparent focus-visible:ring-2 focus-visible:ring-primary",
        compact ? "h-10 px-1.5 py-1" : "h-[60px] px-2 py-1.5", u.status === "on_hold" && "unit-hold", hit && "z-10 ring-2 ring-white/90 shadow-lg")}>
      <span className="flex items-start justify-between gap-1">
        <span className={cn("font-semibold tabular-nums leading-none", compact ? "text-[11px]" : "text-[13px]")}>{u.number}</span>
        <Icon className={cn("shrink-0 opacity-90", compact ? "size-3" : "size-3.5")} aria-hidden />
      </span>
      {!compact && (
        <span className="flex items-end justify-between gap-1 text-[10.5px] font-medium leading-none opacity-90">
          <span className="truncate">{left ?? u.bhk?.replace(" BHK", "B") ?? ""}</span>
          <span className="truncate max-sm:hidden">{u.status === "vacant" ? "" : priceLine(u).replace("/mo", "")}</span>
        </span>
      )}
    </motion.button>
  );
});

function Cloud({ top, size, delay, opacity }: { top: string; size: number; delay: number; opacity: number }) {
  return (
    <svg aria-hidden className="cloud pointer-events-none absolute" style={{ top, width: size, animationDelay: `${delay}s`, opacity }} viewBox="0 0 120 50" fill="currentColor">
      <g className="text-white dark:text-[#2a3470]"><ellipse cx="38" cy="34" rx="30" ry="14" /><ellipse cx="66" cy="26" rx="28" ry="18" /><ellipse cx="92" cy="35" rx="24" ry="12" /></g>
    </svg>
  );
}

export function Sky({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("facade-sky relative overflow-hidden", className)}>
      <div className="facade-stars pointer-events-none absolute inset-0" aria-hidden />
      <Cloud top="6%" size={150} delay={0} opacity={0.9} /><Cloud top="22%" size={100} delay={-35} opacity={0.7} /><Cloud top="12%" size={120} delay={-62} opacity={0.8} />
      <svg aria-hidden className="pointer-events-none absolute right-6 top-5 size-14" viewBox="0 0 64 64" style={{ animation: "sun-breathe 6s ease-in-out infinite" }}>
        <defs><radialGradient id="sunglow"><stop offset="0" stopColor="#fff7c2" /><stop offset="1" stopColor="#fde047" stopOpacity="0" /></radialGradient></defs>
        <circle cx="32" cy="32" r="30" fill="url(#sunglow)" className="dark:hidden" /><circle cx="32" cy="32" r="12" fill="#fde047" className="dark:hidden" />
        <circle cx="32" cy="32" r="11" fill="#e8ecff" className="hidden dark:block" /><circle cx="37" cy="29" r="9" fill="#1b2352" className="hidden dark:block" />
      </svg>
      <div className="relative">{children}</div>
    </div>
  );
}

/** Rooftop: parapet, water tank, antenna with a blinking beacon, and the tower's name on a sign. */
function Roof({ name }: { name: string }) {
  return (
    <div className="relative mx-auto">
      <svg aria-hidden viewBox="0 0 160 52" className="mx-auto block h-[52px] w-[160px]">
        <rect x="26" y="26" width="34" height="26" rx="3" fill="var(--slab)" /><rect x="30" y="20" width="26" height="8" rx="4" fill="var(--slab-edge)" />
        <rect x="76" y="30" width="48" height="22" rx="2" fill="var(--slab)" />
        <line x1="136" y1="52" x2="136" y2="6" stroke="var(--slab-edge)" strokeWidth="2.5" strokeLinecap="round" /><line x1="128" y1="20" x2="144" y2="20" stroke="var(--slab-edge)" strokeWidth="2" strokeLinecap="round" />
        <circle cx="136" cy="5" r="3.2" fill="#ef4444" style={{ animation: "beacon 1.8s ease-in-out infinite" }} />
      </svg>
      <div className="relative -mt-px flex h-7 items-center justify-center rounded-t-lg border border-b-0 border-[var(--frame-edge)] bg-[var(--slab)]">
        <span className="rounded-full bg-[var(--frame)] px-3 py-0.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-fg-muted">{name}</span>
      </div>
    </div>
  );
}

function Street() {
  return (
    <div className="relative mt-0 overflow-hidden rounded-b-xl bg-[var(--ground)] pb-3 pt-2">
      <svg aria-hidden viewBox="0 0 600 36" preserveAspectRatio="xMidYMax slice" className="block h-9 w-full">
        <g fill="#16a34a"><circle cx="70" cy="22" r="11" /><circle cx="84" cy="25" r="9" /><circle cx="530" cy="22" r="11" /><circle cx="516" cy="25" r="9" /><circle cx="130" cy="27" r="7" /><circle cx="470" cy="27" r="7" /></g>
        <g fill="#7c4a24"><rect x="68" y="28" width="4" height="8" /><rect x="528" y="28" width="4" height="8" /></g>
      </svg>
      <div className="relative mt-1 h-3 bg-[var(--slab)]">
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2" style={{ backgroundImage: "repeating-linear-gradient(90deg,#fff 0 14px,transparent 14px 28px)", opacity: 0.55 }} />
        <svg aria-hidden viewBox="0 0 40 16" className="absolute -top-2.5 h-5 w-10" style={{ animation: "car-drive 16s linear infinite" }}>
          <path d="M3 12h34v-3l-5-1-4-4H14l-4 4-6 1z" fill="#2563eb" /><path d="M13 8l3-3h7l3 3z" fill="#bfdbfe" /><circle cx="12" cy="13" r="3" fill="#0f172a" /><circle cx="29" cy="13" r="3" fill="#0f172a" />
        </svg>
      </div>
    </div>
  );
}

type Hover = { u: UnitMini; x: number; y: number; w: number } | null;

/** The hero: the tower as you'd see it from the street. Floors stack bottom-to-top, each flat is a lit window coloured by its status. */
export function BuildingView({ data, spot, onOpen, flashFloor, registerFloor }: {
  data: Building; spot: Spot; onOpen: (id: string) => void; flashFloor?: number | null; registerFloor?: (floor: number, el: HTMLElement | null) => void;
}) {
  const { resolved } = useTheme();
  const dark = resolved === "dark";
  const reduce = useReducedMotion();
  const wrap = React.useRef<HTMLDivElement>(null);
  const [hover, setHover] = React.useState<Hover>(null);
  const spotting = isSpotting(spot);
  const cols = Math.max(data.summary.units_per_floor ?? 4, 1);
  const total = data.summary.total;
  const compact = data.floors.length > 22 || cols > 8;
  const animateTiles = !reduce && total <= 260;
  const rows = data.floors.length;
  const onHover = React.useCallback((u: UnitMini | null, el: HTMLElement | null) => {
    if (!u || !el || !wrap.current) return setHover(null);
    const a = el.getBoundingClientRect(), b = wrap.current.getBoundingClientRect();
    setHover({ u, x: a.left - b.left + a.width / 2, y: a.top - b.top, w: b.width });
  }, []);
  const maxW = Math.min(1040, 96 + cols * (compact ? 78 : 118));

  return (
    <div ref={wrap} className="relative" onPointerLeave={() => setHover(null)}>
      <div className="mx-auto w-full" style={{ maxWidth: maxW }}>
        <Roof name={data.tower.name} />
        <div className="border-x border-[var(--frame-edge)] bg-[var(--frame)] px-2 py-1.5 sm:px-3" role="list" aria-label={`${data.tower.name}, ${rows} floors`}>
          {data.floors.map((f, ri) => {
            const fromBottom = rows - 1 - ri;
            const free = f.units.filter((u) => ["vacant", "for_sale", "for_rent"].includes(u.status)).length;
            const anyHit = !spotting || f.units.some((u) => fitsSpot(u, spot));
            return (
              <div key={f.floor} ref={(el) => registerFloor?.(f.floor, el)} role="listitem" data-floor={f.floor}
                className={cn("grid grid-cols-[44px_1fr] items-center gap-2 rounded-md border-b-[5px] border-[var(--slab)] py-[3px] sm:grid-cols-[62px_1fr]", flashFloor === f.floor && "floor-flash", !anyHit && "opacity-60")}>
                <div className="pr-1 text-right leading-tight">
                  <div className="text-[11px] font-semibold text-fg-muted sm:text-xs"><span className="sm:hidden">{f.floor === 0 ? "G" : String(f.floor).padStart(2, "0")}</span><span className="hidden sm:inline">{floorLabel(f.floor)}</span></div>
                  {free > 0 && !compact && <div className="hidden text-[10px] text-fg-subtle sm:block">{free} free</div>}
                </div>
                <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
                  {f.units.map((u) => {
                    const hit = spotting && fitsSpot(u, spot);
                    return <UnitTile key={u.id} u={u} dark={dark} dim={spotting && !hit} hit={hit} compact={compact} animate={animateTiles} delay={Math.min(fromBottom * 0.04 + (u.position - 1) * 0.02, 1.4)} onOpen={onOpen} onHover={onHover} />;
                  })}
                  {f.units.length === 0 && <div className="col-span-full rounded-md border border-dashed border-border-strong py-3 text-center text-xs text-fg-subtle">No flats on this floor yet</div>}
                </div>
              </div>
            );
          })}
        </div>
        <Street />
      </div>

      <AnimatePresence>
        {hover && (
          <motion.div key="hc" initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, transition: { duration: 0.08 } }} transition={{ type: "spring", stiffness: 500, damping: 34 }}
            className="pointer-events-none absolute z-30 w-[236px] rounded-xl border border-border bg-surface p-3.5 shadow-lg"
            style={{ left: Math.min(Math.max(hover.x - 118, 4), Math.max(hover.w - 240, 4)), top: Math.max(hover.y - 8, 0), transform: "translateY(-100%)" }}>
            <HoverCard u={hover.u} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function HoverCard({ u }: { u: UnitMini }) {
  const s = STATUS[u.status];
  const Icon = s.icon;
  const left = u.status === "on_hold" ? holdLeft(u.hold_until) : null;
  return (
    <div className="text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="text-base font-semibold tracking-tight">Unit {u.number}</span>
        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold" style={{ background: s.bg, color: s.ink }}><Icon className="size-3" />{s.label}</span>
      </div>
      <p className="mt-1 text-[13px] text-fg-muted">{[u.bhk, u.area_sqft ? `${Math.round(u.area_sqft).toLocaleString("en-IN")} sq ft` : null, u.facing ? `${u.facing} facing` : null].filter(Boolean).join(" · ") || "No details yet"}</p>
      <div className="mt-2 flex items-center justify-between border-t border-border pt-2 text-[13px]">
        <span className="text-fg-muted">{u.status === "for_rent" || u.status === "rented" ? "Rent" : "Price"}</span><span className="font-semibold tabular-nums">{priceLine(u)}</span>
      </div>
      {left && <p className="mt-1 text-xs font-medium text-[#7c3aed] dark:text-[#a78bfa]">Hold · {left}</p>}
      <p className="mt-1.5 text-[11px] text-fg-subtle">Click to open</p>
    </div>
  );
}

/** Colour key. Doubles as the quickest filter: tap a status to spotlight just those flats on the building. */
export function Legend({ counts, active, onToggle, className }: { counts: Partial<Record<UnitStatus, number>>; active: UnitStatus[]; onToggle: (s: UnitStatus) => void; className?: string }) {
  const { resolved } = useTheme();
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)} role="group" aria-label="Filter by status">
      {STATUS_ORDER.filter((s) => (counts[s] ?? 0) > 0 || active.includes(s)).map((s) => {
        const m = STATUS[s];
        const on = active.includes(s);
        const Icon = m.icon;
        return (
          <button key={s} type="button" onClick={() => onToggle(s)} aria-pressed={on} title={m.hint}
            className={cn("group inline-flex h-8 items-center gap-2 rounded-full border px-2.5 text-[13px] font-medium transition-all", on ? "border-transparent shadow-sm" : "border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg")}
            style={on ? { background: resolved === "dark" ? m.bgDark : m.bg, color: m.ink } : undefined}>
            <span className="grid size-5 place-items-center rounded-full" style={{ background: on ? "rgba(255,255,255,.22)" : resolved === "dark" ? m.bgDark : m.bg, color: m.ink }}><Icon className="size-3" /></span>
            {m.label}<span className={cn("tabular-nums", on ? "opacity-90" : "text-fg-subtle")}>{counts[s] ?? 0}</span>
          </button>
        );
      })}
    </div>
  );
}
