// Typed access to the parity data exported by scripts/export_ui_vectors.py.
// Monetary values stay strings end to end: the UI never parses money into JS numbers.
import captured from './captured_veto.json';
import raw from './parity_vectors.json';

export interface LayoutRow {
  record: string;
  path: string;
  level: number;
  name: string;
  pic: string | null;
  usage: string | null;
  offset: number;
  size: number;
  end: number;
  redefines: string | null;
  sync: boolean;
  slack_before: number;
  slack_range: [number, number] | null;
}

export interface SampleField {
  name: string;
  offset: number;
  size: number;
  hex: string;
  value: string;
  overlay: boolean;
}

export interface Comp3Vector {
  label: string;
  pic: string;
  input: string;
  digits: number;
  scale: number;
  byte_length: number;
  hex: string;
  nibbles: string[];
  sign_nibble: string;
  decoded: string;
}

export interface ZonedVector {
  input: string;
  pic: string;
  hex: string;
  ascii: string;
  decoded: string;
}

export interface Comp3Description {
  pic: string;
  hex: string;
  byte_length: number;
  nibbles: string[];
  sign_nibble: string | null;
  sign_class?: string;
  valid: boolean;
  s0c7: boolean;
  value?: string;
  error?: string;
  invalid_nibble?: string;
  invalid_nibble_index?: number;
  invalid_nibble_kind?: string;
}

export interface FuzzReport {
  passed: boolean;
  drift_pct: string;
  records: number;
  battery: number;
  comparisons: number;
  drifted: number;
  sort_mismatches: number;
  s0c7_unexpected: number;
  abend_mismatches: number;
  s0c7_injected_detected: number;
  candidate_drift: number;
  violations: string[];
  packed_dump_abends: string[];
  examples: string[];
}

export interface HookRun {
  tool_name: string;
  target: string;
  exit_code: number;
  stdout: string[];
  stderr: string[];
}

export interface ServiceRun {
  service: string;
  report: FuzzReport;
  screen: string[];
  hook: HookRun;
}

export interface HookConfig {
  version: string;
  hooks: {
    name: string;
    description: string;
    trigger: string;
    matcher: string;
    action: { type: string; command: string };
    timeout: number;
    enabled: boolean;
  }[];
}

export interface ParityData {
  generated_at: string;
  seed: number;
  records: number;
  copybook: {
    name: string;
    source: string[];
    record_size: number;
    layout: LayoutRow[];
    sample: { bytes: string[]; chars: string[]; owners: string[]; fields: SampleField[] };
  };
  vectors: {
    A: Comp3Vector;
    B: ZonedVector[];
    C: {
      input: string[];
      ascii: string[];
      ebcdic: string[];
      first_bytes: Record<string, { ascii: string; ebcdic: string }>;
    };
    D: Comp3Vector[];
    E: Comp3Description;
  };
  s0c7_samples: Comp3Description[];
  hook_config: HookConfig;
  hardened: ServiceRun;
  vulnerable: ServiceRun | null;
}

export interface CapturedVeto extends HookRun {
  source: string;
  source_excerpt: string[];
}

export const DATA = raw as unknown as ParityData;
export const CAPTURED_VETO = captured as CapturedVeto;

export type ScenarioId = 'hardened' | 'vulnerable';

export interface Scenario {
  id: ScenarioId;
  service: string;
  title: string;
  summary: string;
  hook: HookRun;
  /** Full fuzzer report when the service was actually run; null for the captured veto. */
  report: FuzzReport | null;
  /** IEEE 754 violations found by the hook's scanner. */
  violations: string[];
  /** Screen rendered by engine/shadow_fuzzer.py render_3270, when available. */
  screen: string[] | null;
  provenance: string;
}

const VIOLATION = /Float precision violation.*/;

export const SCENARIOS: Record<ScenarioId, Scenario> = {
  hardened: {
    id: 'hardened',
    service: DATA.hardened.service,
    title: 'HARDENED  decimal.Decimal  ROUND_DOWN',
    summary: 'Context(prec=28, ROUND_DOWN), parse_float=Decimal, CP-037 sort',
    hook: DATA.hardened.hook,
    report: DATA.hardened.report,
    violations: DATA.hardened.report.violations,
    screen: DATA.hardened.screen,
    provenance: `export_ui_vectors.py ran the real hook + ${DATA.records.toLocaleString('en-US')}-record fuzzer`,
  },
  vulnerable: DATA.vulnerable
    ? {
      id: 'vulnerable',
      service: DATA.vulnerable.service,
      title: 'VULNERABLE  IEEE 754 float  round()',
      summary: 'float(), round() banker\u2019s rounding, ASCII sort',
      hook: DATA.vulnerable.hook,
      report: DATA.vulnerable.report,
      violations: DATA.vulnerable.report.violations,
      screen: DATA.vulnerable.screen,
      provenance: 'export_ui_vectors.py ran the real hook + fuzzer on the negative control',
    }
    : {
      id: 'vulnerable',
      service: CAPTURED_VETO.target,
      title: 'VULNERABLE  IEEE 754 float  round()',
      summary: 'float(), round() banker\u2019s rounding, ASCII sort',
      hook: CAPTURED_VETO,
      report: null,
      violations: CAPTURED_VETO.stderr
        .map((line) => VIOLATION.exec(line)?.[0])
        .filter((line): line is string => Boolean(line)),
      screen: null,
      provenance: 'Captured live: Kiro blocked the fs_write of this file (exit 2)',
    },
};

export interface Telemetry {
  records: number;
  battery: number;
  comparisons: number | null;
  engineDrift: string;
  drifted: number;
  sortMismatches: number;
  s0c7Detected: number;
  s0c7Unexpected: number;
  violations: number;
  /** Candidate service vs golden engine; null when the hook blocked it before execution. */
  candidateDrift: number | null;
}

/** Parse the fuzzer summary line, e.g. "[FAIL] drift=0.00000% records=10000 ...". */
function parseSummary(lines: string[]): Record<string, string> {
  const line = lines.find((l) => /^\[(PASS|FAIL)\] drift=/.test(l)) ?? '';
  return Object.fromEntries([...line.matchAll(/(\w+)=(\S+)/g)].map((m) => [m[1], m[2]]));
}

export function telemetry(s: Scenario): Telemetry {
  if (s.report) {
    const rep = s.report;
    return {
      records: rep.records,
      battery: rep.battery,
      comparisons: rep.comparisons,
      engineDrift: rep.drift_pct,
      drifted: rep.drifted,
      sortMismatches: rep.sort_mismatches,
      s0c7Detected: rep.s0c7_injected_detected,
      s0c7Unexpected: rep.s0c7_unexpected,
      violations: rep.violations.length,
      candidateDrift: rep.candidate_drift,
    };
  }
  const kv = parseSummary(s.hook.stderr);
  const int = (key: string) => Number.parseInt(kv[key] ?? '0', 10);
  return {
    records: int('records'),
    battery: int('battery'),
    comparisons: null,
    engineDrift: kv.drift ?? 'n/a',
    drifted: int('drifted'),
    sortMismatches: int('sort_mismatches'),
    s0c7Detected: int('s0c7_injected_detected'),
    s0c7Unexpected: int('s0c7_unexpected'),
    violations: int('violations'),
    candidateDrift: null,
  };
}

export const HOOK = DATA.hook_config.hooks[0];
export const MODEL_ID = 'anthropic.claude-3-5-sonnet-20241022-v2:0';
