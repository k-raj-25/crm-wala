"use client";
import * as React from "react";

/* Liquid glass refraction. Every `.glass` / `.glass-pop` bar marked `data-refract` gets an SVG displacement filter as its backdrop-filter
   (drawn on its `::before`, see `.lg-on` in styles.css),
   so whatever sits behind it bends like light through a water droplet: strongly pulled and magnified in a band along the
   rounded edge, with a slight lens magnification in the middle. Red, green and blue are displaced by slightly different
   amounts, so the edges fringe with colour. `.glass` stays fairly clear, while `.glass-pop` (menus, dialogs) is frosted over.

   The map depends on the element's size and corner radius, so filters are generated per size bucket and shared by every
   element of that size. Only Chromium renders SVG filters in `backdrop-filter`; other browsers keep the plain blur from
   styles.css. */

const NS = "http://www.w3.org/2000/svg";
const BUCKET = 4; // px; sizes are rounded so near-identical cards share a filter
const MAX_FILTERS = 120;

type Entry = { id: string; refs: number; node: SVGFilterElement; ready: boolean };

function supported() {
  if (typeof window === "undefined") return false;
  const brands = (navigator as Navigator & { userAgentData?: { brands: { brand: string }[] } }).userAgentData?.brands;
  const chromium = brands ? brands.some((b) => /Chromium|Google Chrome|Microsoft Edge/.test(b.brand)) : /Chrome\//.test(navigator.userAgent) && !/Edg\/|OPR\//.test(navigator.userAgent) ? true : false;
  return chromium && CSS.supports("backdrop-filter", "blur(1px)") && !matchMedia("(prefers-reduced-transparency: reduce)").matches;
}

/** The displacement map: red = sideways shift, green = up/down shift, 128 = none. Drawn at half size; feImage stretches it.
    It runs PAD px past every side with no shift, so if the map lands a few pixels off the element nothing tears at the rim. */
const PAD = 24;
function makeMap(w: number, h: number, radius: number, band: number, maxShift: number) {
  const s = 0.5, mw = Math.max(2, Math.round((w + 2 * PAD) * s)), mh = Math.max(2, Math.round((h + 2 * PAD) * s));
  const c = document.createElement("canvas"); c.width = mw; c.height = mh;
  const ctx = c.getContext("2d")!; const img = ctx.createImageData(mw, mh); const px = img.data;
  const hw = w / 2, hh = h / 2, r = Math.min(radius, hw, hh);
  for (let j = 0; j < mh; j++) for (let i = 0; i < mw; i++) {
    const x = (i + 0.5) / s - PAD - hw, y = (j + 0.5) / s - PAD - hh; // centred coordinates
    // signed distance to the rounded rectangle and the outward normal there
    const qx = Math.abs(x) - (hw - r), qy = Math.abs(y) - (hh - r);
    let dist: number, nx: number, ny: number;
    if (qx > 0 && qy > 0) { const l = Math.hypot(qx, qy) || 1; dist = r - l; nx = (qx / l) * Math.sign(x); ny = (qy / l) * Math.sign(y); }
    else if (qx > qy) { dist = r - qx; nx = Math.sign(x); ny = 0; }
    else { dist = r - qy; nx = 0; ny = Math.sign(y); }
    let dx = 0, dy = 0;
    if (dist >= 0) {
      // edge: a convex rim pulls the backdrop in from further inside (looks magnified and bent); strongest at the border
      const e = dist < band ? Math.pow(1 - dist / band, 2.2) : 0;
      dx = -nx * e * maxShift; dy = -ny * e * maxShift;
      // centre: a gentle lens, everything pulled a little towards the middle
      dx += (-x / hw) * maxShift * 0.15; dy += (-y / hh) * maxShift * 0.15;
    }
    const k = (j * mw + i) * 4;
    px[k] = 128 + (dx / maxShift) * 127; px[k + 1] = 128 + (dy / maxShift) * 127; px[k + 2] = 128; px[k + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return c.toDataURL();
}

function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>, parent?: Element) {
  const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v)); parent?.appendChild(n); return n;
}

function buildFilter(id: string, w: number, h: number, radius: number, frost: boolean, blur: number) {
  const band = Math.max(6, Math.min(30, Math.min(w, h) * 0.34));
  const shift = Math.min(band * 1.1, 28);
  const f = el("filter", { id, x: -PAD, y: -PAD, width: w + 2 * PAD, height: h + 2 * PAD, filterUnits: "userSpaceOnUse", primitiveUnits: "userSpaceOnUse", "color-interpolation-filters": "sRGB" });
  el("feImage", { href: makeMap(w, h, radius, band, shift), x: -PAD, y: -PAD, width: w + 2 * PAD, height: h + 2 * PAD, preserveAspectRatio: "none", result: "map" }, f);
  // one displacement per colour channel, each a touch weaker: the colour fringe along the rim
  const channels: [string, number, string][] = [["r", 2 * shift, "1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"], ["g", 2 * shift * 0.96, "0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0"], ["b", 2 * shift * 0.92, "0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"]];
  for (const [c, scale, m] of channels) {
    el("feDisplacementMap", { in: "SourceGraphic", in2: "map", scale, xChannelSelector: "R", yChannelSelector: "G", result: `d${c}` }, f);
    el("feColorMatrix", { in: `d${c}`, type: "matrix", values: m, result: c }, f);
  }
  el("feBlend", { in: "r", in2: "g", mode: "screen", result: "rg" }, f);
  el("feBlend", { in: "rg", in2: "b", mode: "screen", result: "rgb" }, f);
  el("feGaussianBlur", { in: "rgb", stdDeviation: blur, result: "soft" }, f);
  el("feColorMatrix", { in: "soft", type: "saturate", values: frost ? 1.5 : 1.35 }, f);
  return f;
}

