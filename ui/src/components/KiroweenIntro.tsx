import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { DATA, HOOK, candidateById } from '../data/vectors';
import { terminalAudio } from '../lib/audio';

/** sessionStorage key: set to 'true' when the judge opts out of the intro. */
export const INTRO_DISMISSED_KEY = 'kiroween_intro_dismissed';

export type IntroExit = 'cockpit' | 'veto';

interface Props {
  /** Called after the power-off animation. `skip` mirrors the checkbox. */
  onExit: (action: IntroExit, skip: boolean) => void;
}

const EXIT_MS = 480;
const fmt = (value: number) => value.toLocaleString('en-US');

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}

function alreadyDismissed(): boolean {
  try {
    return sessionStorage.getItem(INTRO_DISMISSED_KEY) === 'true';
  } catch {
    return false;
  }
}

// ----------------------------------------------------------------- facts, all from the exported engine data

const FLOAT = candidateById('float');
const ORACLE_VERSION = DATA.oracle.compiler.replace(/^cobc \(GnuCOBOL\)\s*/, '');
const VETO_EXIT = FLOAT?.hook.exit_code ?? 2;
const VETO_STAT = FLOAT
  ? `IEEE 754 PORT: ${fmt(FLOAT.report.candidate_drift)} OF ${fmt(FLOAT.report.candidate_records)} RECORDS DRIFT -> EXIT ${VETO_EXIT}`
  : `FLOAT PORT -> EXIT ${VETO_EXIT}`;

type BootLine = { label: string; status?: string; amber?: boolean; cursor?: boolean };

// Static facts about the exported data, not live probes: the intro cannot see the engine.
const BOOT: BootLine[] = [
  { label: 'MAINFRAMEGHOST COLD START' },
  { label: `ORACLE  ${DATA.oracle.compiler}`, status: 'FIXTURES' },
  { label: `ACCTIN  ${fmt(DATA.records)} BINARY RECORDS`, status: `SEED ${DATA.seed}` },
  { label: `HOOK    ${HOOK.trigger} parity_guard.json`, status: `EXIT ${VETO_EXIT}` },
  { label: 'SPIRIT OF 1959', status: 'RISEN', amber: true },
  { label: 'AWAITING OPERATOR', cursor: true },
];

const BOOT_WIDTH = 46;

interface Lore {
  icon: string;
  kicker: string;
  title: string;
  body: string;
  foot: string;
  tone: 'green' | 'amber';
}

const LORE: Lore[] = [
  {
    icon: '🕯️',
    kicker: 'LORE 01',
    title: 'THE 1959 CURSE',
    body:
      'COBOL dates from 1959 and still runs core banking: an estimated 220B lines moving about $3T a day. Most modernization projects fail or run over budget. This gate targets two bugs a port can hide: IEEE 754 float drift and S0C7 data exceptions.',
    foot: 'FIGURES: INDUSTRY ESTIMATES',
    tone: 'amber',
  },
  {
    icon: '⚡',
    kicker: 'LORE 02',
    title: 'THE COMPILED ORACLE',
    body: `Drift is not judged by another Python model. Each proposed port runs in a sandbox and must match, to the cent and scale, the output of compiled GnuCOBOL ${ORACLE_VERSION} on ${fmt(DATA.records)} binary account records.`,
    foot: 'COBOL OUTPUT: cobol/fixtures/ // SHA-256 PINNED',
    tone: 'green',
  },
  {
    icon: '🛡️',
    kicker: 'LORE 03',
    title: 'THE KIRO SENTINEL',
    body: `Kiro's ${HOOK.trigger} IDE hook intercepts the write, runs the shadow fuzzer, and vetoes drift with POSIX exit code ${VETO_EXIT}. The drifting file is never written.`,
    foot: VETO_STAT,
    tone: 'amber',
  },
];

// ----------------------------------------------------------------- deterministic atmosphere (no Math.random in render)

const SPIRIT_GLYPHS = ['4A', '9D', 'S0C7', '0C', 'F1', 'COMP-3', 'C1', '7F', 'EBCDIC', 'D7', '0D', 'PIC S9', '5B', '1959', 'FF', 'ABEND'];

const SPIRITS = SPIRIT_GLYPHS.map((text, i) => ({
  text,
  amber: i % 3 === 0,
  style: {
    left: `${(i * 61 + 7) % 97}%`,
    '--kw-dur': `${11 + ((i * 37) % 9)}s`,
    '--kw-delay': `-${((i * 1.7) % 14).toFixed(1)}s`,
    '--kw-op': `${0.16 + (i % 4) * 0.06}`,
    '--kw-drift': `${((i % 5) - 2) * 14}px`,
  } as CSSProperties,
}));

