import { useEffect, useRef } from 'react';
import { DATA, HOOK, MODEL_ID, SCENARIOS, telemetry, type ScenarioId } from '../data/vectors';
import type { Phase, RunState } from '../lib/run';

interface Props {
  run: RunState;
  selected: ScenarioId;
  onSelect: (id: ScenarioId) => void;
  onDeploy: (id: ScenarioId) => void;
  onInject: () => void;
  onReset: () => void;
}

type StepState = 'wait' | 'run' | 'pass' | 'veto';
const ORDER: Phase[] = ['transpile', 'hook', 'fuzz', 'verdict'];
const fmt = (value: number) => value.toLocaleString('en-US');

function stepState(run: RunState, step: Phase): StepState {
  if (run.phase === 'idle') return 'wait';
  const at = ORDER.indexOf(run.phase);
  const me = ORDER.indexOf(step);
  if (run.phase === 'verdict') {
    if (run.exitCode === 2 && me >= ORDER.indexOf('fuzz')) return 'veto';
    return 'pass';
  }
  if (me < at) return 'pass';
  if (me === at) return 'run';
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

/** AWS & Kiro Sentinel: fuzzer telemetry, PreToolUse hook status, veto banner. */
export function Sentinel({ run, selected, onSelect, onDeploy, onInject, onReset }: Props) {
  const scenario = SCENARIOS[run.phase === 'idle' ? selected : run.scenario];
  const t = telemetry(scenario);
  const done = run.phase === 'verdict';
  const busy = run.phase !== 'idle' && !done;
  const vetoed = done && run.exitCode === 2;
  const passed = done && run.exitCode === 0;
  const records = done ? t.records : run.records;
  const battery = done ? t.battery : run.battery;
  const pct = t.records ? Math.floor((records * 100) / t.records) : 0;

  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [run.phase]);

  return (
    <section
      aria-label="AWS and Kiro Sentinel"
      className="crt-bezel flex max-h-[85vh] min-w-0 flex-col lg:h-0 lg:max-h-none lg:min-h-full"
    >
      <div className="crt-screen min-h-0 flex-1" style={{ borderRadius: '18px' }}>
        <div className="panel-scroll flex h-full flex-col gap-4 overflow-y-auto p-5 text-[13px]">
          <header className="flex items-baseline justify-between">
            <h2 className="phosphor-hi text-base tracking-[0.25em]">AWS &amp; KIRO SENTINEL</h2>
            <span className={`text-[11px] tracking-widest ${vetoed ? 'abend-text' : 'phosphor-dim'}`}>
              {busy ? `${run.phase.toUpperCase()}...` : done ? `EXIT ${run.exitCode}` : 'STANDBY'}
            </span>
          </header>

          {/* ---------------------------------------------------- verdict banner */}
          <div aria-live="assertive">
            {vetoed && (
              <div className="veto-pulse rounded-sm border-2 border-[var(--abend)] bg-[rgba(255,51,51,0.12)] p-4 shadow-[0_0_24px_rgba(255,51,51,0.45)]">
                <div className="abend-inverse inline-block px-2 py-0.5 text-[11px] tracking-[0.3em]">HARD VETO</div>
                <div className="abend-text mt-2 text-2xl font-semibold tracking-wider">POSIX EXIT CODE 2</div>
                <div className="abend-text text-sm tracking-[0.2em]">DEPLOYMENT VETOED // TOOL CALL ABORTED</div>
                <ul className="abend-text mt-2 space-y-0.5 text-[11px]">
                  {scenario.violations.slice(0, 5).map((v, i) => (
                    <li key={i}>&gt; {v}</li>
                  ))}
                </ul>
              </div>
            )}
            {passed && (
              <div className="rounded-sm border-2 border-[var(--ph)] bg-[rgba(var(--ph-glow),0.08)] p-4 shadow-[0_0_20px_rgba(var(--ph-glow),0.35)]">
                <div className="ph-inverse inline-block px-2 py-0.5 text-[11px] tracking-[0.3em]">PARITY VERIFIED</div>
                <div className="phosphor-hi mt-2 text-2xl font-semibold tracking-wider">EXIT CODE 0</div>
                <div className="phosphor text-sm tracking-[0.2em]">
                  {t.engineDrift} DRIFT // DEPLOY_LAMBDA MAY PROCEED
                </div>
              </div>
            )}
          </div>

          {/* ---------------------------------------------------- scenario + actions */}
          <div className="grid grid-cols-2 gap-2">
            {(['hardened', 'vulnerable'] as const).map((id) => {
              const s = SCENARIOS[id];
              const active = selected === id;
              return (
                <button
                  key={id}
                  type="button"
                  disabled={busy}
                  onClick={() => onSelect(id)}
                  className={`rounded-sm border p-2 text-left transition-colors disabled:opacity-60 ${active ? (id === 'vulnerable' ? 'border-[var(--abend)]' : 'border-[var(--ph)]') : 'glow-border opacity-70 hover:opacity-100'
                    }`}
                >
                  <span className={`block text-[11px] tracking-wider ${id === 'vulnerable' ? 'abend-text' : 'phosphor-hi'}`}>
                    {s.title}
                  </span>
                  <span className="phosphor block truncate text-[11px]">{s.service}</span>
                  <span className="phosphor-dim block truncate text-[10px]">{s.summary}</span>
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => onDeploy(selected)}
              className="ph-inverse rounded-sm px-4 py-2 text-[12px] font-semibold tracking-[0.2em] disabled:opacity-50"
            >
              RUN deploy_lambda
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

          {/* ---------------------------------------------------- pipeline */}
          <ol className="space-y-2" aria-label="Deployment pipeline">
            <Step state={stepState(run, 'transpile')} title="AWS BEDROCK TRANSPILE" detail={`${MODEL_ID}  T=0  (offline replay)`} />
            <Step state={stepState(run, 'hook')} title="KIRO PreToolUse HOOK" detail={`matcher ${HOOK.matcher}`} />
            <Step state={stepState(run, 'fuzz')} title="DUAL-ENGINE SHADOW FUZZER" detail={`${fmt(t.records)} records + ${fmt(t.battery)} S0C7 dumps, seed ${DATA.seed}`} />
            <Step
              state={stepState(run, 'verdict')}
              title={vetoed ? 'AWS LAMBDA  BLOCKED' : 'AWS LAMBDA  python3.12'}
              detail={vetoed ? 'never reached: hook returned exit 2' : 'handler services.hardened_service.lambda_handler'}
            />
          </ol>

          {/* ---------------------------------------------------- telemetry */}
          <div>
            <div className="phosphor-dim mb-1 flex justify-between text-[10px] tracking-[0.2em]">
              <span>DIFFERENTIAL FUZZER TELEMETRY</span>
              <span className="tabular-nums">
                {fmt(records)} / {fmt(t.records)}
              </span>
            </div>
            <div className="glow-border h-3 overflow-hidden rounded-sm border">
              <div
                className={`h-full transition-[width] duration-100 ${vetoed ? 'bg-[var(--abend)]' : 'bg-ph'}`}
                style={{ width: `${pct}%`, boxShadow: '0 0 10px currentColor' }}
              />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Metric label="ENGINE DRIFT" value={done ? t.engineDrift : run.phase === 'idle' ? '--' : t.engineDrift} sub="golden vs Decimal engine" />
              <Metric
                label="CANDIDATE DRIFT"
                value={!done ? '--' : t.candidateDrift === null ? 'BLOCKED' : fmt(t.candidateDrift)}
                alert={done && (t.candidateDrift === null || t.candidateDrift > 0)}
                sub={t.candidateDrift === null ? 'vetoed before execution' : `of ${fmt(t.records)} records`}
              />
              <Metric label="IEEE 754 HITS" value={done ? String(t.violations) : '--'} alert={done && t.violations > 0} sub="float() round() literals" />
              <Metric label="S0C7 DETECTED" value={fmt(done ? t.s0c7Detected : Math.floor((battery * t.s0c7Detected) / Math.max(t.battery, 1)))} sub={`of ${fmt(t.battery)} corrupted dumps`} />
              <Metric label="EBCDIC SORT" value={done ? String(t.sortMismatches) : '--'} alert={done && t.sortMismatches > 0} sub="CP-037 order mismatches" />
              <Metric label="S0C7 ON VALID" value={done ? String(t.s0c7Unexpected) : '--'} alert={done && t.s0c7Unexpected > 0} sub="false abends" />
            </div>
          </div>

          {/* ---------------------------------------------------- hook status */}
          <div className="glow-border rounded-sm border p-3">
            <div className="flex items-baseline justify-between">
              <span className="phosphor-hi text-[12px] tracking-[0.2em]">.kiro/hooks/parity_guard.json</span>
              <span
                className={`px-2 text-[12px] font-semibold tabular-nums ${vetoed ? 'abend-inverse' : passed ? 'ph-inverse' : 'phosphor-dim'
                  }`}
              >
                {done ? `EXIT ${run.exitCode}` : busy ? 'RUNNING' : 'ARMED'}
              </span>
            </div>
            <dl className="mt-2 grid grid-cols-[6rem_1fr] gap-x-2 gap-y-0.5 text-[11px]">
              <dt className="phosphor-dim">name</dt>
              <dd className="phosphor truncate">{HOOK.name}</dd>
              <dt className="phosphor-dim">trigger</dt>
              <dd className="phosphor">{HOOK.trigger}</dd>
              <dt className="phosphor-dim">matcher</dt>
              <dd className="phosphor truncate">{HOOK.matcher}</dd>
              <dt className="phosphor-dim">command</dt>
              <dd className="phosphor truncate">{HOOK.action.command}</dd>
              <dt className="phosphor-dim">timeout</dt>
              <dd className="phosphor">{HOOK.timeout}s  //  enabled={String(HOOK.enabled)}</dd>
              <dt className="phosphor-dim">contract</dt>
              <dd className="phosphor">0 = proceed, 2 = hard veto (stderr to agent), other = warning</dd>
            </dl>
            <div
              ref={logRef}
              className="panel-scroll mt-3 max-h-40 overflow-y-auto rounded-sm bg-black/40 p-2 text-[11px] leading-snug"
              aria-label="Hook transcript"
            >
              <div className="phosphor-dim">
                $ echo &apos;{`{"tool_name":"${scenario.hook.tool_name}", ...}`}&apos; | {HOOK.action.command}
              </div>
              {done ? (
                <>
                  {scenario.hook.stdout.map((line, i) => (
                    <div key={`o${i}`} className="phosphor whitespace-pre-wrap">
                      {line}
                    </div>
                  ))}
                  {scenario.hook.stderr.map((line, i) => (
                    <div key={`e${i}`} className="abend-text whitespace-pre-wrap">
                      {line}
                    </div>
                  ))}
                  <div className={vetoed ? 'abend-text' : 'phosphor-hi'}>$ echo $?  =&gt;  {run.exitCode}</div>
                </>
              ) : (
                <div className="phosphor-dim">{busy ? 'waiting for sentinel...' : 'no tool call intercepted yet'}</div>
              )}
            </div>
            <p className="phosphor-dim mt-2 text-[10px]">SOURCE: {scenario.provenance}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
