/* Night-time artwork for the expanding panels: one glowing subject per panel on a near-black field.
   Each SVG is drawn around the centre of a 640×520 canvas (subject within x 0–400) and sliced to fill, so a narrow (collapsed) panel shows the centre strip. */

const Svg = ({ children }: { children: React.ReactNode }) => (
  <svg viewBox="-120 0 640 520" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 size-full" aria-hidden>{children}</svg>
);

/** 01 — a lit tower on still water, blue haze behind, a gold thread of light up its spine. */
export function TowerArt() {
  const lit = [3, 6, 8, 11, 12, 17, 19, 22, 25, 26, 30, 33, 35, 38, 41, 44, 46, 49, 50, 54];
  return (
    <Svg>
      <defs>
        <linearGradient id="t-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#02040a" /><stop offset=".55" stopColor="#0b1d3a" /><stop offset=".7" stopColor="#081326" /><stop offset="1" stopColor="#020309" /></linearGradient>
        <linearGradient id="t-beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffe3a3" stopOpacity="0" /><stop offset=".35" stopColor="#ffd27a" /><stop offset="1" stopColor="#f2a640" /></linearGradient>
        <filter id="t-blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="22" /></filter>
        <filter id="t-glow" x="-200%" y="-20%" width="500%" height="140%"><feGaussianBlur stdDeviation="5" /></filter>
        <filter id="t-soft"><feGaussianBlur stdDeviation="2.5" /></filter>
      </defs>
      <rect x="-120" width="640" height="520" fill="url(#t-sky)" />
      <ellipse cx="200" cy="300" rx="190" ry="70" fill="#2a6ad6" opacity=".45" filter="url(#t-blur)" />
      <ellipse cx="110" cy="250" rx="70" ry="120" fill="#3b82f6" opacity=".22" filter="url(#t-blur)" />
      <ellipse cx="300" cy="240" rx="60" ry="130" fill="#60a5fa" opacity=".18" filter="url(#t-blur)" />
      {[[40, 60], [90, 30], [330, 50], [360, 120], [60, 140], [250, 30], [150, 70], [300, 160]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r="1" fill="#cfe1ff" opacity=".6" />)}
      <g>
        <rect x="165" y="118" width="70" height="252" rx="2" fill="#04060c" stroke="#1d2c48" />
        <rect x="186" y="96" width="28" height="22" fill="#04060c" stroke="#1d2c48" />
        {Array.from({ length: 56 }).map((_, i) => {
          const c = i % 4, r = Math.floor(i / 4);
          return <rect key={i} x={172 + c * 15} y={128 + r * 17} width="9" height="9" rx="1" fill={lit.includes(i) ? "#f6c76d" : "#0f1a2e"} opacity={lit.includes(i) ? 0.9 : 1} />;
        })}
      </g>
      <rect x="196" y="60" width="8" height="310" fill="url(#t-beam)" filter="url(#t-glow)" opacity=".95" />
      <rect x="199" y="80" width="2" height="290" fill="#fff4d6" />
      <rect x="-120" y="370" width="640" height="1" fill="#6c8fcf" opacity=".5" />
      <g transform="translate(0 740) scale(1 -1)" opacity=".28" filter="url(#t-soft)">
        <rect x="165" y="118" width="70" height="252" fill="#0a1426" />
        <rect x="196" y="120" width="8" height="250" fill="#f2a640" />
      </g>
      <rect x="-120" y="372" width="640" height="148" fill="#020309" opacity=".35" />
    </Svg>
  );
}

