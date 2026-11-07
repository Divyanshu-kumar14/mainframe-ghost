// Client for cockpit/server.py. All numbers travel as strings.
import type { Comp3Description, FuzzReport, LayoutRow } from '../data/vectors';

export interface Health {
  ok: boolean;
  exec_enabled: boolean;
  oracle: { compiler?: string; records?: number; error?: string } | null;
  sandbox: string | null;
}

export interface VerifyResult {
  exit_code: number;
  target: string;
  report: FuzzReport;
  screen: string[];
  summary: string;
}

export interface ZonedResult {
  pic: string;
  text: string;
  valid: boolean;
  s0c7: boolean;
  value?: string;
  error?: string;
  ebcdic_hex?: string | null;
}

export interface SortResult {
  ascii: string[];
  ebcdic: string[];
  first_bytes: Record<string, { ascii: string; ebcdic: string }>;
}

export interface LayoutResult {
  fixed_format: boolean;
  layout: LayoutRow[];
  records: { name: string; size: number }[];
}

export class ApiError extends Error {}

async function post<T>(path: string, body: unknown, timeoutMs = 60000): Promise<T> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    if (!res.ok) throw new ApiError(String((data as { error?: string }).error ?? `HTTP ${res.status}`));
    return data as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError('COCKPIT API OFFLINE: run python3 -m cockpit.server');
  } finally {
    window.clearTimeout(timer);
  }
}

export async function health(): Promise<Health | null> {
  try {
    const res = await fetch('/api/health', { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

export const api = {
  comp3: (hex: string, pic: string) => post<Comp3Description>('/api/comp3', { hex, pic }),
  pack: (value: string, pic: string) => post<Comp3Description>('/api/pack', { value, pic }),
  zoned: (text: string, pic: string) => post<ZonedResult>('/api/zoned', { text, pic }),
  sort: (keys: string[]) => post<SortResult>('/api/sort', { keys }),
  layout: (copybook: string) => post<LayoutResult>('/api/layout', { copybook }),
  verify: (code: string, target: string) => post<VerifyResult>('/api/verify', { code, target }, 90000),
};
