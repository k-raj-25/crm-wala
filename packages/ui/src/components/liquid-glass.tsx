"use client";
import * as React from "react";

/* Liquid glass refraction. Every floating `.glass` / `.glass-pop` element gets its own SVG displacement filter as its backdrop-filter,
   so whatever sits behind it bends like light through a water droplet: strongly pulled and magnified in a band along the
   rounded edge, with a slight lens magnification in the middle. Red, green and blue are displaced by slightly different
   amounts, so the edges fringe with colour. `.glass` stays fairly clear, while `.glass-pop` (menus, dialogs) is frosted over.

   The map depends on the element's size and corner radius, so filters are generated per size bucket and shared by every
   element of that size. Only Chromium renders SVG filters in `backdrop-filter`; other browsers keep the plain blur from
   styles.css. */

const NS = "http://www.w3.org/2000/svg";
const BUCKET = 4; // px; sizes are rounded so near-identical cards share a filter
const MAX_FILTERS = 120;

type Entry = { id: string; refs: number; node: SVGFilterElement };

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

function buildFilter(id: string, w: number, h: number, radius: number, frost: boolean, blur: number, ox: number, oy: number) {
  const band = Math.max(6, Math.min(30, Math.min(w, h) * 0.34));
  const shift = Math.min(band * 1.1, 28);
  const f = el("filter", { id, x: -ox - PAD, y: -oy - PAD, width: w + 2 * PAD, height: h + 2 * PAD, filterUnits: "userSpaceOnUse", primitiveUnits: "userSpaceOnUse", "color-interpolation-filters": "sRGB" });
  el("feImage", { href: makeMap(w, h, radius, band, shift), x: -ox - PAD, y: -oy - PAD, width: w + 2 * PAD, height: h + 2 * PAD, preserveAspectRatio: "none", result: "map" }, f);
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

/* Only glass that floats over content refracts: anything fixed or sticky (top bars, the sidebar, menus, dialogs, drawers,
   toasts, the assistant). Cards in normal flow only ever sit on the soft background glow, where bending shows nothing,
   and each refracting panel costs three displacement passes on every frame, so they keep the plain blur. */
function floats(node: HTMLElement) {
  if (node.hasAttribute("data-glass-still")) return false; // floats, but nothing ever passes behind it (the sidebar)
  for (let e: HTMLElement | null = node; e && e !== document.body; e = e.parentElement) { const p = getComputedStyle(e).position; if (p === "fixed" || p === "sticky") return true; }
  return false;
}

/* Chromium places a backdrop filter's user space at the top-left of the element's visual overflow, not its border box, so a
   drop shadow or a child sticking out would shift the map off the element. Measure that overflow (box shadows reach about
   1.5x their blur) and offset the filter by it. */
function inkOffset(node: HTMLElement) {
  let left = 0, top = 0;
  const cs = getComputedStyle(node);
  for (const part of cs.boxShadow === "none" ? [] : cs.boxShadow.split(/,(?![^(]*\))/)) {
    if (/inset/.test(part)) continue;
    const n = (part.replace(/rgba?\([^)]*\)|#[0-9a-f]+/gi, "").match(/-?[\d.]+px/g) ?? []).map(parseFloat);
    const [x = 0, y = 0, blur = 0, spread = 0] = n;
    left = Math.max(left, blur * 1.5 + spread - x); top = Math.max(top, blur * 1.5 + spread - y);
  }
  if (cs.overflow === "visible") {
    const box = node.getBoundingClientRect();
    const walk = document.createTreeWalker(node, NodeFilter.SHOW_ELEMENT, { acceptNode: (e) => (getComputedStyle(e as Element).overflow !== "visible" ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) });
    for (let i = 0, e = walk.nextNode() as Element | null; e && i < 600; i++, e = walk.nextNode() as Element | null) {
      const r = e.getBoundingClientRect(); if (!r.width && !r.height) continue;
      left = Math.max(left, box.left - r.left); top = Math.max(top, box.top - r.top);
    }
  }
  return [Math.max(0, Math.round(left)), Math.max(0, Math.round(top))];
}

export function LiquidGlass() {
  const svgRef = React.useRef<SVGSVGElement>(null);
  React.useEffect(() => {
    const svg = svgRef.current; if (!svg || !supported()) return;
    const defs = svg.querySelector("defs")!;
    const cache = new Map<string, Entry>();
    const current = new WeakMap<Element, string>();
    let seq = 0;

    const release = (key: string | undefined) => {
      if (!key) return; const e = cache.get(key); if (!e) return;
      e.refs--;
      if (e.refs <= 0 && cache.size > MAX_FILTERS) { e.node.remove(); cache.delete(key); }
    };
    const apply = (node: HTMLElement) => {
      const w = node.offsetWidth, h = node.offsetHeight;
      if (w < 8 || h < 8) return;
      if (!floats(node)) { release(current.get(node)); current.delete(node); if (node.classList.contains("lg-on")) { node.style.removeProperty("backdrop-filter"); node.classList.remove("lg-on"); } return; }
      const bw = Math.round(w / BUCKET) * BUCKET || BUCKET, bh = Math.round(h / BUCKET) * BUCKET || BUCKET;
      const cs = getComputedStyle(node);
      const radius = Math.min(parseFloat(cs.borderTopLeftRadius) || 0, bw / 2, bh / 2);
      const frost = node.classList.contains("glass-pop");
      // `--lg-blur` lets a panel that carries text over busy content (the landing nav) frost a little more
      const blur = parseFloat(cs.getPropertyValue("--lg-blur")) || (frost ? 9 : 2.5);
      const [ox, oy] = inkOffset(node);
      const key = `${bw}x${bh}r${Math.round(radius)}${frost ? "f" : "c"}b${blur}o${ox},${oy}`;
      if (current.get(node) === key) return;
      let e = cache.get(key);
      if (!e) { const id = `lg-${++seq}`; e = { id, refs: 0, node: buildFilter(id, bw, bh, radius, frost, blur, ox, oy) }; defs.appendChild(e.node); cache.set(key, e); }
      e.refs++; release(current.get(node)); current.set(node, key);
      node.style.setProperty("backdrop-filter", `url(#${e.id})`); if (!node.classList.contains("lg-on")) node.classList.add("lg-on");
    };

    const pending = new Set<HTMLElement>(); let raf = 0;
    const flush = () => { raf = 0; pending.forEach((n) => n.isConnected && apply(n)); pending.clear(); };
    const queue = (n: HTMLElement) => { pending.add(n); if (!raf) raf = requestAnimationFrame(flush); };
    const ro = new ResizeObserver((entries) => entries.forEach((en) => queue(en.target as HTMLElement)));
    const watched = new WeakSet<Element>();
    const watch = (root: ParentNode) => root.querySelectorAll<HTMLElement>(".glass, .glass-pop").forEach((n) => { if (!watched.has(n)) { watched.add(n); ro.observe(n); } queue(n); });
    watch(document);
    const mo = new MutationObserver((muts) => {
      for (const m of muts) {
        if (m.type === "attributes") { const t = m.target as HTMLElement; if (t.classList.contains("glass") || t.classList.contains("glass-pop")) { if (!watched.has(t)) { watched.add(t); ro.observe(t); } queue(t); } continue; }
        m.addedNodes.forEach((n) => { if (n instanceof HTMLElement) { if (n.matches(".glass, .glass-pop") && !watched.has(n)) { watched.add(n); ro.observe(n); queue(n); } watch(n); } });
        m.removedNodes.forEach((n) => { if (n instanceof HTMLElement) { [n, ...n.querySelectorAll(".glass, .glass-pop")].forEach((x) => { release(current.get(x)); current.delete(x); ro.unobserve(x); watched.delete(x); }); } });
      }
    });
    mo.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    // a hover that grows a shadow changes the overflow too, so re-measure when a shadow transition ends
    const onTransition = (e: TransitionEvent) => { const t = e.target as HTMLElement; if ((e.propertyName === "box-shadow" || e.propertyName === "all") && t.matches?.(".glass, .glass-pop")) queue(t); };
    document.addEventListener("transitionend", onTransition);
    return () => { document.removeEventListener("transitionend", onTransition); mo.disconnect(); ro.disconnect(); cancelAnimationFrame(raf); };
  }, []);
  return <svg ref={svgRef} aria-hidden width="0" height="0" style={{ position: "absolute", width: 0, height: 0, pointerEvents: "none" }}><defs /></svg>;
}
