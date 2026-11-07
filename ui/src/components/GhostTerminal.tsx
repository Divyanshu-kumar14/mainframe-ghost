import { memo } from 'react';
import { PAGES, type PageId } from '../lib/pages';
import type { Row, Tone } from '../lib/screen';

const TONE_CLASS: Record<Tone, string> = {
  n: 'phosphor',
  d: 'phosphor-dim',
  h: 'phosphor-hi font-semibold',
  r: 'abend-text',
  R: 'abend-inverse font-semibold',
  I: 'ph-inverse',
};

interface Props {
  rows: Row[];
  page: PageId;
  abend: boolean;
  flashKey: number;
  onPage: (page: PageId) => void;
}

/** 80x24 Mainframe Ghost Terminal inside a CRT tube. */
function GhostTerminalImpl({ rows, page, abend, flashKey, onPage }: Props) {
  return (
    <section aria-label="Mainframe Ghost Terminal" className="flex min-w-0 flex-col gap-3">
      <div className="crt-bezel">
        <div className="crt-screen crt-power-on" style={{ aspectRatio: '4 / 3.05' }}>
          <div className="crt-roll" />
          {abend && <div key={flashKey} className="crt-abend pointer-events-none absolute inset-0 z-[1]" />}
          <div className="term-host crt-flicker relative z-0 flex h-full flex-col justify-center px-[3.2%] py-[3%]">
            <div className="term-grid" role="log" aria-live="polite">
              {rows.map((segs, y) => (
                <div key={y}>
                  {segs.map((seg, x) => (
                    <span key={x} className={`${TONE_CLASS[seg.c]} ${seg.blink ? 'blink' : ''}`}>
                      {seg.t}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between px-2 text-[10px] tracking-[0.3em] text-stone-500">
          <span>IBM 3278 MODEL 2 // DISPLAY STATION</span>
          <span className="flex items-center gap-2">
            <span
              className={`inline-block h-2 w-2 rounded-full ${abend ? 'bg-[var(--abend)] shadow-[0_0_8px_var(--abend)]' : 'bg-ph shadow-[0_0_8px_var(--ph)]'}`}
            />
            POWER
          </span>
        </div>
      </div>

      <nav aria-label="Program function keys" className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {PAGES.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onPage(p.id)}
            className={`rounded-sm border px-2 py-2 text-left text-[11px] leading-tight tracking-wider transition-colors ${page === p.id ? 'ph-inverse border-transparent' : 'glow-border phosphor-dim hover:text-ph'
              }`}
          >
            <span className="block font-semibold">{p.key.replace('F', 'PF')}</span>
            <span className="block">{p.label}</span>
          </button>
        ))}
      </nav>
    </section>
  );
}

export const GhostTerminal = memo(GhostTerminalImpl);