/** 02 — two threads of warm light spiral toward each other and meet: the client and the flat. */
export function MatchArt() {
  const a = "M70 540 C 340 430, 40 300, 230 220 S 120 40, 330 -20";
  const b = "M330 540 C 60 430, 360 300, 170 220 S 280 40, 70 -20";
  return (
    <Svg>
      <defs>
        <radialGradient id="m-bg" cx=".5" cy=".45" r=".75"><stop offset="0" stopColor="#3a1206" /><stop offset=".45" stopColor="#170704" /><stop offset="1" stopColor="#040202" /></radialGradient>
        <linearGradient id="m-a" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stopColor="#ff7a2f" stopOpacity="0" /><stop offset=".45" stopColor="#ffb36b" /><stop offset="1" stopColor="#ff6a1f" stopOpacity=".1" /></linearGradient>
        <filter id="m-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9" /></filter>
        <filter id="m-dust"><feGaussianBlur stdDeviation="30" /></filter>
      </defs>
      <rect x="-120" width="640" height="520" fill="url(#m-bg)" />
      <ellipse cx="160" cy="180" rx="120" ry="90" fill="#b4380f" opacity=".25" filter="url(#m-dust)" />
      <ellipse cx="260" cy="340" rx="110" ry="80" fill="#7a1f08" opacity=".35" filter="url(#m-dust)" />
      {[a, b].map((d) => (
        <g key={d} fill="none" strokeLinecap="round">
          <path d={d} stroke="#ff7a2f" strokeWidth="16" opacity=".45" filter="url(#m-glow)" />
          <path d={d} stroke="url(#m-a)" strokeWidth="3.5" />
          <path d={d} stroke="#fff1de" strokeWidth="1" opacity=".8" />
        </g>
      ))}
      <circle cx="200" cy="222" r="40" fill="#ffb36b" opacity=".35" filter="url(#m-glow)" />
      <circle cx="200" cy="222" r="5" fill="#fff6e8" />
      {[[120, 120, 1.6], [280, 150, 1.2], [90, 300, 1.4], [310, 280, 1.8], [230, 400, 1.1], [150, 440, 1.5], [250, 90, 1.3], [175, 330, 1]].map(([x, y, r]) => <circle key={`${x}${y}`} cx={x} cy={y} r={r} fill="#ffcf9a" opacity=".85" />)}
    </Svg>
  );
}

/** 03 — an icy ring counting down, like light caught in glass. */
export function HoldArt() {
  const R = 92, C = 2 * Math.PI * R;
  return (
    <Svg>
      <defs>
        <radialGradient id="h-bg" cx=".5" cy=".42" r=".7"><stop offset="0" stopColor="#0d1520" /><stop offset=".6" stopColor="#05070b" /><stop offset="1" stopColor="#020204" /></radialGradient>
        <linearGradient id="h-arc" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#f2f8ff" /><stop offset=".6" stopColor="#9cc7ff" /><stop offset="1" stopColor="#5a8ee8" /></linearGradient>
        <linearGradient id="h-glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffffff" stopOpacity=".18" /><stop offset=".5" stopColor="#ffffff" stopOpacity=".02" /><stop offset="1" stopColor="#9cc7ff" stopOpacity=".12" /></linearGradient>
        <filter id="h-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="8" /></filter>
      </defs>
      <rect x="-120" width="640" height="520" fill="url(#h-bg)" />
      <rect x="92" y="112" width="216" height="216" rx="34" fill="url(#h-glass)" stroke="#cfe3ff" strokeOpacity=".22" />
      <rect x="104" y="124" width="192" height="192" rx="28" fill="none" stroke="#ffffff" strokeOpacity=".06" />
      <g transform="rotate(-90 200 220)">
        <circle cx="200" cy="220" r={R} fill="none" stroke="#ffffff" strokeOpacity=".07" strokeWidth="8" />
        <circle cx="200" cy="220" r={R} fill="none" stroke="#9cc7ff" strokeWidth="14" strokeDasharray={`${C * 0.68} ${C}`} strokeLinecap="round" opacity=".45" filter="url(#h-glow)" />
        <circle cx="200" cy="220" r={R} fill="none" stroke="url(#h-arc)" strokeWidth="5" strokeDasharray={`${C * 0.68} ${C}`} strokeLinecap="round" />
      </g>
      {Array.from({ length: 24 }).map((_, i) => { const t = (i / 24) * Math.PI * 2; return <circle key={i} cx={200 + Math.cos(t) * 74} cy={220 + Math.sin(t) * 74} r={i % 6 === 0 ? 1.8 : 1} fill="#dbeaff" opacity={i % 6 === 0 ? 0.8 : 0.35} />; })}
      <text x="200" y="228" textAnchor="middle" fill="#eef5ff" fontSize="26" fontWeight="600" letterSpacing="1" style={{ fontVariantNumeric: "tabular-nums" }}>23:59</text>
      <text x="200" y="250" textAnchor="middle" fill="#9cb3d6" fontSize="10" letterSpacing="2">HELD</text>
      {[[70, 60], [330, 80], [60, 400], [340, 420], [120, 470], [290, 470]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r="1" fill="#cfe3ff" opacity=".5" />)}
    </Svg>
  );
}

