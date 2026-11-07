// Typed access to the parity data exported by scripts/export_ui_vectors.py.
// Monetary values stay strings end to end: the UI never parses money into JS numbers.
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
  input?: string;
  error?: string;
  invalid_nibble?: string;
  invalid_nibble_index?: number;
  invalid_nibble_kind?: string;
}

/** engine/shadow_fuzzer.py ParityReport.as_dict() */
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
  candidate_records: number;
  candidate_drift_pct: string;
  candidate_ledger_delta: string;
  candidate_misposted: string;
  candidate_source: string;
  candidate_errors: string[];
  sandbox: string;
  oracle: string;
  oracle_mismatches: number;
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

export interface Candidate {
  id: string;
  title: string;
  summary: string;
  file: string;
  target: string;
  provenance: string;
  source: string[];
  report: FuzzReport;
  screen: string[];
  hook: HookRun;
  meta: Record<string, unknown> | null;
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

export interface OracleInfo {
  compiler: string;
  runner: string;
  compile: string[];
  records: number;
  generated_at: string;
  sha256: Record<string, string>;
  program: string;
  procedure: string[];
  sample: {
    key: string;
    balance: string;
    rate: string;
    interest_hex: string;
    interest: string;
    new_balance_zoned: string;
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
  oracle: OracleInfo;
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
  candidates: Candidate[];
}

export const DATA = raw as unknown as ParityData;
export const CANDIDATES: Candidate[] = DATA.candidates;
export const HOOK = DATA.hook_config.hooks[0];
export const ORACLE = DATA.oracle;

export function candidateById(id: string): Candidate | undefined {
  return CANDIDATES.find((c) => c.id === id);
}

/** Short command aliases for DEPLOY <x>. */
export const ALIASES: Record<string, string> = {
  H: 'hardened',
  HARDENED: 'hardened',
  V: 'float',
  F: 'float',
  FLOAT: 'float',
  VULNERABLE: 'float',
  FLOOR: 'floor',
  U: 'halfup',
  HALFUP: 'halfup',
};

export interface Telemetry {
  records: number;
  battery: number;
  comparisons: number;
  engineDrift: string;
  candidateRecords: number;
  candidateDrift: number;
  candidateDriftPct: string;
  misposted: string;
  netDelta: string;
  sortMismatches: number;
  s0c7Detected: number;
  s0c7Unexpected: number;
  violations: number;
  oracleMismatches: number;
}

export function telemetry(rep: FuzzReport): Telemetry {
  return {
    records: rep.records,
    battery: rep.battery,
    comparisons: rep.comparisons,
    engineDrift: rep.drift_pct,
    candidateRecords: rep.candidate_records,
    candidateDrift: rep.candidate_drift,
    candidateDriftPct: rep.candidate_drift_pct,
    misposted: rep.candidate_misposted,
    netDelta: rep.candidate_ledger_delta,
    sortMismatches: rep.sort_mismatches,
    s0c7Detected: rep.s0c7_injected_detected,
    s0c7Unexpected: rep.s0c7_unexpected,
    violations: rep.violations.length,
    oracleMismatches: rep.oracle_mismatches,
  };
}