const BATS = [
  { top: '11%', dur: '17s', delay: '-3s', scale: 1 },
  { top: '24%', dur: '23s', delay: '-12s', scale: 0.7 },
  { top: '7%', dur: '29s', delay: '-20s', scale: 0.5 },
];

function cobwebPath(size: number): string {
  const angles = [0, 22.5, 45, 67.5, 90].map((a) => (a * Math.PI) / 180);
  const pt = (a: number, r: number) => `${(r * Math.cos(a)).toFixed(1)} ${(r * Math.sin(a)).toFixed(1)}`;
  let d = angles.map((a) => `M0 0L${pt(a, size)}`).join('');
  for (const r of [0.22, 0.45, 0.7, 0.95].map((k) => k * size)) {
    d += `M${pt(angles[0], r)}`;
    for (let i = 1; i < angles.length; i += 1) {
      d += `Q${pt((angles[i - 1] + angles[i]) / 2, r * 0.82)} ${pt(angles[i], r)}`;
    }
  }
  return d;
}

const COBWEB = cobwebPath(150);

// ----------------------------------------------------------------- small decorative SVGs

function Cobweb({ flip }: { flip?: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 150 150"
      className={`pointer-events-none absolute top-0 h-28 w-28 opacity-30 sm:h-40 sm:w-40 ${flip ? 'right-0 -scale-x-100' : 'left-0'}`}
    >
      <path d={COBWEB} fill="none" stroke="#9cff9c" strokeWidth="0.8" />
      <line x1="104" y1="104" x2="104" y2="142" stroke="#9cff9c" strokeWidth="0.6" />
      <circle cx="104" cy="144" r="3" fill="#ff8c00" />
    </svg>
  );
}

function Pumpkin({ className }: { className: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 64 56" className={`kw-pumpkin pointer-events-none absolute ${className}`}>
      <path d="M30 10 Q31 2 37 1" fill="none" stroke="#1f8a1f" strokeWidth="3" strokeLinecap="round" />
      <ellipse cx="32" cy="33" rx="29" ry="21" fill="#a84d00" />
      <ellipse cx="32" cy="33" rx="19" ry="21" fill="#c45c00" />
      <ellipse cx="32" cy="33" rx="8" ry="21" fill="#d96a00" />
      <g className="kw-candle" fill="#ffd36b">
        <path d="M17 27 L23 20 L27 29 Z" />
        <path d="M47 27 L41 20 L37 29 Z" />
        <path d="M14 36 Q32 52 50 36 L45 38 L41 35 L37 40 L32 36 L27 40 L23 35 L19 38 Z" />
      </g>
    </svg>
  );
}

function Bat({ top, dur, delay, scale }: (typeof BATS)[number]) {
  return (
    <div
      aria-hidden="true"
      className="kw-bat"
      style={{ top, '--kw-dur': dur, '--kw-delay': delay } as CSSProperties}
    >
      <svg viewBox="0 0 40 20" width={44 * scale} height={22 * scale} className="kw-bat-wings">
        <path
          d="M20 9 C16 2 10 1 2 4 C6 6 7 9 6 12 C9 10 12 11 14 14 C16 11 18 11 20 13 C22 11 24 11 26 14 C28 11 31 10 34 12 C33 9 34 6 38 4 C30 1 24 2 20 9 Z"
          fill="#020402"
          stroke="rgba(255,140,0,0.55)"
          strokeWidth="0.8"
        />
        <circle cx="18.6" cy="8.6" r="0.8" fill="#ff8c00" />
        <circle cx="21.4" cy="8.6" r="0.8" fill="#ff8c00" />
      </svg>
    </div>
  );
}

/** One tape reel eye: amber rim, rotating hub with three spoke holes. */
function Reel({ cx, slow }: { cx: number; slow?: boolean }) {
  const cy = 104;
  return (
    <g>
      <circle cx={cx} cy={cy} r="18" fill="#021002" stroke="#ff8c00" strokeWidth="3" />
      <g className={slow ? 'kw-reel-slow' : 'kw-reel'}>
        <circle cx={cx} cy={cy} r="14" fill="none" stroke="rgba(255,140,0,0.25)" strokeWidth="1" />
        {[0, 120, 240].map((deg) => {
          const a = (deg * Math.PI) / 180;
          return <circle key={deg} cx={cx + 9 * Math.cos(a)} cy={cy + 9 * Math.sin(a)} r="3.6" fill="#ff8c00" opacity="0.85" />;
        })}
        <circle cx={cx} cy={cy} r="4.5" fill="#33ff33" />
        <rect x={cx - 1} y={cy - 15} width="2" height="4" fill="#33ff33" />
      </g>
    </g>
  );
}

