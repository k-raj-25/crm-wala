/* The moving layer between the glow (body::before) and the glass: a few soft liquid balls in the accent's colours that
   slowly swell, stretch and shrink back. Each ball is two overlapping drops that breathe out of step, so the shape
   bulges and settles like liquid. Only `transform` animates, so nothing repaints. Styles live in packages/ui styles.css. */
const BALLS = [
  { x: 8, y: 6, size: 520, tone: "a", dur: 26, delay: 0 },
  { x: 86, y: 14, size: 420, tone: "b", dur: 31, delay: -9 },
  { x: 58, y: 88, size: 600, tone: "a", dur: 34, delay: -17 },
  { x: 22, y: 70, size: 360, tone: "b", dur: 28, delay: -5 },
];

export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden>
      {BALLS.map((b, i) => (
        <div key={i} className="liquid" style={{ left: `${b.x}%`, top: `${b.y}%`, width: b.size, height: b.size, ["--dur" as string]: `${b.dur}s`, ["--delay" as string]: `${b.delay}s` }}>
          <span className={`liquid-drop liquid-${b.tone}`} />
          <span className={`liquid-drop liquid-drop-2 liquid-${b.tone}`} />
        </div>
      ))}
    </div>
  );
}
