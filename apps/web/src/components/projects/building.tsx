"use client";
import { AnimatePresence, motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";
import { Check } from "lucide-react";
import * as React from "react";
import { cn, useTheme } from "@crm/ui";
import { STATUS, STATUS_ORDER, floorLabel, holdLeft, money, priceLine } from "@/lib/realestate";
import type { Building, UnitMini, UnitStatus } from "@/lib/realestate";

/* ---- spotlight filter ------------------------------------------------------------------------------------------------ */
export type Spot = { statuses: UnitStatus[]; bhk: string | null; q: string };
export const NO_SPOT: Spot = { statuses: [], bhk: null, q: "" };
export const isSpotting = (s: Spot) => s.statuses.length > 0 || !!s.bhk || !!s.q.trim();
export const fitsSpot = (u: UnitMini, s: Spot) => {
  if (s.statuses.length && !s.statuses.includes(u.status)) return false;
  if (s.bhk && u.bhk !== s.bhk) return false;
  const q = s.q.trim().toLowerCase();
  return !q || u.number.toLowerCase().includes(q) || (u.bhk ?? "").toLowerCase().includes(q) || (u.facing ?? "").toLowerCase().includes(q);
};

/* ---- sky ------------------------------------------------------------------------------------------------------------ */
// The sky follows the app theme: light shows the day scene, dark shows the night scene.
type SkyMode = "day" | "night";

/** The sky for the current theme. */
export function useSky(): SkyMode {
  const { resolved } = useTheme();
  return resolved === "dark" ? "night" : "day";
}

const STARS = Array.from({ length: 22 }, (_, i) => { const r = (n: number) => { const x = Math.sin(i * 91.7 + n * 12.3) * 10000; return x - Math.floor(x); }; const f = (n: number) => Math.round(n * 10) / 10; /* rounded so server and browser print identical numbers */ return { x: f(r(1) * 100), y: f(r(2) * 60), s: f(0.8 + r(3) * 1.4), d: f(r(4) * 3) }; });

function Cloud({ top, size, delay, opacity }: { top: string; size: number; delay: number; opacity: number }) {
  return (
    <svg aria-hidden className="cloud pointer-events-none" style={{ top, width: size, animationDelay: `${delay}s`, opacity }} viewBox="0 0 120 50">
      <ellipse cx="38" cy="34" rx="30" ry="14" /><ellipse cx="66" cy="26" rx="28" ry="18" /><ellipse cx="92" cy="35" rx="24" ry="12" />
    </svg>
  );
}
function Bird({ top, delay, scale = 1 }: { top: string; delay: number; scale?: number }) {
  return (
    <svg aria-hidden className="bird pointer-events-none absolute left-0" style={{ top, animationDelay: `${delay}s`, width: 22 * scale }} viewBox="0 0 22 10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <g className="bird-wing" style={{ animationDelay: `${delay % 0.4}s` }}><path d="M1 7 Q6 0 11 6" /><path d="M11 6 Q16 0 21 7" /></g>
    </svg>
  );
}

/** Sky, sun/moon, clouds, birds and stars behind whatever you put in it. The content leans toward the pointer a little. */
export function Sky({ children, className, tilt = true }: { children: React.ReactNode; className?: string; tilt?: boolean }) {
  const sky = useSky();
  const reduce = useReducedMotion();
  const px = useMotionValue(0), py = useMotionValue(0);
  const sx = useSpring(px, { stiffness: 60, damping: 16 }), sy = useSpring(py, { stiffness: 60, damping: 16 });
  const rotY = useTransform(sx, (v) => v * 4.5), rotX = useTransform(sy, (v) => v * -3);
  const far = useTransform(sx, (v) => v * -22), farY = useTransform(sy, (v) => v * -8);
  const on = tilt && !reduce;
  return (
    <div data-sky={sky} className={cn("facade-sky relative", className)}
      onPointerMove={on ? (e) => { if (e.pointerType !== "mouse") return; const r = e.currentTarget.getBoundingClientRect(); px.set((e.clientX - r.left) / r.width - 0.5); py.set((e.clientY - r.top) / r.height - 0.5); } : undefined}
      onPointerLeave={on ? () => { px.set(0); py.set(0); } : undefined}>
      <motion.div aria-hidden style={{ x: far, y: farY }} className="pointer-events-none absolute -inset-6">
        <div className="sky-stars absolute inset-6">{STARS.map((s, i) => <span key={i} className="twinkle absolute rounded-full bg-white" style={{ left: `${s.x}%`, top: `${s.y}%`, width: s.s, height: s.s, animationDelay: `${s.d}s` }} />)}</div>
        <Cloud top="14%" size={150} delay={0} opacity={0.9} /><Cloud top="30%" size={100} delay={-35} opacity={0.7} /><Cloud top="20%" size={120} delay={-62} opacity={0.8} />
        <div className="sky-body absolute inset-6 text-slate-700/70" style={{ opacity: sky === "night" ? 0 : 1 }}><Bird top="16%" delay={0} /><Bird top="22%" delay={-0.6} scale={0.75} /><Bird top="12%" delay={-1.3} scale={0.6} /></div>
        <motion.svg viewBox="0 0 64 64" className="absolute size-16" animate={{ left: "84%", top: "12%", opacity: sky === "night" ? 0 : 1 }} transition={{ type: "spring", stiffness: 50, damping: 15 }}>
          <defs><radialGradient id="sg"><stop offset="0" stopColor="var(--sun)" stopOpacity="0.9" /><stop offset="1" stopColor="var(--sun)" stopOpacity="0" /></radialGradient></defs>
          <circle cx="32" cy="32" r="31" fill="url(#sg)" style={{ animation: "sun-breathe 6s ease-in-out infinite" }} /><circle cx="32" cy="32" r="12" fill="var(--sun)" />
        </motion.svg>
        <motion.svg viewBox="0 0 64 64" className="absolute size-14" animate={{ left: "84%", top: sky === "night" ? "12%" : "30%", opacity: sky === "night" ? 1 : 0 }} transition={{ type: "spring", stiffness: 50, damping: 15 }}>
          <circle cx="32" cy="32" r="22" fill="#cdd6ff" opacity="0.15" /><circle cx="32" cy="32" r="11" fill="#eef1ff" /><circle cx="37" cy="29" r="9" fill="var(--sky-bot)" opacity="0.8" /><circle cx="28" cy="35" r="2" fill="#c3cbee" /><circle cx="33" cy="26" r="1.4" fill="#c3cbee" />
        </motion.svg>
      </motion.div>
      <div className="haze pointer-events-none absolute inset-0" aria-hidden />
      <motion.div className="relative" style={on ? { rotateY: rotY, rotateX: rotX, transformPerspective: 1200 } : undefined}>{children}</motion.div>
    </div>
  );
}

/* ---- the tower ------------------------------------------------------------------------------------------------------ */
function tileStyle(status: UnitStatus, dark: boolean): React.CSSProperties {
  const s = STATUS[status];
  const bg = dark ? s.bgDark : s.bg;
  const lamp = status === "rented" || status === "self_occupied" ? ", radial-gradient(circle at 82% 88%, rgba(255,226,140,.55), transparent 52%)" : "";
  return {
    color: dark ? s.inkDark : s.ink,
    backgroundColor: bg,
    // glass: a light-to-dark wash, and (for lived-in flats) a lamp glowing in the corner
    backgroundImage: `linear-gradient(160deg, rgba(255,255,255,${status === "vacant" ? 0.45 : 0.22}) 0%, rgba(255,255,255,0) 48%, rgba(0,0,0,.14) 100%)${lamp}`,
    ["--st" as string]: bg,
  };
}

const UnitTile = React.memo(function UnitTile({ u, dark, dim, hit, compact, delay, animate, picking, picked, onOpen, onHover }: {
  u: UnitMini; dark: boolean; dim: boolean; hit: boolean; compact: boolean; delay: number; animate: boolean; picking: boolean; picked: boolean; onOpen: (id: string) => void; onHover: (u: UnitMini | null, el: HTMLElement | null) => void;
}) {
  const s = STATUS[u.status];
  const Icon = s.icon;
  const left = u.status === "on_hold" ? holdLeft(u.hold_until) : null;
  return (
    <motion.button
      type="button"
      initial={animate ? { opacity: 0, y: 18, scale: 0.85 } : false}
      animate={{ opacity: dim ? 0.18 : 1, y: 0, scale: hit ? 1.04 : 1, filter: dim ? "saturate(.15)" : "saturate(1)" }}
      transition={{ delay: animate ? delay : 0, type: "spring", stiffness: 380, damping: 24 }}
      whileHover={dim ? undefined : { y: -4 }}
      whileTap={{ scale: 0.96 }}
      onClick={() => onOpen(u.id)}
      onPointerEnter={(e) => e.pointerType === "mouse" && !dim && onHover(u, e.currentTarget)}
      onPointerLeave={() => onHover(null, null)}
      onFocus={(e) => (!picking || e.currentTarget.matches(":focus-visible")) && onHover(u, e.currentTarget)}
      onBlur={() => onHover(null, null)}
      aria-label={`Unit ${u.number}${u.bhk ? `, ${u.bhk}` : ""}, ${s.label}${u.sale_price ? `, ${money(u.sale_price)}` : ""}`}
      aria-pressed={picking ? picked : undefined}
      data-unit={u.id}
      data-dim={dim ? "1" : undefined}
      style={{ ...tileStyle(u.status, dark), ...(animate ? { ["--d" as string]: `${delay + 0.35}s` } : null) }}
      className={cn("unit-tile @container/tile relative flex min-w-0 flex-col justify-between overflow-hidden rounded-[7px] text-left outline-none focus-visible:ring-2 focus-visible:ring-primary",
        `unit-${u.status}`, compact ? "h-[60px] px-2 py-1.5 sm:h-10 sm:px-1.5 sm:py-1" : "h-[60px] px-2 py-1.5", animate && "tile-wave", u.status === "on_hold" && "unit-hold", hit && "tile-hit z-10",
        picking && !picked && "opacity-80", picked && "tile-picked z-10")}>
      {/* On a narrow tile (phones) the tick takes the status icon's corner, so the size below it keeps its room. */}
      {picked && <span aria-hidden className={cn("pick-badge absolute bottom-0 right-0 z-10 grid place-items-center rounded-tl-[7px] bg-primary text-primary-fg", compact ? "size-5 sm:size-4" : "size-5 @max-[56px]/tile:top-0 @max-[56px]/tile:bottom-auto @max-[56px]/tile:size-4 @max-[56px]/tile:rounded-tl-none @max-[56px]/tile:rounded-bl-[7px]")}><Check className={compact ? "size-3.5 sm:size-2.5" : "size-3.5 @max-[56px]/tile:size-2.5"} strokeWidth={3} /></span>}
      <span className="flex items-start justify-between gap-1 @max-[56px]/tile:gap-0.5">
        <span className={cn("font-semibold tabular-nums leading-none", compact ? "text-[13px] sm:text-[11px]" : "text-[13px]")}>{u.number}</span>
        <Icon className={cn("shrink-0 opacity-90", `ico-${u.status}`, compact ? "size-3.5 sm:size-3" : "size-3.5 @max-[56px]/tile:size-2.5", picked && !compact && "@max-[56px]/tile:invisible", compact && "@max-[34px]/tile:hidden")} aria-hidden />
      </span>
      {/* Compact towers (lots of floors or flats) drop this line on bigger screens; phones scroll sideways, so they always keep it. */}
      <span className={cn("flex items-end justify-between gap-1 text-[10.5px] font-medium leading-none opacity-90", picked && "pr-4 @max-[56px]/tile:pr-0", compact && "sm:hidden")}>
        <span className="truncate">{left ? <>{left.replace(" left", "")}<span className="@max-[100px]/tile:hidden"> left</span></> : u.bhk?.replace(" BHK", "BHK") ?? ""}</span>
        <span className="truncate @max-[80px]/tile:hidden">{u.status === "vacant" ? "" : priceLine(u).replace("/mo", "")}</span>
      </span>
    </motion.button>
  );
});

/** Rooftop: parapet, water tank, a flag, an antenna with a beacon, and the tower's name on a sign. Unfinished projects get a crane. */
function Roof({ name, building }: { name: string; building: boolean }) {
  return (
    <div className="relative mx-auto">
      {building && <Crane />}
      <svg aria-hidden viewBox="0 0 160 52" className="mx-auto block h-[52px] w-[160px] overflow-visible">
        <rect x="26" y="26" width="34" height="26" rx="3" fill="var(--slab)" /><rect x="30" y="20" width="26" height="8" rx="4" fill="var(--slab-edge)" />
        <rect x="76" y="30" width="48" height="22" rx="2" fill="var(--slab)" />
        <line x1="136" y1="52" x2="136" y2="6" stroke="var(--slab-edge)" strokeWidth="2.5" strokeLinecap="round" /><line x1="128" y1="20" x2="144" y2="20" stroke="var(--slab-edge)" strokeWidth="2" strokeLinecap="round" />
        <circle cx="136" cy="5" r="3.2" fill="#ef4444" style={{ animation: "beacon 1.8s ease-in-out infinite" }} />
        <line x1="92" y1="30" x2="92" y2="10" stroke="var(--slab-edge)" strokeWidth="1.6" strokeLinecap="round" /><path className="flag" d="M92 10 L108 13 L92 17 Z" fill="#f97316" />
      </svg>
      <div className="relative -mt-px flex h-7 items-center justify-center rounded-t-lg max-sm:justify-start border border-b-0 border-[var(--frame-edge)] bg-[var(--slab)]">
        <span className="rounded-full bg-[var(--frame)] px-3 py-0.5 text-[11px] max-sm:sticky max-sm:left-9 max-sm:ml-9 font-semibold uppercase tracking-[0.18em] text-[color:var(--facade-ink)]">{name}</span>
      </div>
    </div>
  );
}

function Crane() {
  return (
    <svg aria-hidden viewBox="0 0 150 96" className="pointer-events-none absolute bottom-7 right-[4%] h-[96px] w-[150px] overflow-visible">
      <rect x="28" y="20" width="5" height="76" fill="var(--slab-edge)" />
      <path d="M28 96 L33 84 L28 72 L33 60 L28 48 L33 36 L28 24 M33 96 L28 84 L33 72 L28 60 L33 48 L28 36 L33 24" stroke="var(--slab)" strokeWidth="1.2" fill="none" />
      <path d="M30 6 L22 20 M31 6 L39 20" stroke="var(--slab-edge)" strokeWidth="1.6" />
      <rect x="2" y="16" width="146" height="4" rx="1" fill="#f59e0b" /><rect x="4" y="20" width="14" height="9" fill="var(--slab-edge)" />
      <path d="M30 6 L148 16 M30 6 L4 16" stroke="var(--slab-edge)" strokeWidth="1" />
      <g className="trolley"><rect x="62" y="20" width="9" height="4" fill="var(--slab-edge)" /><g className="hook"><line x1="66.5" y1="24" x2="66.5" y2="58" stroke="var(--slab-edge)" strokeWidth="1.1" /><rect x="58" y="58" width="17" height="7" rx="1" fill="#7c4a24" /></g></g>
      <circle cx="30" cy="4" r="2.6" fill="#ef4444" style={{ animation: "beacon 1.4s ease-in-out infinite" }} />
    </svg>
  );
}

function StreetScene() {
  return (
    <svg aria-hidden viewBox="0 0 600 40" preserveAspectRatio="xMidYMax slice" className="block h-10 w-full">
      <g className="sway"><circle cx="70" cy="22" r="11" fill="#16a34a" /><circle cx="84" cy="25" r="9" fill="#15803d" /></g><rect x="68" y="28" width="4" height="10" fill="#7c4a24" />
      <g className="sway" style={{ animationDelay: "-2s" }}><circle cx="530" cy="22" r="11" fill="#16a34a" /><circle cx="516" cy="25" r="9" fill="#15803d" /></g><rect x="528" y="28" width="4" height="10" fill="#7c4a24" />
      <g className="sway" style={{ animationDelay: "-1s" }}><circle cx="130" cy="27" r="7" fill="#22c55e" /></g><g className="sway" style={{ animationDelay: "-3s" }}><circle cx="470" cy="27" r="7" fill="#22c55e" /></g>
      {[200, 300, 400].map((x) => (<g key={x}><rect x={x - 1} y="16" width="2" height="22" fill="var(--slab-edge)" /><rect x={x - 5} y="14" width="10" height="3" rx="1.5" fill="var(--slab-edge)" /><circle className="lamp-glow" cx={x} cy="20" r="14" fill="#fde68a" opacity="0.35" /><circle className="lamp-glow" cx={x} cy="17" r="2.2" fill="#fef08a" /></g>))}
    </svg>
  );
}

function Street() {
  return (
    <div className="relative overflow-hidden rounded-b-xl bg-[var(--ground)] pb-3 pt-2">
      <StreetScene />
      <div className="walker pointer-events-none absolute bottom-[19px] z-[1]" aria-hidden>
        <svg viewBox="0 0 10 16" className="h-[14px] w-[9px]"><circle cx="5" cy="3" r="2.4" fill="#f4c7a1" /><rect x="3" y="5.5" width="4" height="6" rx="1.5" fill="#6366f1" /><path d="M4 11 L3 15 M6 11 L7 15" stroke="#334155" strokeWidth="1.3" strokeLinecap="round" /></svg>
      </div>
      <div className="relative mt-1 h-3.5 bg-[var(--slab)]">
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2" style={{ backgroundImage: "repeating-linear-gradient(90deg,#fff 0 14px,transparent 14px 28px)", opacity: 0.55 }} />
        <svg aria-hidden viewBox="0 0 40 16" className="car-a absolute -top-2 h-5 w-10"><path d="M3 12h34v-3l-5-1-4-4H14l-4 4-6 1z" fill="#2563eb" /><path d="M13 8l3-3h7l3 3z" fill="#bfdbfe" /><circle cx="12" cy="13" r="3" fill="#0f172a" /><circle cx="29" cy="13" r="3" fill="#0f172a" /><circle className="lamp-glow" cx="37" cy="10" r="2" fill="#fef08a" /></svg>
        <svg aria-hidden viewBox="0 0 40 16" className="car-b absolute -top-1 h-5 w-10" style={{ scale: "-1 1" }}><path d="M3 12h34v-3l-5-1-4-4H14l-4 4-6 1z" fill="#dc2626" /><path d="M13 8l3-3h7l3 3z" fill="#fecaca" /><circle cx="12" cy="13" r="3" fill="#0f172a" /><circle cx="29" cy="13" r="3" fill="#0f172a" /><circle className="lamp-glow" cx="37" cy="10" r="2" fill="#fef08a" /></svg>
      </div>
    </div>
  );
}

type Hover = { u: UnitMini; x: number; y: number; w: number } | null;

/** The hero: the tower as you'd see it from the street. Floors stack bottom-to-top, each flat is a lit window coloured by its status.
 *  Move the pointer over it and the flats swell toward you; a glint of sunlight sweeps across the glass every few seconds. */
export function BuildingView({ data, spot, onOpen, flashFloor, registerFloor, picked }: {
  data: Building; spot: Spot; onOpen: (id: string) => void; flashFloor?: number | null; registerFloor?: (floor: number, el: HTMLElement | null) => void;
  /** Compare mode: the flats already picked. Tapping a flat then picks it instead of opening it. */
  picked?: Set<string> | null;
}) {
  const dark = useSky() === "night"; // at night the empty flats go dark; lit ones glow
  const reduce = useReducedMotion();
  const wrap = React.useRef<HTMLDivElement>(null);
  const frame = React.useRef<HTMLDivElement>(null);
  const [hover, setHover] = React.useState<Hover>(null);
  const spotting = isSpotting(spot);
  const cols = Math.max(data.summary.units_per_floor ?? 4, 1);
  const total = data.summary.total;
  const compact = data.floors.length > 22 || cols > 8;
  const animateTiles = !reduce && total <= 260;
  const magnifyOn = !reduce && total <= 260;
  const rows = data.floors.length;
  const onHover = React.useCallback((u: UnitMini | null, el: HTMLElement | null) => {
    if (!u || !el || !wrap.current) return setHover(null);
    const a = el.getBoundingClientRect(), b = wrap.current.getBoundingClientRect();
    setHover({ u, x: a.left - b.left + a.width / 2, y: a.top - b.top, w: b.width });
  }, []);

  // "Dock" magnify: flats near the pointer swell, falling off smoothly. Writes a CSS variable per tile (no React re-render per move).
  const centres = React.useRef<{ el: HTMLElement; x: number; y: number }[] | null>(null);
  const stamp = React.useRef(0);
  const raf = React.useRef(0);
  const magnify = (e: React.PointerEvent) => {
    if (!magnifyOn || e.pointerType !== "mouse" || !frame.current) return;
    const { clientX: cx, clientY: cy } = e;
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => {
      const now = performance.now();
      if (!centres.current || now - stamp.current > 350) {
        stamp.current = now;
        centres.current = [...frame.current!.querySelectorAll<HTMLElement>("[data-unit]")].map((el) => { const r = el.getBoundingClientRect(); return { el, x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
      }
      for (const t of centres.current) {
        const m = t.el.dataset.dim ? 1 : 1 + 0.16 * Math.exp(-((t.x - cx) ** 2 + (t.y - cy) ** 2) / (2 * 80 * 80));
        t.el.style.setProperty("--mag", m.toFixed(3));
      }
    });
  };
  const calm = () => {
    cancelAnimationFrame(raf.current);
    setHover(null);
    frame.current?.querySelectorAll<HTMLElement>("[data-unit]").forEach((el) => el.style.setProperty("--mag", "1"));
    centres.current = null;
  };
  const maxW = Math.min(1120, 104 + cols * (compact ? 84 : 132));
  // Phones don't squeeze the flats to fit: each keeps its desktop size and details, and the tower scrolls sideways (floor numbers stay pinned).
  const minW = 26 + 8 + cols * 96 + (cols - 1) * 8 + 18;

  return (
    <div ref={wrap} className="relative" onPointerLeave={calm}>
      <div className="mx-auto w-full max-sm:overflow-x-auto max-sm:overscroll-x-contain" style={{ maxWidth: maxW }}>
      <div className="max-sm:min-w-[var(--tower-min)]" style={{ ["--tower-min" as string]: `${minW}px` }}>
        <Roof name={data.tower.name} building={data.project.stage !== "ready"} />
        <div ref={frame} onPointerMove={magnify} className="@container relative overflow-clip border-x border-[var(--frame-edge)] bg-[var(--frame)] px-2 py-2 sm:px-4 sm:py-3" role="list" aria-label={`${data.tower.name}, ${rows} floors`}>
          {!reduce && <div aria-hidden className="glare pointer-events-none absolute inset-y-0 left-0 z-20 w-[40%]" />}
          {data.floors.map((f, ri) => {
            const fromBottom = rows - 1 - ri;
            const anyHit = !spotting || f.units.some((u) => fitsSpot(u, spot));
            return (
              <div key={f.floor} ref={(el) => registerFloor?.(f.floor, el)} role="listitem" data-floor={f.floor}
                className={cn("grid grid-cols-[26px_1fr] items-center gap-2 rounded-md border-b-[5px] border-[var(--slab)] sm:grid-cols-[62px_1fr] sm:gap-3", compact ? "py-2.5 sm:py-1" : "py-2.5 sm:py-3", flashFloor === f.floor && "floor-flash", !anyHit && "opacity-60")}>
                <div className="z-[5] pr-1 text-right leading-tight text-[color:var(--facade-ink)] max-sm:sticky max-sm:left-0 max-sm:self-stretch max-sm:bg-[var(--frame)] max-sm:flex max-sm:items-center max-sm:justify-end">
                  <div className="text-[11px] font-semibold sm:text-xs"><span className="sm:hidden">{f.floor === 0 ? "G" : String(f.floor).padStart(2, "0")}</span><span className="hidden sm:inline">{floorLabel(f.floor)}</span></div>
                </div>
                <div className={cn("grid", compact ? "gap-2 sm:gap-1.5" : "gap-2 @2xl:gap-3")} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
                  {f.units.map((u) => {
                    const hit = spotting && fitsSpot(u, spot);
                    return <UnitTile key={u.id} u={u} dark={dark} dim={spotting && !hit} hit={hit} compact={compact} animate={animateTiles} delay={Math.min(fromBottom * 0.045 + (u.position - 1) * 0.02, 1.5)} picking={!!picked} picked={!!picked?.has(u.id)} onOpen={onOpen} onHover={onHover} />;
                  })}
                  {f.units.length === 0 && <div className="col-span-full rounded-md border border-dashed border-border-strong py-3 text-center text-xs text-fg-subtle">No flats on this floor yet</div>}
                </div>
              </div>
            );
          })}
        </div>
        <Street />
      </div>
      </div>

      <AnimatePresence>
        {hover && (
          <motion.div key="hc" initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, transition: { duration: 0.08 } }} transition={{ type: "spring", stiffness: 500, damping: 34 }}
            className="pointer-events-none absolute z-30 w-[236px] rounded-xl border border-border bg-surface p-3.5 shadow-lg"
            style={{ left: Math.min(Math.max(hover.x - 118, 4), Math.max(hover.w - 240, 4)), top: Math.max(hover.y - 8, 0), transform: "translateY(-100%)" }}>
            <HoverCard u={hover.u} hint={picked ? (picked.has(hover.u.id) ? "Click to remove from comparison" : "Click to add to comparison") : "Click to open"} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function HoverCard({ u, hint }: { u: UnitMini; hint: string }) {
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
      <p className="mt-1.5 text-[11px] text-fg-subtle">{hint}</p>
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
            style={on ? { background: resolved === "dark" ? m.bgDark : m.bg, color: resolved === "dark" ? m.inkDark : m.ink } : undefined}>
            <span className="grid size-5 place-items-center rounded-full" style={{ background: on ? "rgba(255,255,255,.22)" : resolved === "dark" ? m.bgDark : m.bg, color: resolved === "dark" ? m.inkDark : m.ink }}><Icon className="size-3" /></span>
            {m.label}<span className={cn("tabular-nums", on ? "opacity-90" : "text-fg-subtle")}>{counts[s] ?? 0}</span>
          </button>
        );
      })}
    </div>
  );
}
