"use client";
import * as React from "react";

/* The moving layer between the glow (body::before) and the glass. Each style only animates `transform` and `opacity`,
   so the browser moves already painted layers instead of repainting each frame. Styles live in packages/ui styles.css. */
export type BackdropStyle = "aurora" | "spotlight" | "bokeh";

const ORBS = Array.from({ length: 12 }, (_, i) => ({
  left: (i * 37 + 7) % 100,
  size: 90 + ((i * 53) % 170),
  dur: 34 + ((i * 17) % 30),
  delay: -((i * 11) % 60),
  sway: i % 2 ? 1 : -1,
  tone: i % 3 === 0 ? "b" : "a",
}));

export function Backdrop({ variant }: { variant: BackdropStyle }) {
  const spot = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (variant !== "spotlight") return;
    const el = spot.current;
    if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches || !matchMedia("(pointer: fine)").matches) return;
    let frame = 0;
    const move = (e: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { el.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0)`; el.dataset.follow = ""; });
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => { window.removeEventListener("pointermove", move); cancelAnimationFrame(frame); };
  }, [variant]);

  return (
    <div className={`backdrop backdrop-${variant}`} aria-hidden>
      {variant === "aurora" && <><span className="aurora-band" /><span className="aurora-band aurora-band-2" /></>}
      {variant === "spotlight" && <><span className="spot-grid" /><div ref={spot} className="spot-light" /></>}
      {variant === "bokeh" && ORBS.map((o, i) => (
        <span key={i} className={`bokeh-orb bokeh-${o.tone}`}
          style={{ left: `${o.left}%`, width: o.size, height: o.size, animationDuration: `${o.dur}s`, animationDelay: `${o.delay}s`, ["--sway" as string]: `${o.sway * 40}px` }} />
      ))}
    </div>
  );
}