/** 04 — a small warm light floats above an open doorway: the visit. */
export function VisitArt() {
  return (
    <Svg>
      <defs>
        <linearGradient id="v-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#050403" /><stop offset=".6" stopColor="#0c0906" /><stop offset="1" stopColor="#040302" /></linearGradient>
        <radialGradient id="v-orb" cx=".4" cy=".35" r=".7"><stop offset="0" stopColor="#fffaf0" /><stop offset=".55" stopColor="#ecd3a2" /><stop offset="1" stopColor="#a2814f" /></radialGradient>
        <linearGradient id="v-door" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffd08a" stopOpacity=".05" /><stop offset="1" stopColor="#ffc277" stopOpacity=".55" /></linearGradient>
        <filter id="v-halo" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="26" /></filter>
        <filter id="v-soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="12" /></filter>
      </defs>
      <rect x="-120" width="640" height="520" fill="url(#v-bg)" />
      <circle cx="200" cy="170" r="90" fill="#f3c27a" opacity=".22" filter="url(#v-halo)" />
      <circle cx="200" cy="170" r="34" fill="url(#v-orb)" />
      <circle cx="190" cy="160" r="6" fill="#ffffff" opacity=".35" />
      <path d="M150 440 V300 a50 50 0 0 1 100 0 V440 Z" fill="url(#v-door)" stroke="#e8b878" strokeOpacity=".5" />
      <path d="M150 440 V300 a50 50 0 0 1 100 0 V440" fill="none" stroke="#ffd9a1" strokeWidth="6" opacity=".25" filter="url(#v-soft)" />
      <ellipse cx="200" cy="452" rx="120" ry="18" fill="#ffbf6b" opacity=".35" filter="url(#v-soft)" />
      <rect x="-120" y="440" width="640" height="1" fill="#6b5235" opacity=".6" />
    </Svg>
  );
}

/** 05 — a folded sheet of violet light with a gold edge: the deal closing. */
export function CloseArt() {
  return (
    <Svg>
      <defs>
        <radialGradient id="c-bg" cx=".55" cy=".4" r=".7"><stop offset="0" stopColor="#120c24" /><stop offset=".6" stopColor="#06040c" /><stop offset="1" stopColor="#020104" /></radialGradient>
        <linearGradient id="c-sheet" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#2a1a63" /><stop offset=".35" stopColor="#7b62e6" /><stop offset=".55" stopColor="#c9bbff" /><stop offset=".75" stopColor="#5b3fd1" /><stop offset="1" stopColor="#1a0f3d" /></linearGradient>
        <linearGradient id="c-gold" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#e7b45a" stopOpacity="0" /><stop offset=".5" stopColor="#ffd88a" /><stop offset="1" stopColor="#e7b45a" stopOpacity="0" /></linearGradient>
        <filter id="c-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14" /></filter>
        <filter id="c-edge" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" /></filter>
      </defs>
      <rect x="-120" width="640" height="520" fill="url(#c-bg)" />
      <ellipse cx="220" cy="240" rx="130" ry="150" fill="#5b3fd1" opacity=".3" filter="url(#c-glow)" />
      <path d="M250 40 C 230 110, 300 140, 270 210 C 330 230, 350 300, 300 360 C 250 420, 160 400, 120 350 C 80 300, 110 250, 90 200 C 140 220, 170 170, 190 130 C 205 100, 240 80, 250 40 Z" fill="url(#c-sheet)" opacity=".92" />
      <path d="M190 130 C 220 190, 200 260, 250 300 C 280 325, 300 340, 300 360" fill="none" stroke="#1a0f3d" strokeWidth="18" opacity=".55" filter="url(#c-edge)" />
      <path d="M270 210 C 230 250, 180 250, 140 290" fill="none" stroke="#efe9ff" strokeWidth="3" opacity=".6" filter="url(#c-edge)" />
      <path d="M90 200 C 140 220, 170 170, 190 130 C 205 100, 240 80, 250 40" fill="none" stroke="url(#c-gold)" strokeWidth="3" />
      <path d="M120 350 C 160 400, 250 420, 300 360" fill="none" stroke="url(#c-gold)" strokeWidth="2" opacity=".8" />
    </Svg>
  );
}
