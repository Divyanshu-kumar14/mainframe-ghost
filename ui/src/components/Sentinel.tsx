import { useEffect, useRef, useState } from 'react';
import { HOOK, ORACLE, telemetry, type Candidate } from '../data/vectors';
import type { Phase, RunState } from '../lib/run';

interface Props {
  run: RunState;
  candidates: Candidate[];
  selected: string;
  onSelect: (id: string) => void;
  code: string;
  edited: boolean;
  onCode: (text: string) => void;
  onRestore: () => void;
  onDeploy: () => void;
  onInject: () => void;
  onReset: () => void;
  live: boolean;
  apiUp: boolean;
  copybook: string;
  onCopybook: (text: string) => void;
  onParse: () => void;
  layoutCustom: boolean;
  onLayoutReset: () => void;
}

type StepState = 'wait' | 'run' | 'pass' | 'veto';
const ORDER: Phase[] = ['scan', 'exec', 'verdict'];
const fmt = (value: number) => value.toLocaleString('en-US');

function stepState(run: RunState, step: Phase, failed: boolean): StepState {
  if (run.phase === 'idle') return 'wait';
  const at = ORDER.indexOf(run.phase);
  const me = ORDER.indexOf(step);
  if (run.phase === 'verdict') return failed && me >= ORDER.indexOf('exec') ? 'veto' : 'pass';
  if (me < at) return 'pass';
  if (me === at) return run.error ? 'veto' : 'run';
  return 'wait';
}

const GLYPH: Record<StepState, string> = { wait: '[  ]', run: '[>>]', pass: '[OK]', veto: '[XX]' };

function Step({ state, title, detail }: { state: StepState; title: string; detail: string }) {
  const tone =
    state === 'veto' ? 'abend-text' : state === 'pass' ? 'phosphor-hi' : state === 'run' ? 'phosphor blink' : 'phosphor-dim';
  return (
    <li className="flex gap-3">
      <span className={`shrink-0 ${tone}`}>{GLYPH[state]}</span>
      <span className="min-w-0">
        <span className={state === 'veto' ? 'abend-text' : 'phosphor'}>{title}</span>
        <span className="phosphor-dim block truncate text-[11px]">{detail}</span>
      </span>
    </li>
  );
}

function Metric({ label, value, alert = false, sub }: { label: string; value: string; alert?: boolean; sub?: string }) {
  return (
    <div className="glow-border rounded-sm border px-3 py-2">
      <div className="phosphor-dim text-[10px] tracking-[0.2em]">{label}</div>
      <div className={`text-xl tabular-nums ${alert ? 'abend-text' : 'phosphor-hi'}`}>{value}</div>
      {sub && <div className="phosphor-dim truncate text-[10px]">{sub}</div>}
    </div>
  );
}