/**
 * Kiro-style ghost insignia: a rounded phosphor ghost with tape-reel eyes,
 * a jack-o'-lantern grin and bat wings. Original artwork, not the Kiro trademark.
 * The base ghost (#kgi-ghost) is cloned through <use> for the chromatic and tear layers.
 */
function GhostInsignia() {
  const body =
    'M64 120 C64 64 94 30 130 30 C166 30 196 64 196 120 L196 196 Q184 214 172 196 Q158 178 144 196 Q130 214 116 196 Q102 178 88 196 Q76 214 64 196 Z';
  const wing = 'M66 96 L40 76 L34 90 L16 82 L20 102 L4 106 L24 122 L40 116 L66 134 Z';
  return (
    <svg
      viewBox="0 0 260 240"
      role="img"
      aria-label="MainframeGhost: a phosphor ghost with tape-reel eyes, a pumpkin grin and bat wings"
      className="h-auto w-full overflow-visible"
    >
      <defs>
        <radialGradient id="kgi-aura" cx="50%" cy="45%" r="50%">
          <stop offset="0%" stopColor="#33ff33" stopOpacity="0.22" />
          <stop offset="55%" stopColor="#9b5cff" stopOpacity="0.08" />
          <stop offset="100%" stopColor="#030803" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="kgi-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#33ff33" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#33ff33" stopOpacity="0.03" />
        </linearGradient>
        <pattern id="kgi-scan" width="4" height="4" patternUnits="userSpaceOnUse">
          <rect width="4" height="1.6" fill="#33ff33" opacity="0.1" />
        </pattern>
        <filter id="kgi-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="kgi-tint-a">
          <feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 0.35  0 0 0 0 0  0 0 0 1 0" />
        </filter>
        <filter id="kgi-tint-b">
          <feColorMatrix type="matrix" values="0 0 0 0 0.2  0 0 0 0 0.85  0 0 0 0 1  0 0 0 1 0" />
        </filter>
        <clipPath id="kgi-band-1">
          <rect x="0" y="88" width="260" height="26" />
        </clipPath>
        <clipPath id="kgi-band-2">
          <rect x="0" y="150" width="260" height="14" />
        </clipPath>
      </defs>

      <ellipse cx="130" cy="120" rx="128" ry="112" fill="url(#kgi-aura)" />
      <ellipse className="kw-shadow" cx="130" cy="228" rx="54" ry="7" fill="#33ff33" opacity="0.45" filter="url(#kgi-glow)" />

      <g filter="url(#kgi-glow)">
        <g id="kgi-ghost" className="kw-bob">
          {/* bat wings */}
          <path className="kw-wing" d={wing} fill="#120a02" stroke="#ff8c00" strokeWidth="2" strokeLinejoin="round" />
          <g transform="matrix(-1 0 0 1 260 0)">
            <path className="kw-wing" d={wing} fill="#120a02" stroke="#ff8c00" strokeWidth="2" strokeLinejoin="round" />
          </g>

          {/* antenna */}
          <line x1="130" y1="30" x2="130" y2="14" stroke="#33ff33" strokeWidth="2" />
          <circle className="blink" cx="130" cy="11" r="4" fill="#ff8c00" />

          {/* body */}
          <path d={body} fill="url(#kgi-body)" />
          <path d={body} fill="url(#kgi-scan)" />
          <path d={body} fill="none" stroke="#33ff33" strokeWidth="3" strokeLinejoin="round" />

          {/* tape-reel eyes on a shared tape path */}
          <path d="M106 122 Q130 130 154 122" fill="none" stroke="#996a00" strokeWidth="2" />
          <rect x="124" y="123" width="12" height="5" rx="1" fill="#33ff33" opacity="0.8" />
          <Reel cx={106} />
          <Reel cx={154} slow />

          {/* jack-o'-lantern grin */}
          <path
            className="kw-candle"
            d="M102 146 Q130 176 158 146 L150 150 L144 145 L137 153 L130 147 L123 153 L116 145 L110 150 Z"
            fill="#ff8c00"
          />

          {/* chest plate */}
          <text x="130" y="186" textAnchor="middle" fontSize="10" letterSpacing="3" fill="#1f8a1f" fontFamily="IBM Plex Mono, monospace">
            3270
          </text>
          <rect x="113" y="168" width="6" height="3" fill="#33ff33" />
          <rect className="blink" x="127" y="168" width="6" height="3" fill="#ff8c00" />
          <rect x="141" y="168" width="6" height="3" fill="#33ff33" />
        </g>
      </g>

      {/* chromatic ghosts and horizontal tears, visible only during sync loss */}
      <use href="#kgi-ghost" className="kw-chroma-a" filter="url(#kgi-tint-a)" />
      <use href="#kgi-ghost" className="kw-chroma-b" filter="url(#kgi-tint-b)" />
      <g clipPath="url(#kgi-band-1)">
        <use href="#kgi-ghost" className="kw-tear" />
      </g>
      <g clipPath="url(#kgi-band-2)">
        <use href="#kgi-ghost" className="kw-tear-rev" />
      </g>
    </svg>
  );
}

