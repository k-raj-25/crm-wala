"use client";
import { useEffect, useRef } from "react";
import { useTheme } from "@crm/ui";

/* A field of tiny dots behind the hero. Around a point that trails the cursor, the dots in a wide ring wake up: they stretch
   into short coloured dashes pointing at that point, coloured by their angle around it (blue, violet, rose, amber), and
   lean outwards a little. Without a mouse (phones, or before the first move) the point drifts slowly on its own.
   Canvas-drawn, paused off screen, and a still frame for people who prefer reduced motion. */

const SPACING = 34; // px between dots
const PALETTE: [number, number, number][] = [[59, 108, 240], [124, 92, 255], [224, 69, 123], [242, 179, 61], [59, 108, 240]];

function mix(t: number): [number, number, number] {
  const s = ((t % 1) + 1) % 1 * (PALETTE.length - 1), i = Math.floor(s), f = s - i;
  const a = PALETTE[i], b = PALETTE[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

export function DotField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const { resolved } = useTheme();
  const dark = resolved === "dark";

  useEffect(() => {
    const canvas = ref.current; if (!canvas) return;
    const ctx = canvas.getContext("2d"); if (!ctx) return;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, dpr = 1, dots: { x: number; y: number; p: number; w: number }[] = [];
    const focus = { x: 0, y: 0 }, target = { x: 0, y: 0 };
    let pointer = false, visible = true, raf = 0, t0 = performance.now();

    const layout = () => {
      const r = canvas.getBoundingClientRect();
      w = r.width; h = r.height; dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      dots = [];
      // a jittered grid, so it reads as scattered dust rather than graph paper
      let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
      for (let y = SPACING / 2; y < h; y += SPACING) for (let x = SPACING / 2; x < w; x += SPACING)
        dots.push({ x: x + (rnd() - 0.5) * SPACING * 0.8, y: y + (rnd() - 0.5) * SPACING * 0.8, p: rnd() * Math.PI * 2, w: 0.35 + rnd() * 0.65 });
      if (!pointer) { focus.x = target.x = w * 0.68; focus.y = target.y = h * 0.42; }
    };

    const draw = (now: number) => {
      const t = (now - t0) / 1000;
      if (!pointer) { target.x = w * (0.5 + 0.3 * Math.cos(t * 0.25)); target.y = h * (0.45 + 0.22 * Math.sin(t * 0.35)); }
      focus.x += (target.x - focus.x) * 0.06; focus.y += (target.y - focus.y) * 0.06;
      const R = Math.min(Math.max(w, h) * 0.22, 300), band = R * 0.5;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.lineCap = "round";
      const base = dark ? "255,255,255" : "30,41,94";
      for (const d of dots) {
        // idle shimmer: every dot breathes a little on its own
        const x0 = d.x + Math.sin(t * 0.6 + d.p) * 1.2, y0 = d.y + Math.cos(t * 0.5 + d.p) * 1.2;
        const dx = x0 - focus.x, dy = y0 - focus.y, dist = Math.hypot(dx, dy) || 1;
        const k = d.w * Math.exp(-(((dist - R) / band) ** 2)); // up to 1 on the ring, 0 far from it; uneven, so the ring reads as scattered arcs
        if (k < 0.04) {
          ctx.fillStyle = `rgba(${base},${dark ? 0.22 : 0.2})`;
          ctx.fillRect(x0 - 0.6, y0 - 0.6, 1.2, 1.2);
          continue;
        }
        const ux = dx / dist, uy = dy / dist, push = k * 8;
        const cx = x0 + ux * push, cy = y0 + uy * push, len = 1 + k * 5;
        const [r, g, b] = mix(Math.atan2(dy, dx) / (Math.PI * 2) + 0.5 + t * 0.02);
        ctx.strokeStyle = `rgba(${r | 0},${g | 0},${b | 0},${0.15 + k * 0.7})`;
        ctx.lineWidth = 1 + k * 1.6;
        ctx.beginPath(); ctx.moveTo(cx - ux * len / 2, cy - uy * len / 2); ctx.lineTo(cx + ux * len / 2, cy + uy * len / 2); ctx.stroke();
      }
    };

    const loop = (now: number) => { draw(now); raf = visible ? requestAnimationFrame(loop) : 0; };
    const start = () => { if (!raf && !still) raf = requestAnimationFrame(loop); };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      const r = canvas.getBoundingClientRect();
      target.x = e.clientX - r.left; target.y = e.clientY - r.top; pointer = true;
    };
    const ro = new ResizeObserver(() => { layout(); if (still) draw(t0 + 4000); });
    const io = new IntersectionObserver(([en]) => { visible = en.isIntersecting; if (visible) start(); });
    layout();
    ro.observe(canvas); io.observe(canvas);
    window.addEventListener("pointermove", onMove, { passive: true });
    if (still) draw(t0 + 4000); else start();
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); window.removeEventListener("pointermove", onMove); };
  }, [dark]);

  return <canvas ref={ref} aria-hidden className={className} />;
}
