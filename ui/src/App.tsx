import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GhostTerminal } from './components/GhostTerminal';
import { Sentinel } from './components/Sentinel';
import { ALIASES, CANDIDATES, DATA, candidateById, type Candidate } from './data/vectors';
import { api, ApiError, health, type Health, type VerifyResult } from './lib/api';
import { terminalAudio } from './lib/audio';
import { DEFAULT_LAYOUT, PAGES, buildScreen, type LayoutView, type PageId } from './lib/pages';
import { IDLE, PHASE_MS, type LabResult, type RunState, type Verdict } from './lib/run';

type Phosphor = 'green' | 'amber';
type Message = { text: string; error: boolean } | null;
export type ApiState = Health | null | 'checking';

const PF_KEYS: Record<string, PageId> = Object.fromEntries(PAGES.map((p) => [p.key, p.id]));
const CUSTOM_TARGET = 'services/candidate_service.py';
const COPYBOOK_TEXT = DATA.copybook.source.join('\n');

function presetVerdict(c: Candidate): Verdict {
  return {
    exitCode: c.hook.exit_code,
    report: c.report,
    screen: c.screen,
    stdout: c.hook.stdout,
    stderr: c.hook.stderr,
    target: c.target,
    source: 'preset',
  };
}

function liveVerdict(res: VerifyResult): Verdict {
  const rep = res.report;
  const vetoLines = [
    res.summary,
    ...rep.violations.map((v) => `  ${v}`),
    ...rep.candidate_errors.map((e) => `  Candidate veto: ${e}`),
    ...rep.examples.slice(0, 6).map((e) => `  ${e}`),
    '[VETO] Mainframe Parity Sentinel: semantic drift, S0C7 abend, or IEEE 754 precision violation detected.',
  ];
  return {
    exitCode: res.exit_code,
    report: rep,
    screen: res.screen,
    stdout: res.exit_code === 0 ? ['[PASS] Parity verified: 0.00000% drift against the GnuCOBOL oracle.', res.summary] : [],
    stderr: res.exit_code === 0 ? [] : vetoLines,
    target: res.target,
    source: 'live',
  };
}

