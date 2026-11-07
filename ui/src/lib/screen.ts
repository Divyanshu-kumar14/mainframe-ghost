// 80x24 IBM 3270 screen model. Every row is normalized to exactly 80 cells.

export const COLS = 80;
export const ROWS = 24;
export const BODY_ROWS = 19; // rows 3..21; title, rule, command, PF legend and OIA take 5

/** n normal, d dim, h high intensity, r abend red, R red inverse, I phosphor inverse */
export type Tone = 'n' | 'd' | 'h' | 'r' | 'R' | 'I';
export interface Seg {
  t: string;
  c: Tone;
  blink?: boolean;
}
export type Row = Seg[];
export type Cell = string | Seg;

export const n = (t: string): Seg => ({ t, c: 'n' });
export const d = (t: string): Seg => ({ t, c: 'd' });
export const h = (t: string): Seg => ({ t, c: 'h' });
export const r = (t: string): Seg => ({ t, c: 'r' });
export const R = (t: string): Seg => ({ t, c: 'R' });
export const I = (t: string): Seg => ({ t, c: 'I' });

/** Build one row, truncated or space-padded to exactly COLS cells. */
export function row(...cells: Cell[]): Row {
  const out: Row = [];
  let width = 0;
  for (const cell of cells) {
    const seg = typeof cell === 'string' ? n(cell) : cell;
    if (width >= COLS) break;
    const text = seg.t.slice(0, COLS - width);
    if (text) out.push({ ...seg, t: text });
    width += text.length;
  }
  if (width < COLS) out.push(n(' '.repeat(COLS - width)));
  return out;
}

export const blank = (): Row => row();
export const rule = (ch = '-'): Row => row(d(ch.repeat(COLS)));

/** Left and right aligned text on one row. */
export function split(left: Cell, right: Cell): Row {
  const l = typeof left === 'string' ? n(left) : left;
  const rt = typeof right === 'string' ? n(right) : right;
  const gap = Math.max(1, COLS - l.t.length - rt.t.length);
  return row(l, n(' '.repeat(gap)), rt);
}

/** Pad or trim a body to exactly `count` rows. */
export function fit(rows: Row[], count = BODY_ROWS): Row[] {
  const out = rows.slice(0, count);
  while (out.length < count) out.push(blank());
  return out;
}

/** Word-wrap text into lines of at most `width`, continuation lines indented. */
export function wrap(text: string, width = COLS - 1, indent = '   '): string[] {
  const words = text.trim().split(/\s+/);
  const lines: string[] = [];
  let line = '';
  for (const word of words) {
    const prefix = lines.length ? indent : '';
    if (line && (prefix + line + ' ' + word).length > width) {
      lines.push(prefix + line);
      line = word;
    } else {
      line = line ? `${line} ${word}` : word;
    }
  }
  if (line) lines.push((lines.length ? indent : '') + line);
  return lines;
}

export const pad = (value: string | number, width: number): string =>
  String(value).padEnd(width).slice(0, width);
export const lpad = (value: string | number, width: number): string =>
  String(value).padStart(width).slice(-width);