// ----------------------------------------------------------------- the intro

/** Full-viewport Kiroween 2026 showcase shown before the 3270 cockpit. */
export function KiroweenIntro({ onExit }: Props) {
  const [skip, setSkip] = useState<boolean>(alreadyDismissed);
  const [exiting, setExiting] = useState<IntroExit | null>(null);
  const [booted, setBooted] = useState<number>(() => (reducedMotion() ? BOOT.length : 0));
  const skipRef = useRef(skip);
  skipRef.current = skip;
  const leaving = useRef(false);
  const timer = useRef<number | null>(null);
  const primary = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    primary.current?.focus({ preventScroll: true });
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, []);

  // Cold-boot log types itself out one line at a time.
  useEffect(() => {
    if (booted >= BOOT.length) return;
    const id = window.setTimeout(() => setBooted((n) => n + 1), booted === 0 ? 380 : 270);
    return () => window.clearTimeout(id);
  }, [booted]);

  const leave = useCallback(
    (action: IntroExit) => {
      if (leaving.current) return;
      leaving.current = true;
      // Inside the user gesture: unlocks Web Audio for the cockpit too.
      terminalAudio.unlock();
      terminalAudio.keystroke(true);
      setExiting(action);
      timer.current = window.setTimeout(() => onExit(action, skipRef.current), reducedMotion() ? 0 : EXIT_MS);
    },
    [onExit],
  );

  // Enter / Space / Escape boot the cockpit. Focused buttons and the checkbox keep their native keys.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (e.key === 'Enter' || e.key === ' ') {
        if (tag === 'BUTTON') return;
        if (tag === 'INPUT' && e.key === ' ') return;
        e.preventDefault();
        leave('cockpit');
      } else if (e.key === 'Escape') {
        e.preventDefault();
        leave('cockpit');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [leave]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="kw-title"
      aria-describedby="kw-tagline"
      className={`kw-root fixed inset-0 z-50 overflow-x-hidden overflow-y-auto ${exiting ? 'kw-power-off' : ''}`}
    >
      {/* atmosphere */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 overflow-hidden">
        <Cobweb />
        <Cobweb flip />
        {BATS.map((b) => (
          <Bat key={b.top} {...b} />
        ))}
        {SPIRITS.map((s) => (
          <span key={s.text} className={`kw-spirit ${s.amber ? 'kw-amber' : 'kw-green'}`} style={s.style}>
            {s.text}
          </span>
        ))}
        <div className="kw-fog" />
        <Pumpkin className="bottom-3 left-3 w-14 sm:w-20" />
        <Pumpkin className="bottom-3 right-3 w-12 sm:w-16" />
      </div>

      {/* CRT glass */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-20 overflow-hidden">
        <div className="crt-roll" />
        <div className="crt-scanlines absolute inset-0" />
        <div className="crt-vignette absolute inset-0" />
      </div>

      <div className="crt-power-on relative z-10 min-h-full">
        <div className="crt-flicker mx-auto flex min-h-full max-w-6xl flex-col justify-center gap-7 px-5 py-8 sm:px-8">
          {/* hero */}
          <section className="grid items-center gap-6 md:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
            <div className="kw-hsync mx-auto w-full max-w-[300px] md:max-w-[340px]">
              <GhostInsignia />
            </div>

            <div className="flex min-w-0 flex-col gap-4">
              <p className="kw-amber text-[11px] tracking-[0.35em] sm:text-xs">
                <span aria-hidden="true">🎃 </span>KIROWEEN 2026 // RESURRECTION
              </p>
              <h1 id="kw-title" className="kw-hsync font-semibold leading-none" style={{ fontSize: 'clamp(1.9rem, 5.4vw, 4.25rem)' }}>
                <span className="kw-title" data-text="MAINFRAMEGHOST">
                  MAINFRAMEGHOST
                </span>
              </h1>
              <p id="kw-tagline" className="kw-soft max-w-xl text-sm leading-relaxed sm:text-[15px]">
                Mainframe COBOL arithmetic, resurrected byte for byte. A Kiro hook blocks any proposed port whose output
                differs from the compiled COBOL by a single cent.
              </p>

              <pre
                aria-label="Cold boot log"
                className="overflow-hidden rounded-sm border-l-2 border-[#ff8c00]/60 bg-black/40 px-3 py-2 text-[10px] leading-[1.6] sm:text-[11px]"
              >
                {BOOT.slice(0, booted).map((line) => (
                  <div key={line.label} className={line.amber ? 'kw-amber' : line.cursor ? 'kw-green' : 'kw-dim'}>
                    {line.status ? `${`${line.label} `.padEnd(BOOT_WIDTH, '.')} ` : line.label}
                    {line.status && <span className={line.amber ? 'kw-amber' : 'kw-green'}>{line.status}</span>}
                    {line.cursor && <span className="blink"> █</span>}
                  </div>
                ))}
                {booted < BOOT.length && <span className="blink kw-green">█</span>}
              </pre>
            </div>
          </section>

          {/* lore cards */}
          <section aria-label="The pitch" className="grid gap-4 md:grid-cols-3">
            {LORE.map((card, i) => (
              <article
                key={card.title}
                data-tone={card.tone}
                className="kw-card kw-rise-in flex flex-col gap-3 rounded-sm p-5"
                style={{ '--kw-delay': `${250 + i * 160}ms` } as CSSProperties}
              >
                <header className="flex items-center gap-3">
                  <span aria-hidden="true" className="text-2xl">
                    {card.icon}
                  </span>
                  <div>
                    <p className="kw-dim text-[10px] tracking-[0.3em]">{card.kicker}</p>
                    <h2 className={`${card.tone === 'amber' ? 'kw-amber' : 'kw-green'} text-sm font-semibold tracking-[0.18em]`}>
                      {card.title}
                    </h2>
                  </div>
                </header>
                <p className="kw-soft flex-1 text-[13px] leading-relaxed">{card.body}</p>
                <p className="kw-dim border-t border-[#33ff33]/15 pt-2 text-[10px] tracking-[0.12em]">{card.foot}</p>
              </article>
            ))}
          </section>

          {/* actions */}
          <section
            aria-label="Enter"
            className="kw-rise-in flex flex-col items-center gap-4"
            style={{ '--kw-delay': '760ms' } as CSSProperties}
          >
            <div className="flex w-full flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
              <button
                ref={primary}
                type="button"
                disabled={exiting !== null}
                onClick={() => leave('cockpit')}
                className="kw-btn-primary rounded-sm px-6 py-4 text-sm font-semibold tracking-[0.2em] sm:text-base"
              >
                [ ⚡ INITIALIZE 3270 COCKPIT ]
              </button>
              <button
                type="button"
                disabled={exiting !== null}
                onClick={() => leave('veto')}
                title={VETO_STAT}
                className="kw-btn-veto rounded-sm px-5 py-3 text-xs font-semibold tracking-[0.14em] sm:text-[13px]"
              >
                [ ⚠️ Trigger Float Drift VETO (Exit {VETO_EXIT}) ]
              </button>
            </div>

            <label className="kw-soft flex cursor-pointer items-center gap-2 text-xs tracking-[0.1em]">
              <input
                type="checkbox"
                checked={skip}
                onChange={(e) => setSkip(e.target.checked)}
                className="h-4 w-4 cursor-pointer accent-[#ff8c00]"
              />
              Skip intro on subsequent visits
            </label>

            <p className="kw-dim text-center text-[10px] tracking-[0.2em]">
              ENTER / SPACE INITIALIZE // F12 OR COMMAND INTRO REOPENS THIS SCREEN
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
