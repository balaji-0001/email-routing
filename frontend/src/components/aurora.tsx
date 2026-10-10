// Flowing-line backdrop. The sign-in screens use it at full strength; the app
// shell uses the `soft` variant so glass surfaces have colour to frost.
// Colours come from the --au-* custom properties set in index.css.

type Curve = [number, number, number, number, number, number, number, number];

const WIDTH = 1440;
const HEIGHT = 900;

// Four currents that sweep top to bottom, left to right. Each neighbouring pair
// bounds one band of lines, so the bands meet without a seam.
const CURRENTS: Curve[] = [
  [-300, -60, 220, 200, -380, 600, 40, 980],
  [270, -60, 840, 240, -80, 540, 690, 980],
  [820, -60, 1100, 320, 540, 560, 1190, 980],
  [1250, -60, 1330, 340, 1050, 640, 1440, 980],
  [1740, -60, 1620, 360, 1700, 660, 1760, 980],
];

// A second current crossing the lower right corner.
const SWELL: [Curve, Curve] = [
  [1560, 300, 1280, 360, 1140, 700, 860, 990],
  [1560, 760, 1450, 800, 1380, 900, 1330, 990],
];

const mix = (a: number, b: number, t: number) => a + (b - a) * t;

function between(from: Curve, to: Curve, t: number) {
  const p = from.map((v, i) => mix(v, to[i], t).toFixed(1));
  return `M${p[0]} ${p[1]}C${p[2]} ${p[3]} ${p[4]} ${p[5]} ${p[6]} ${p[7]}`;
}

function band(from: Curve, to: Curve, count: number, ripples: number) {
  return Array.from({ length: count }, (_, i) => {
    const t = (i + 0.5) / count;
    // Neighbouring lines alternate light and dark; the sine makes ridges of them.
    const ridge = Math.sin(t * Math.PI * ripples) * 0.5 + 0.5;
    return { d: between(from, to, t), light: i % 2 === 0, opacity: +(0.06 + ridge * 0.3).toFixed(2) };
  });
}

function region(from: Curve, to: Curve) {
  const [, , c1x, c1y, c2x, c2y, x1, y1] = to;
  return `${between(from, to, 0)}L${x1} ${y1}C${c2x} ${c2y} ${c1x} ${c1y} ${to[0]} ${to[1]}Z`;
}

const LINES = [
  ...band(CURRENTS[0], CURRENTS[1], 34, 5),
  ...band(CURRENTS[1], CURRENTS[2], 34, 7),
  ...band(CURRENTS[2], CURRENTS[3], 30, 5),
  ...band(CURRENTS[3], CURRENTS[4], 26, 4),
  ...band(SWELL[0], SWELL[1], 26, 5),
];

const REGIONS = [
  { d: region(CURRENTS[0], CURRENTS[1]), tone: 'au-bright' },
  { d: region(CURRENTS[1], CURRENTS[2]), tone: 'au-deep' },
  { d: region(CURRENTS[3], CURRENTS[4]), tone: 'au-night' },
  { d: region(SWELL[0], SWELL[1]), tone: 'au-swell' },
];

export function Aurora({ soft = false }: { soft?: boolean }) {
  return (
    <div className={`aurora ${soft ? 'aurora-soft' : ''}`} aria-hidden="true">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="xMidYMid slice" focusable="false">
        <defs>
          <linearGradient id="au-base" x1="0" y1="0.35" x2="1" y2="0.65">
            <stop offset="0" style={{ stopColor: 'var(--au-0)' }} />
            <stop offset="0.24" style={{ stopColor: 'var(--au-1)' }} />
            <stop offset="0.46" style={{ stopColor: 'var(--au-2)' }} />
            <stop offset="0.64" style={{ stopColor: 'var(--au-3)' }} />
            <stop offset="0.82" style={{ stopColor: 'var(--au-4)' }} />
            <stop offset="1" style={{ stopColor: 'var(--au-5)' }} />
          </linearGradient>
          <filter id="au-blur" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="46" />
          </filter>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#au-base)" />
        <g filter="url(#au-blur)">
          {REGIONS.map((r) => <path key={r.tone} d={r.d} className={r.tone} />)}
        </g>
        <g fill="none" strokeWidth="1.4">
          {LINES.map((l, i) => <path key={i} d={l.d} className={l.light ? 'au-light' : 'au-dark'} strokeOpacity={l.opacity} />)}
        </g>
      </svg>
    </div>
  );
}