/** Kiro Sentinel: candidate picker / editor, copybook parser, verdict and telemetry. */
export function Sentinel(props: Props) {
  const { run, candidates, selected, onSelect, code, edited, onCode, onRestore, onDeploy, onInject, onReset, live, apiUp } = props;
  const [tab, setTab] = useState<'candidate' | 'copybook'>('candidate');
  const verdict = run.phase === 'verdict' ? run.verdict : null;
  const busy = run.phase !== 'idle' && run.phase !== 'verdict' && !run.error;
  const vetoed = verdict !== null && verdict.exitCode !== 0;
  const passed = verdict !== null && verdict.exitCode === 0;
  const t = verdict ? telemetry(verdict.report) : null;
  const cand = candidates.find((c) => c.id === selected);
  const canRun = live || !edited;

  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [run.phase]);

  const reasons = verdict
    ? [...verdict.report.violations, ...verdict.report.candidate_errors].slice(0, 5)
    : [];

  return (
    <section
      aria-label="Kiro Sentinel"
      className="crt-bezel flex max-h-[85vh] min-w-0 flex-col lg:h-0 lg:max-h-none lg:min-h-full"
    >
      <div className="crt-screen min-h-0 flex-1" style={{ borderRadius: '18px' }}>
        <div className="panel-scroll flex h-full flex-col gap-4 overflow-y-auto p-5 text-[13px]">
          <header className="flex items-baseline justify-between">
            <h2 className="phosphor-hi text-base tracking-[0.25em]">KIRO PARITY SENTINEL</h2>
            <span className={`text-[11px] tracking-widest ${vetoed ? 'abend-text' : 'phosphor-dim'}`}>
              {busy ? `${run.phase.toUpperCase()}...` : verdict ? `EXIT ${verdict.exitCode}` : 'ARMED'}
            </span>
          </header>

          {/* ---------------------------------------------------- verdict banner */}
          <div aria-live="assertive">
            {vetoed && t && (
              <div className="veto-pulse rounded-sm border-2 border-[var(--abend)] bg-[rgba(255,51,51,0.12)] p-4 shadow-[0_0_24px_rgba(255,51,51,0.45)]">
                <div className="abend-inverse inline-block px-2 py-0.5 text-[11px] tracking-[0.3em]">HARD VETO</div>
                <div className="abend-text mt-2 text-2xl font-semibold tracking-wider">POSIX EXIT CODE 2</div>
                <div className="abend-text text-sm tracking-[0.2em]">fs_write BLOCKED // FILE NEVER WRITTEN</div>
                {t.candidateRecords > 0 && (
                  <div className="abend-text mt-1 text-[12px]">
                    {fmt(t.candidateDrift)} OF {fmt(t.candidateRecords)} ACCOUNTS ({t.candidateDriftPct}) DIFFER FROM COBOL //
                    ${t.misposted} MISPOSTED
                  </div>
                )}
                <ul className="abend-text mt-2 space-y-0.5 text-[11px]">
                  {reasons.map((v, i) => (
                    <li key={i}>&gt; {v}</li>
                  ))}
                </ul>
              </div>
            )}
            {passed && t && (
              <div className="rounded-sm border-2 border-[var(--ph)] bg-[rgba(var(--ph-glow),0.08)] p-4 shadow-[0_0_20px_rgba(var(--ph-glow),0.35)]">
                <div className="ph-inverse inline-block px-2 py-0.5 text-[11px] tracking-[0.3em]">PARITY VERIFIED</div>
                <div className="phosphor-hi mt-2 text-2xl font-semibold tracking-wider">EXIT CODE 0</div>
                <div className="phosphor text-sm tracking-[0.2em]">
                  {t.candidateRecords ? `${fmt(t.candidateRecords)} / ${fmt(t.candidateRecords)} ACCOUNTS MATCH COBOL` : `${t.engineDrift} DRIFT`} // WRITE PROCEEDS
                </div>
              </div>
            )}
            {run.error && (
              <div className="rounded-sm border border-[var(--abend)] p-3 abend-text text-[12px]">SENTINEL ERROR: {run.error}</div>
            )}
          </div>

          {/* ---------------------------------------------------- tabs */}
          <div role="tablist" className="flex gap-2 text-[11px] tracking-[0.2em]">
            {(['candidate', 'copybook'] as const).map((id) => (
              <button
                key={id}
                role="tab"
                type="button"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`rounded-sm border px-3 py-1 ${tab === id ? 'ph-inverse border-transparent' : 'glow-border phosphor-dim hover:text-ph'}`}
              >
                {id === 'candidate' ? 'CANDIDATE SERVICE' : 'COPYBOOK'}
              </button>
            ))}
          </div>

          {tab === 'candidate' ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                {candidates.map((c) => {
                  const active = selected === c.id;
                  const bad = c.hook.exit_code !== 0;
                  return (
                    <button
                      key={c.id}
                      type="button"
                      disabled={busy}
                      onClick={() => onSelect(c.id)}
                      className={`rounded-sm border p-2 text-left transition-colors disabled:opacity-60 ${active ? (bad ? 'border-[var(--abend)]' : 'border-[var(--ph)]') : 'glow-border opacity-70 hover:opacity-100'}`}
                    >
                      <span className={`block text-[11px] tracking-wider ${bad ? 'abend-text' : 'phosphor-hi'}`}>{c.title}</span>
                      <span className="phosphor block truncate text-[11px]">{c.file}</span>
                      <span className="phosphor-dim block truncate text-[10px]">{c.summary}</span>
                    </button>
                  );
                })}
              </div>
              <div>
                <div className="phosphor-dim mb-1 flex justify-between text-[10px] tracking-[0.2em]">
                  <span>
                    PROPOSED fs_write {cand?.target ?? ''} {edited ? '(EDITED)' : ''}
                  </span>
                  {edited && (
                    <button type="button" onClick={onRestore} className="phosphor hover:text-ph-hi">
                      RESTORE
                    </button>
                  )}
                </div>
                <textarea
                  aria-label="Candidate source code"
                  spellCheck={false}
                  value={code}
                  onChange={(e) => onCode(e.target.value)}
                  readOnly={!live}
                  rows={12}
                  className="glow-border phosphor panel-scroll w-full resize-y rounded-sm border bg-black/50 p-2 font-[inherit] text-[11px] leading-snug outline-none focus:border-[var(--ph)]"
                />
                <p className="phosphor-dim mt-1 text-[10px]">
                  {live
                    ? 'EDIT FREELY: RUN SENDS THIS CODE TO verify_stdin(), THE SAME FUNCTION THE HOOK SCRIPT CALLS.'
                    : 'READ ONLY: VERDICTS BELOW WERE PRODUCED BY THE REAL HOOK. RUN python3 -m cockpit.server TO VERIFY YOUR OWN CODE.'}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy || !canRun}
                  onClick={onDeploy}
                  className="ph-inverse rounded-sm px-4 py-2 text-[12px] font-semibold tracking-[0.2em] disabled:opacity-50"
                >
                  RUN PreToolUse HOOK
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={onInject}
                  className="abend-text rounded-sm border border-[var(--abend)] px-3 py-2 text-[12px] tracking-[0.15em] hover:bg-[rgba(255,51,51,0.12)] disabled:opacity-50"
                >
                  INJECT S0C7
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={onReset}
                  className="glow-border phosphor-dim rounded-sm border px-3 py-2 text-[12px] tracking-[0.15em] hover:text-ph disabled:opacity-50"
                >
                  RESET
                </button>
              </div>
            </>
          ) : (
            <div>
              <textarea
                aria-label="COBOL copybook"
                spellCheck={false}
                value={props.copybook}
                onChange={(e) => props.onCopybook(e.target.value)}
                rows={14}
                className="glow-border phosphor panel-scroll w-full resize-y rounded-sm border bg-black/50 p-2 font-[inherit] text-[11px] leading-snug outline-none focus:border-[var(--ph)]"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={!apiUp}
                  onClick={props.onParse}
                  className="ph-inverse rounded-sm px-4 py-2 text-[12px] font-semibold tracking-[0.2em] disabled:opacity-50"
                >
                  PARSE LAYOUT &rarr; PF1
                </button>
                {props.layoutCustom && (
                  <button type="button" onClick={props.onLayoutReset} className="glow-border phosphor-dim rounded-sm border px-3 py-2 text-[12px]">
                    BACK TO INTACCR
                  </button>
                )}
              </div>
              <p className="phosphor-dim mt-1 text-[10px]">
                {apiUp
                  ? 'PARSED BY engine/copybook_parser.py: LEVELS 01-49, PIC, COMP/COMP-3/DISPLAY, REDEFINES, SYNC SLACK.'
                  : 'COPYBOOK PARSING NEEDS THE COCKPIT API (python3 -m cockpit.server).'}
              </p>
            </div>
          )}

          {/* ---------------------------------------------------- pipeline */}
          <ol className="space-y-2" aria-label="Hook pipeline">
            <Step state={stepState(run, 'scan', vetoed)} title="KIRO PreToolUse HOOK" detail={`${HOOK.matcher}  ->  ${HOOK.action.command}`} />
            <Step
              state={stepState(run, 'exec', vetoed)}
              title="STATIC SCAN + SANDBOXED RUN"
              detail={`IEEE 754 tokens, then ${fmt(ORACLE.records)} records in a child process (python -I, no env, no network)`}
            />
            <Step
              state={stepState(run, 'verdict', vetoed)}
              title={vetoed ? 'WRITE BLOCKED  EXIT 2' : `DIFF vs ${ORACLE.compiler.replace('cobc ', '').toUpperCase()}`}
              detail={vetoed ? 'stderr returned to the agent; file never reaches disk' : `COMP-3 + zoned bytes from ${ORACLE.program}`}
            />
          </ol>

          {/* ---------------------------------------------------- telemetry */}
          <div>
            <div className="phosphor-dim mb-1 flex justify-between text-[10px] tracking-[0.2em]">
              <span>CANDIDATE vs GNUCOBOL</span>
              <span className="tabular-nums">
                {fmt(Math.floor((verdict ? 1 : run.progress) * ORACLE.records))} / {fmt(ORACLE.records)}
              </span>
            </div>
            <div className="glow-border h-3 overflow-hidden rounded-sm border">
              <div
                className={`h-full transition-[width] duration-100 ${vetoed ? 'bg-[var(--abend)]' : 'bg-ph'}`}
                style={{ width: `${Math.floor((verdict ? 1 : run.progress) * 100)}%`, boxShadow: '0 0 10px currentColor' }}
              />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Metric
                label="CANDIDATE DRIFT"
                value={t ? (t.candidateRecords ? fmt(t.candidateDrift) : 'n/a') : '--'}
                alert={!!t && t.candidateDrift > 0}
                sub={t && t.candidateRecords ? `${t.candidateDriftPct} of ${fmt(t.candidateRecords)} accounts` : 'accounts that differ from COBOL'}
              />
              <Metric label="MISPOSTED" value={t ? `$${t.misposted}` : '--'} alert={!!t && t.misposted !== '0.00' && t.misposted !== '0'} sub={t ? `net ledger delta $${t.netDelta}` : 'sum |candidate - COBOL|'} />
              <Metric label="IEEE 754 HITS" value={t ? String(t.violations) : '--'} alert={!!t && t.violations > 0} sub="float() round() literals" />
              <Metric label="ENGINE vs COBOL" value={t ? String(t.oracleMismatches) : '--'} alert={!!t && t.oracleMismatches > 0} sub="golden + Decimal engine self-check" />
              <Metric label="S0C7 DETECTED" value={t ? fmt(t.s0c7Detected) : '--'} sub={t ? `of ${fmt(t.battery)} corrupted dumps` : 'corrupted COMP-3 battery'} />
              <Metric label="EBCDIC SORT" value={t ? String(t.sortMismatches) : '--'} alert={!!t && t.sortMismatches > 0} sub="vs COBOL SORT order" />
            </div>
          </div>

          {/* ---------------------------------------------------- hook transcript */}
          <div className="glow-border rounded-sm border p-3">
            <div className="flex items-baseline justify-between">
              <span className="phosphor-hi text-[12px] tracking-[0.2em]">.kiro/hooks/parity_guard.json</span>
              <span className={`px-2 text-[12px] font-semibold tabular-nums ${vetoed ? 'abend-inverse' : passed ? 'ph-inverse' : 'phosphor-dim'}`}>
                {verdict ? `EXIT ${verdict.exitCode}` : busy ? 'RUNNING' : 'ARMED'}
              </span>
            </div>
            <dl className="mt-2 grid grid-cols-[6rem_1fr] gap-x-2 gap-y-0.5 text-[11px]">
              <dt className="phosphor-dim">trigger</dt>
              <dd className="phosphor">{HOOK.trigger}  //  timeout {HOOK.timeout}s</dd>
              <dt className="phosphor-dim">matcher</dt>
              <dd className="phosphor truncate">{HOOK.matcher}</dd>
              <dt className="phosphor-dim">contract</dt>
              <dd className="phosphor">0 = proceed, 2 = hard veto (stderr to agent)</dd>
              <dt className="phosphor-dim">sandbox</dt>
              <dd className="phosphor truncate">{verdict?.report.sandbox || 'python -I -B, empty env, rlimits, unshare --net'}</dd>
            </dl>
            <div
              ref={logRef}
              className="panel-scroll mt-3 max-h-44 overflow-y-auto rounded-sm bg-black/40 p-2 text-[11px] leading-snug"
              aria-label="Hook transcript"
            >
              <div className="phosphor-dim">
                $ echo &apos;{`{"tool_name":"fs_write","tool_input":{"path":"${verdict?.target ?? cand?.target ?? ''}",...}}`}&apos; | {HOOK.action.command}
              </div>
              {verdict ? (
                <>
                  {verdict.stdout.map((line, i) => (
                    <div key={`o${i}`} className="phosphor whitespace-pre-wrap">
                      {line}
                    </div>
                  ))}
                  {verdict.stderr.map((line, i) => (
                    <div key={`e${i}`} className="abend-text whitespace-pre-wrap">
                      {line}
                    </div>
                  ))}
                  <div className={vetoed ? 'abend-text' : 'phosphor-hi'}>$ echo $?  =&gt;  {verdict.exitCode}</div>
                </>
              ) : (
                <div className="phosphor-dim">{busy ? 'waiting for sentinel...' : 'no tool call intercepted yet'}</div>
              )}
            </div>
            <p className="phosphor-dim mt-2 text-[10px]">
              SOURCE:{' '}
              {verdict
                ? verdict.source === 'live'
                  ? 'live: verify_stdin() in cockpit/server.py on this machine'
                  : `preset: real hook output exported by scripts/export_ui_vectors.py (${cand?.provenance ?? ''})`
                : cand?.provenance}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
