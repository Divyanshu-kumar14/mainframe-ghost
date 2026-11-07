import type { FuzzReport } from '../data/vectors';
import type { Comp3Description } from '../data/vectors';
import type { SortResult, ZonedResult } from './api';

export type Phase = 'idle' | 'scan' | 'exec' | 'verdict';

/** Where a verdict came from. Shown verbatim in the UI so nothing is passed off as live. */
export type Source = 'live' | 'preset';

export interface Verdict {
  exitCode: number;
  report: FuzzReport;
  screen: string[];
  /** Hook transcript: real hook script output (preset) or verify_stdin summary (live). */
  stdout: string[];
  stderr: string[];
  target: string;
  source: Source;
}

export interface RunState {
  phase: Phase;
  candidateId: string;
  label: string;
  /** 0..1 animation progress for the exec phase. */
  progress: number;
  verdict: Verdict | null;
  error: string | null;
}

export const IDLE: RunState = {
  phase: 'idle',
  candidateId: 'hardened',
  label: '',
  progress: 0,
  verdict: null,
  error: null,
};

export const PHASE_MS = { scan: 650, exec: 2200 } as const;

export type LabResult =
  | { kind: 'comp3'; title: string; data: Comp3Description }
  | { kind: 'zoned'; data: ZonedResult }
  | { kind: 'sort'; data: SortResult }
  | { kind: 'error'; command: string; error: string }
  | { kind: 'busy'; command: string };