/* Only the bars that stay on screen while content scrolls under them refract, and they opt in with `data-refract`: the
   app's top bar, the phone tab bar, the landing nav and the compare tray. Menus, dropdowns, dialogs, drawers, toasts and
   the assistant keep the plain frost (Kamal preferred its softer, richer blur), and so do cards, which only ever sit on the
   background glow. Each refracting panel also costs three displacement passes on every frame. */
const refracts = (node: HTMLElement) => node.hasAttribute("data-refract");

export function LiquidGlass() {
  const svgRef = React.useRef<SVGSVGElement>(null);
  React.useEffect(() => {
    const svg = svgRef.current; if (!svg || !supported()) return;
    const defs = svg.querySelector("defs")!;
    const cache = new Map<string, Entry>();
    const current = new WeakMap<Element, string>();
    let seq = 0;

    // A floating panel always starts with the plain CSS frost (`.lg-glass` matches its blur to the filter's). Refraction
    // (`.lg-on`) switches on only once the filter's map has loaded and nothing is fading the panel: while the panel or an
    // ancestor has opacity below 1 (every open and close animation), Chromium gives the `::before` an empty backdrop, which
    // would show the page behind unblurred.
    const tracked = new Set<HTMLElement>();
    const off = (node: HTMLElement) => {
      node.classList.remove("lg-on", "lg-glass"); node.style.removeProperty("--lg-filter"); node.style.removeProperty("--glass-blur");
      if (node.dataset.lgPos !== undefined) { node.style.removeProperty("position"); delete node.dataset.lgPos; }
      tracked.delete(node);
    };
    const release = (key: string | undefined) => {
      if (!key) return; const e = cache.get(key); if (!e) return;
      e.refs--;
      if (e.refs <= 0 && cache.size > MAX_FILTERS) { e.node.remove(); cache.delete(key); }
    };
    const opaque = (node: HTMLElement) => {
      for (let e: HTMLElement | null = node; e && e !== document.body; e = e.parentElement) if (getComputedStyle(e).opacity !== "1") return false;
      return true;
    };
    // an opacity animation makes Chromium treat the panel as faded even on the frames where its value is still 1
    const fades = new WeakMap<Animation, boolean>();
    const fadesOpacity = (a: Animation) => {
      let v = fades.get(a);
      if (v === undefined) { v = (a as CSSTransition).transitionProperty === "opacity" || !!(a.effect as KeyframeEffect | null)?.getKeyframes().some((k) => "opacity" in k); fades.set(a, v); }
      return v;
    };
    // decide, for every floating panel, whether refraction can show this frame; true while something is still moving
    const settle = () => {
      if (!tracked.size) return false;
      const anims = document.getAnimations().filter((a) => a.playState === "running");
      let busy = false;
      tracked.forEach((node) => {
        const e = cache.get(current.get(node) ?? "");
        const mine = anims.filter((a) => { const t = (a.effect as KeyframeEffect | null)?.target; return !!t && (t === node || t.contains(node)); });
        if (mine.length || !e?.ready) busy = true;
        const on = !!e?.ready && !mine.some(fadesOpacity) && opaque(node);
        if (on !== node.classList.contains("lg-on")) node.classList.toggle("lg-on", on);
      });
      return busy;
    };
    let loop = 0;
    const tick = () => { loop = settle() ? requestAnimationFrame(tick) : 0; };
    const kick = () => { if (!loop) loop = requestAnimationFrame(tick); };
    const apply = (node: HTMLElement) => {
      const cs = getComputedStyle(node);
      // the filter fills the padding box (inside the border), see `.lg-on::before` in styles.css
      const bl = parseFloat(cs.borderLeftWidth) || 0, bt = parseFloat(cs.borderTopWidth) || 0;
      const w = node.offsetWidth - bl - (parseFloat(cs.borderRightWidth) || 0), h = node.offsetHeight - bt - (parseFloat(cs.borderBottomWidth) || 0);
      if (w < 8 || h < 8) return;
      if (!refracts(node)) { release(current.get(node)); current.delete(node); if (tracked.has(node)) off(node); return; }
      const bw = Math.round(w / BUCKET) * BUCKET || BUCKET, bh = Math.round(h / BUCKET) * BUCKET || BUCKET;
      const radius = Math.min(Math.max(0, (parseFloat(cs.borderTopLeftRadius) || 0) - Math.max(bl, bt)), bw / 2, bh / 2);
      const frost = node.classList.contains("glass-pop");
      // `--lg-blur` lets a panel that carries text over busy content (the landing nav) frost a little more
      const blur = parseFloat(cs.getPropertyValue("--lg-blur")) || (frost ? 9 : 2.5);
      const key = `${bw}x${bh}r${Math.round(radius)}${frost ? "f" : "c"}b${blur}`;
      if (current.get(node) === key) return;
      let e = cache.get(key);
      if (!e) {
        const id = `lg-${++seq}`, f = buildFilter(id, bw, bh, radius, frost, blur), entry: Entry = { id, refs: 0, node: f, ready: false };
        defs.appendChild(f); cache.set(key, entry); e = entry;
        // the map is a data URL; decode it before the filter is used, or the first frames bend with an empty map
        const img = new Image(); img.src = f.querySelector("feImage")!.getAttribute("href")!;
        img.decode().catch(() => {}).finally(() => { entry.ready = true; kick(); });
      }
      e.refs++; release(current.get(node)); current.set(node, key);
      node.style.setProperty("--lg-filter", `url(#${e.id})`);
      if (!tracked.has(node)) {
        // the filter's pseudo-element is absolutely placed, so the panel must be positioned
        if (cs.position === "static") { node.style.position = "relative"; node.dataset.lgPos = ""; }
        node.style.setProperty("--glass-blur", `${blur}px`); node.classList.add("lg-glass"); tracked.add(node);
      }
      kick();
    };
    // every open/close animation (CSS keyframes, transitions, or a script's element.animate, which framer-motion uses) starts
    // the check again; it then runs each frame until the animation ends
    const onAnim = () => kick();
    document.addEventListener("animationstart", onAnim, true); document.addEventListener("transitionrun", onAnim, true);
    const animate = Element.prototype.animate;
    Element.prototype.animate = function (this: Element, ...args: Parameters<Element["animate"]>) { kick(); return animate.apply(this, args); };

    const pending = new Set<HTMLElement>(); let raf = 0;
    const flush = () => { raf = 0; pending.forEach((n) => n.isConnected && apply(n)); pending.clear(); };
    const queue = (n: HTMLElement) => { pending.add(n); if (!raf) raf = requestAnimationFrame(flush); };
    const ro = new ResizeObserver((entries) => entries.forEach((en) => queue(en.target as HTMLElement)));
    const watched = new WeakSet<Element>();
    const watch = (root: ParentNode) => root.querySelectorAll<HTMLElement>(".glass, .glass-pop").forEach((n) => { if (!watched.has(n)) { watched.add(n); ro.observe(n); } queue(n); });
    watch(document);
    const mo = new MutationObserver((muts) => {
      for (const m of muts) {
        if (m.type === "attributes") {
          const t = m.target as HTMLElement;
          // a script fading a panel frame by frame (inline opacity), or Radix flipping data-state before its close animation
          if (m.attributeName !== "class") { if (tracked.size && [...tracked].some((n) => t.contains(n))) kick(); continue; }
          if (t.classList.contains("glass") || t.classList.contains("glass-pop")) { if (!watched.has(t)) { watched.add(t); ro.observe(t); } queue(t); } continue; }
        m.addedNodes.forEach((n) => { if (n instanceof HTMLElement) { if (n.matches(".glass, .glass-pop") && !watched.has(n)) { watched.add(n); ro.observe(n); queue(n); } watch(n); } });
        m.removedNodes.forEach((n) => { if (n instanceof HTMLElement) { [n, ...n.querySelectorAll<HTMLElement>(".glass, .glass-pop")].forEach((x) => { release(current.get(x)); current.delete(x); tracked.delete(x); ro.unobserve(x); watched.delete(x); }); } });
      }
    });
    mo.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "data-state", "style"] });
    return () => {
      mo.disconnect(); ro.disconnect(); cancelAnimationFrame(raf); cancelAnimationFrame(loop);
      document.removeEventListener("animationstart", onAnim, true); document.removeEventListener("transitionrun", onAnim, true);
      Element.prototype.animate = animate;
    };
  }, []);
  return (
    <>
      <svg ref={svgRef} aria-hidden width="0" height="0" style={{ position: "absolute", width: 0, height: 0, pointerEvents: "none" }}><defs /></svg>
      {/* A 2px speck of the pop-up frost, always on screen, so the browser has prepared that blur before the first menu opens
          (preparing it on first use can stall a frame on some GPUs). */}
      <div aria-hidden className="glass-pop" style={{ position: "fixed", left: 0, bottom: 0, width: 2, height: 2, pointerEvents: "none", background: "transparent", border: 0, zIndex: 2147483647 }} />
    </>
  );
}
