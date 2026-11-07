import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GhostTerminal } from './components/GhostTerminal';
import { Sentinel } from './components/Sentinel';
import { DATA, SCENARIOS, telemetry, type ScenarioId } from './data/vectors';
import { terminalAudio } from './lib/audio';
import { PAGES, buildScreen, type PageId } from './lib/pages';
import { IDLE, PHASE_MS, type RunState } from './lib/run';

type Phosphor = 'green' | 'amber';
type Message = { text: string; error: boolean } | null;

const PF_KEYS: Record<string, PageId> = Object.fromEntries(PAGES.map((p) => [p.key, p.id]));

export default function App() {
  const [phosphor, setPhosphor] = useState<Phosphor>('green');
  const [muted, setMuted] = useState(false);
  const [page, setPage] = useState<PageId>('ast');
  const [command, setCommand] = useState('');
  const [message, setMessage] = useState<Message>(null);
  const [run, setRun] = useState<RunState>(IDLE);
  const [selected, setSelected] = useState<ScenarioId>('hardened');
  const [abend, setAbend] = useState(false);
  const [flashKey, setFlashKey] = useState(0);
  const timers = useRef<number[]>([]);
  const frame = useRef<number | null>(null);
  const commandRef = useRef('');
  commandRef.current = command;

  useEffect(() => {
    document.documentElement.dataset.phosphor = phosphor;
  }, [phosphor]);

  useEffect(() => {
    terminalAudio.muted = muted;
  }, [muted]);

  const cancel = useCallback(() => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
  }, []);

  useEffect(() => cancel, [cancel]);

  const raiseAbend = useCallback(() => {
    setAbend(true);
    setFlashKey((k) => k + 1);
    terminalAudio.abendAlarm();
  }, []);

  const deploy = useCallback(
    (id: ScenarioId) => {
      cancel();
      terminalAudio.unlock();
      const scenario = SCENARIOS[id];
      const t = telemetry(scenario);
      setSelected(id);
      setAbend(false);
      setMessage({ text: `deploy_lambda ${scenario.service}: INTERCEPTED BY PreToolUse`, error: false });
      setPage('fuzz');
      setRun({ phase: 'transpile', scenario: id, records: 0, battery: 0, exitCode: null });

      const at = (ms: number, fn: () => void) => timers.current.push(window.setTimeout(fn, ms));
      at(PHASE_MS.transpile, () => setRun((s) => ({ ...s, phase: 'hook' })));
      at(PHASE_MS.transpile + PHASE_MS.hook, () => {
        setRun((s) => ({ ...s, phase: 'fuzz' }));
        const start = performance.now();
        let lastTick = 0;
        const tick = (now: number) => {
          const p = Math.min(1, (now - start) / PHASE_MS.fuzz);
          setRun((s) => ({
            ...s,
            records: Math.floor(p * t.records),
            battery: Math.floor(p * t.battery),
          }));
          if (now - lastTick > 140) {
            terminalAudio.keystroke();
            lastTick = now;
          }
          if (p < 1) {
            frame.current = requestAnimationFrame(tick);
            return;
          }
          frame.current = null;
          const code = scenario.hook.exit_code;
          setRun((s) => ({ ...s, phase: 'verdict', records: t.records, battery: t.battery, exitCode: code }));
          if (code === 0) {
            terminalAudio.passChime();
            setMessage({ text: `EXIT CODE 0  PARITY ${t.engineDrift}  deploy_lambda PROCEEDS`, error: false });
          } else {
            raiseAbend();
            setMessage({ text: `POSIX EXIT CODE ${code}  DEPLOYMENT VETOED`, error: true });
          }
        };
        frame.current = requestAnimationFrame(tick);
      });
    },
    [cancel, raiseAbend],
  );

  const inject = useCallback(() => {
    terminalAudio.unlock();
    setPage('s0c7');
    setMessage({ text: `S0C7 INJECTED: ${DATA.vectors.E.hex} -> ${DATA.vectors.E.error ?? 'ABEND'}`, error: true });
    raiseAbend();
  }, [raiseAbend]);

  const reset = useCallback(() => {
    cancel();
    setRun({ ...IDLE, scenario: selected });
    setAbend(false);
    setMessage(null);
  }, [cancel, selected]);

  const busy = run.phase !== 'idle' && run.phase !== 'verdict';

  const execute = useCallback(
    (raw: string) => {
      const cmd = raw.trim().toUpperCase().replace(/\s+/g, ' ');
      const go = (p: PageId) => {
        setPage(p);
        setMessage(null);
      };
      if (!cmd) return;
      if (['1', 'AST'].includes(cmd)) go('ast');
      else if (['2', 'HEX', 'HEXDUMP'].includes(cmd)) go('hex');
      else if (['3', 'VEC', 'VECTORS'].includes(cmd)) go('vec');
      else if (['4', 'S0C7', 'ABEND', 'INJECT'].includes(cmd)) inject();
      else if (['5', 'FUZZ', 'FUZZER'].includes(cmd)) go('fuzz');
      else if (/^DEPLOY (H|HARDENED|V|VULNERABLE)$/.test(cmd)) {
        if (busy) setMessage({ text: 'SENTINEL BUSY: WAIT FOR THE CURRENT VERDICT', error: true });
        else deploy(cmd.startsWith('DEPLOY H') ? 'hardened' : 'vulnerable');
      }
      else if (['GREEN', 'P31'].includes(cmd)) setPhosphor('green');
      else if (['AMBER', 'P4'].includes(cmd)) setPhosphor('amber');
      else if (['SOUND', 'MUTE'].includes(cmd)) setMuted((m) => !m);
      else if (cmd === 'RESET') reset();
      else setMessage({ text: `INVALID COMMAND: ${cmd.slice(0, 40)}   TRY AST HEX VEC S0C7 FUZZ DEPLOY H|V`, error: true });
    },
    [busy, deploy, inject, reset],
  );

  // 3270 keyboard: PF keys, command line, Enter to execute.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const onButton = target?.tagName === 'BUTTON';
      if (PF_KEYS[e.key]) {
        e.preventDefault();
        terminalAudio.keystroke(true);
        if (PF_KEYS[e.key] === 's0c7') setMessage(null);
        setPage(PF_KEYS[e.key]);
        return;
      }
      if (e.key === 'F9') {
        e.preventDefault();
        terminalAudio.keystroke(true);
        setPhosphor((p) => (p === 'green' ? 'amber' : 'green'));
        return;
      }
      if (onButton && (e.key === 'Enter' || e.key === ' ')) return; // let the button act
      if (e.key === 'Enter') {
        e.preventDefault();
        terminalAudio.keystroke(true);
        const typed = commandRef.current;
        setCommand('');
        execute(typed);
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        terminalAudio.keystroke();
        setCommand((c) => c.slice(0, -1));
      } else if (e.key === 'Escape') {
        terminalAudio.keystroke();
        setCommand('');
        setMessage(null);
      } else if (e.key.length === 1 && /[\x20-\x7e]/.test(e.key)) {
        e.preventDefault();
        terminalAudio.keystroke(e.key === ' ');
        setCommand((c) => (c.length < 60 ? c + e.key.toUpperCase() : c));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [execute]);

  const rows = useMemo(
    () => buildScreen({ page, run, command, message, abend }),
    [page, run, command, message, abend],
  );

  const choosePage = useCallback((p: PageId) => {
    terminalAudio.keystroke(true);
    setMessage(null);
    setPage(p);
  }, []);

  return (
    <div className="mx-auto flex min-h-full max-w-[1680px] flex-col gap-4 p-4 lg:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="phosphor-hi text-lg tracking-[0.35em]">MAINFRAMEGHOST</h1>
          <p className="phosphor-dim text-[11px] tracking-[0.2em]">
            IBM z/OS COBOL &rarr; AWS BEDROCK &amp; LAMBDA // PARITY SENTINEL COCKPIT
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] tracking-[0.2em]">
          <div role="radiogroup" aria-label="Phosphor" className="glow-border flex rounded-sm border">
            {(['green', 'amber'] as const).map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={phosphor === p}
                onClick={() => {
                  terminalAudio.keystroke(true);
                  setPhosphor(p);
                }}
                className={`px-3 py-1.5 ${phosphor === p ? 'ph-inverse' : 'phosphor-dim hover:text-ph'}`}
              >
                {p === 'green' ? 'P31 GREEN' : 'P4 AMBER'}
              </button>
            ))}
          </div>
          <button
            type="button"
            aria-pressed={!muted}
            onClick={() => {
              terminalAudio.unlock();
              setMuted((m) => !m);
            }}
            className="glow-border phosphor rounded-sm border px-3 py-1.5 hover:text-ph-hi"
          >
            SOUND {muted ? 'OFF' : 'ON'}
          </button>
        </div>
      </header>

      <main className="grid flex-1 items-start gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] lg:items-stretch">
        <GhostTerminal rows={rows} page={page} abend={abend} flashKey={flashKey} onPage={choosePage} />
        <Sentinel
          run={run}
          selected={selected}
          onSelect={(id) => {
            terminalAudio.keystroke();
            setSelected(id);
            if (run.phase === 'verdict') setRun({ ...IDLE, scenario: id });
          }}
          onDeploy={deploy}
          onInject={inject}
          onReset={reset}
        />
      </main>

      <footer className="phosphor-dim flex flex-wrap justify-between gap-2 text-[10px] tracking-[0.15em]">
        <span>
          TYPE A COMMAND + ENTER (AST HEX VEC S0C7 FUZZ DEPLOY H|V GREEN AMBER RESET) // PF1-PF5 PANELS // PF9 PHOSPHOR
        </span>
        <span>
          VECTORS: scripts/export_ui_vectors.py @ {DATA.generated_at} // SEED {DATA.seed}
        </span>
      </footer>
    </div>
  );
}
