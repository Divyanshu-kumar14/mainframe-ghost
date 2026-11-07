import type { ScenarioId } from '../data/vectors';

export type Phase = 'idle' | 'transpile' | 'hook' | 'fuzz' | 'verdict';

export interface RunState {
  phase: Phase;
  scenario: ScenarioId;
  /** Records verified so far in the replayed fuzzer run (0..records). */
  records: number;
  /** Corrupted COMP-3 dumps checked so far (0..battery). */
  battery: number;
  /** Exit code once the hook verdict is in. */
  exitCode: number | null;
}

export const IDLE: RunState = {
  phase: 'idle',
  scenario: 'hardened',
  records: 0,
  battery: 0,
  exitCode: null,
};

export const PHASE_MS = { transpile: 900, hook: 700, fuzz: 2600 } as const;