export default function App() {
  const [phosphor, setPhosphor] = useState<Phosphor>('green');
  const [muted, setMuted] = useState(false);
  const [page, setPage] = useState<PageId>('fuzz');
  const [command, setCommand] = useState('');
  const [message, setMessage] = useState<Message>(null);
  const [run, setRun] = useState<RunState>(IDLE);
  const [selected, setSelected] = useState<string>('hardened');
  const [code, setCode] = useState<string>(() => (candidateById('hardened')?.source ?? []).join('\n'));
  const [edited, setEdited] = useState(false);
  const [abend, setAbend] = useState(false);
  const [flashKey, setFlashKey] = useState(0);
  const [apiState, setApiState] = useState<ApiState>('checking');
  const [layout, setLayout] = useState<LayoutView>(DEFAULT_LAYOUT);
  const [copybook, setCopybook] = useState(COPYBOOK_TEXT);
  const [lab, setLab] = useState<LabResult | null>(null);
  const timers = useRef<number[]>([]);
  const frame = useRef<number | null>(null);
  const runToken = useRef(0);
  const commandRef = useRef('');
  commandRef.current = command;

  useEffect(() => {
    document.documentElement.dataset.phosphor = phosphor;
  }, [phosphor]);

  useEffect(() => {
    terminalAudio.muted = muted;
  }, [muted]);

  useEffect(() => {
    let alive = true;
    health().then((h) => alive && setApiState(h));
    return () => {
      alive = false;
    };
  }, []);

  const live = apiState !== 'checking' && apiState !== null && apiState.exec_enabled;
  const apiUp = apiState !== 'checking' && apiState !== null;

  const cancel = useCallback(() => {
    runToken.current += 1;
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

  const selectCandidate = useCallback(
    (id: string) => {
      const c = candidateById(id);
      if (!c) return;
      setSelected(id);
      setCode(c.source.join('\n'));
      setEdited(false);
      if (run.phase === 'verdict') setRun({ ...IDLE, candidateId: id });
    },
    [run.phase],
  );

  const deploy = useCallback(
    (id: string, source: string, isEdited: boolean) => {
      const cand = candidateById(id);
      if (!live && (isEdited || !cand)) {
        setMessage({ text: 'EDITED CODE NEEDS THE LOCAL ENGINE: python3 -m cockpit.server', error: true });
        return;
      }
      cancel();
      const token = runToken.current;
      terminalAudio.unlock();
      setAbend(false);
      setPage('fuzz');
      const label = isEdited || !cand ? `${cand?.target ?? CUSTOM_TARGET} (edited)` : cand.file;
      const target = cand?.target ?? CUSTOM_TARGET;
      setMessage({ text: `fs_write ${target}: INTERCEPTED BY PreToolUse`, error: false });
      setRun({ phase: 'scan', candidateId: id, label, progress: 0, verdict: null, error: null });

      let result: Verdict | null = null;
      let failure: string | null = null;
      const pending = live
        ? api.verify(source, target).then(liveVerdict)
        : Promise.resolve(presetVerdict(cand as Candidate));
      pending
        .then((v) => {
          result = v;
        })
        .catch((err: unknown) => {
          failure = err instanceof ApiError ? err.message : String(err);
        });

      const finish = (v: Verdict) => {
        setRun((s) => ({ ...s, phase: 'verdict', progress: 1, verdict: v }));
        if (v.exitCode === 0) {
          terminalAudio.passChime();
          setMessage({ text: `EXIT CODE 0  PARITY ${v.report.drift_pct}  WRITE PROCEEDS`, error: false });
        } else {
          raiseAbend();
          setMessage({ text: `POSIX EXIT CODE ${v.exitCode}  WRITE VETOED`, error: true });
        }
      };

      timers.current.push(
        window.setTimeout(() => {
          if (token !== runToken.current) return;
          setRun((s) => ({ ...s, phase: 'exec' }));
          const start = performance.now();
          const tick = (now: number) => {
            if (token !== runToken.current) return;
            const elapsed = now - start;
            const p = Math.min(result || failure ? 1 : 0.97, elapsed / PHASE_MS.exec);
            setRun((s) => ({ ...s, progress: p }));
            if (failure) {
              frame.current = null;
              setRun((s) => ({ ...s, phase: 'exec', error: failure }));
              setMessage({ text: `SENTINEL ERROR: ${failure}`.slice(0, 76), error: true });
              return;
            }
            if (result && p >= 1) {
              frame.current = null;
              finish(result);
              return;
            }
            frame.current = requestAnimationFrame(tick);
          };
          frame.current = requestAnimationFrame(tick);
        }, PHASE_MS.scan),
      );
    },
    [cancel, live, raiseAbend],
  );

  const inject = useCallback(() => {
    terminalAudio.unlock();
    setPage('s0c7');
    setMessage({ text: `S0C7 INJECTED: ${DATA.vectors.E.hex} -> ${DATA.vectors.E.error ?? 'ABEND'}`, error: true });
    raiseAbend();
  }, [raiseAbend]);

  const reset = useCallback(() => {
    cancel();
    setRun({ ...IDLE, candidateId: selected });
    setAbend(false);
    setMessage(null);
  }, [cancel, selected]);

  const parseCopybook = useCallback(async (text: string) => {
    terminalAudio.unlock();
    try {
      const res = await api.layout(text);
      const rec = res.records[0];
      setLayout({ name: 'PASTED COPYBOOK', recordSize: rec?.size ?? 0, layout: res.layout, custom: true });
      setMessage({ text: `COPYBOOK PARSED: ${res.records.length} RECORD(S), ${res.layout.length} FIELDS`, error: false });
    } catch (err) {
      setMessage({ text: `COPYBOOK ERROR: ${err instanceof Error ? err.message : String(err)}`.slice(0, 76), error: true });
    }
    setPage('ast');
  }, []);

  const runLab = useCallback(async (raw: string, verb: string, args: string[]) => {
    setPage('lab');
    setMessage(null);
    setLab({ kind: 'busy', command: raw });
    try {
      if (verb === 'UNPACK' && args.length === 2) {
        const data = await api.comp3(args[0], args[1]);
        setLab({ kind: 'comp3', title: `UNPACK ${data.hex}`, data });
        if (data.s0c7) raiseAbend();
      } else if (verb === 'PACK' && args.length === 2) {
        const data = await api.pack(args[0], args[1]);
        setLab({ kind: 'comp3', title: `PACK ${args[0]}`, data });
      } else if (verb === 'ZONED' && args.length === 2) {
        const data = await api.zoned(args[0], args[1]);
        setLab({ kind: 'zoned', data });
        if (data.s0c7) raiseAbend();
      } else if (verb === 'SORT' && args.length >= 2) {
        setLab({ kind: 'sort', data: await api.sort(args) });
      } else {
        setLab({ kind: 'error', command: raw, error: `USAGE: ${verb} NEEDS ${verb === 'SORT' ? 'TWO OR MORE KEYS' : '<input> <pic>'}` });
      }
    } catch (err) {
      setLab({ kind: 'error', command: raw, error: err instanceof Error ? err.message : String(err) });
    }
  }, [raiseAbend]);

  const busy = run.phase !== 'idle' && run.phase !== 'verdict' && !run.error;

  const execute = useCallback(
    (raw: string) => {
      const text = raw.trim().replace(/\s+/g, ' ');
      if (!text) return;
      const [first, ...args] = text.split(' ');
      const verb = first.toUpperCase();
      const cmd = text.toUpperCase();
      const go = (p: PageId) => {
        setPage(p);
        setMessage(null);
      };
      if (['1', 'AST'].includes(cmd)) go('ast');
      else if (['2', 'HEX', 'HEXDUMP'].includes(cmd)) go('hex');
      else if (['3', 'VEC', 'VECTORS'].includes(cmd)) go('vec');
      else if (['4', 'S0C7', 'ABEND', 'INJECT'].includes(cmd)) inject();
      else if (['5', 'FUZZ', 'SENTINEL'].includes(cmd)) go('fuzz');
      else if (['6', 'LAB', 'HELP'].includes(cmd)) {
        setLab(null);
        go('lab');
      } else if (['UNPACK', 'PACK', 'ZONED', 'SORT'].includes(verb)) void runLab(text, verb, args);
      else if (verb === 'LAYOUT') void parseCopybook(copybook);
      else if (verb === 'DEPLOY' && args.length === 1) {
        const id = ALIASES[args[0].toUpperCase()] ?? args[0].toLowerCase();
        if (busy) setMessage({ text: 'SENTINEL BUSY: WAIT FOR THE CURRENT VERDICT', error: true });
        else if (!candidateById(id)) setMessage({ text: `UNKNOWN CANDIDATE ${args[0]}`, error: true });
        else {
          selectCandidate(id);
          deploy(id, (candidateById(id) as Candidate).source.join('\n'), false);
        }
      } else if (['GREEN', 'P31'].includes(cmd)) setPhosphor('green');
      else if (['AMBER', 'P4'].includes(cmd)) setPhosphor('amber');
      else if (['SOUND', 'MUTE'].includes(cmd)) setMuted((m) => !m);
      else if (cmd === 'RESET') reset();
      else setMessage({ text: `INVALID COMMAND: ${cmd.slice(0, 30)}   TRY LAB FOR HELP, DEPLOY H|V|FLOOR|U`, error: true });
    },
    [busy, copybook, deploy, inject, parseCopybook, reset, runLab, selectCandidate],
  );

  // 3270 keyboard: PF keys, command line, Enter to execute. Text fields keep their keys.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const editing = tag === 'TEXTAREA' || tag === 'INPUT' || target?.isContentEditable;
      if (PF_KEYS[e.key]) {
        e.preventDefault();
        terminalAudio.keystroke(true);
        if (PF_KEYS[e.key] === 'lab') setLab(null);
        setMessage(null);
        setPage(PF_KEYS[e.key]);
        return;
      }
      if (e.key === 'F9') {
        e.preventDefault();
        terminalAudio.keystroke(true);
        setPhosphor((p) => (p === 'green' ? 'amber' : 'green'));
        return;
      }
      if (editing) return;
      if (tag === 'BUTTON' && (e.key === 'Enter' || e.key === ' ')) return; // let the button act
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
        setCommand((c) => (c.length < 64 ? c + e.key : c));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [execute]);

  const rows = useMemo(
    () => buildScreen({ page, run, command, message, abend, layout, lab }),
    [page, run, command, message, abend, layout, lab],
  );

  const choosePage = useCallback((p: PageId) => {
    terminalAudio.keystroke(true);
    setMessage(null);
    if (p === 'lab') setLab(null);
    setPage(p);
  }, []);

  const mode = apiState === 'checking' ? 'CHECKING ENGINE' : live ? 'LIVE ENGINE' : apiUp ? 'PUBLIC: PRESET VERDICTS' : 'OFFLINE: PRESET VERDICTS';

  return (
    <div className="mx-auto flex min-h-full max-w-[1680px] flex-col gap-4 p-4 lg:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="phosphor-hi text-lg tracking-[0.35em]">MAINFRAMEGHOST</h1>
          <p className="phosphor-dim text-[11px] tracking-[0.2em]">
            KIRO PreToolUse GATE FOR AI-PORTED COBOL // VERIFIED AGAINST GNUCOBOL, BYTE FOR BYTE
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] tracking-[0.2em]">
          <span
            title={live ? `cockpit/server.py on this machine, sandbox ${typeof apiState === 'object' && apiState ? apiState.sandbox : ''}` : 'Verdicts were exported by scripts/export_ui_vectors.py from the real hook'}
            className={`rounded-sm border px-3 py-1.5 ${live ? 'ph-inverse border-transparent' : 'glow-border phosphor-dim'}`}
          >
            {mode}
          </span>
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
          candidates={CANDIDATES}
          selected={selected}
          onSelect={(id) => {
            terminalAudio.keystroke();
            selectCandidate(id);
          }}
          code={code}
          edited={edited}
          onCode={(text) => {
            setCode(text);
            setEdited(true);
          }}
          onRestore={() => selectCandidate(selected)}
          onDeploy={() => deploy(selected, code, edited)}
          onInject={inject}
          onReset={reset}
          live={live}
          apiUp={apiUp}
          copybook={copybook}
          onCopybook={setCopybook}
          onParse={() => void parseCopybook(copybook)}
          layoutCustom={layout.custom}
          onLayoutReset={() => {
            setLayout(DEFAULT_LAYOUT);
            setCopybook(COPYBOOK_TEXT);
            setPage('ast');
          }}
        />
      </main>

      <footer className="phosphor-dim flex flex-wrap justify-between gap-2 text-[10px] tracking-[0.15em]">
        <span>
          COMMANDS: DEPLOY H|V|FLOOR|U  UNPACK  PACK  ZONED  SORT  LAYOUT  GREEN AMBER RESET // PF1-PF6 PANELS // PF9 PHOSPHOR
        </span>
        <span>
          PRESETS: scripts/export_ui_vectors.py @ {DATA.generated_at} // SEED {DATA.seed}
        </span>
      </footer>
    </div>
  );
}
