// 3270 panels. Every value shown comes from parity_vectors.json (engine output).
import { CAPTURED_VETO, DATA, SCENARIOS, telemetry, type Comp3Vector, type LayoutRow, type Scenario } from '../data/vectors';
import type { RunState } from './run';
import {
  BODY_ROWS,
  COLS,
  I,
  R,
  blank,
  d,
  fit,
  h,
  lpad,
  n,
  pad,
  r,
  row,
  wrap,
  type Row,
  type Seg,
} from './screen';

export type PageId = 'ast' | 'hex' | 'vec' | 's0c7' | 'fuzz';

export const PAGES: { id: PageId; key: string; label: string; title: string }[] = [
  { id: 'ast', key: 'F1', label: 'AST', title: 'COPYBOOK AST / BYTE LAYOUT' },
  { id: 'hex', key: 'F2', label: 'HEXDUMP', title: 'EBCDIC / COMP-3 HEX DUMP' },
  { id: 'vec', key: 'F3', label: 'VECTORS', title: 'GOLDEN TEST VECTORS A-D' },
  { id: 's0c7', key: 'F4', label: 'S0C7', title: 'S0C7 DATA EXCEPTION MONITOR' },
  { id: 'fuzz', key: 'F5', label: 'FUZZER', title: 'DUAL-ENGINE SHADOW FUZZER' },
];

const book = DATA.copybook;
const fmt = (value: number) => value.toLocaleString('en-US');
const isOverlay = (f: LayoutRow) =>
  book.layout.some((g) => g.redefines && f.path.startsWith(`${g.path}.`));

// ------------------------------------------------------------------------- PF1 AST

function astPage(): Row[] {
  const rows: Row[] = [
    row(h(` ${book.name}   01 ${book.layout[0].name}   RECORD LENGTH ${book.record_size} BYTES`)),
    row(d(' LVL  NAME              PIC        USAGE     OFFSET  LEN  NOTES')),
  ];
  for (const f of book.layout) {
    const indent = f.level === 1 ? '' : f.level <= 5 ? ' ' : '  ';
    const lvl = pad(`${indent}${String(f.level).padStart(2, '0')}`, 5);
    let note: Seg = n('');
    if (f.slack_before) note = h(`SYNC +${f.slack_before} SLACK @${f.offset - f.slack_before}`);
    else if (f.redefines) note = h(`REDEF ${f.redefines}`);
    else if (f.sync) note = d('SYNC ALIGNED');
    else if (isOverlay(f)) note = d('OVERLAY VIEW');
    const tone = f.redefines || f.slack_before ? h : n;
    rows.push(
      row(
        tone(` ${lvl}${pad(f.name, 18)}${pad(f.pic ?? '', 11)}${pad(f.usage ?? 'GROUP', 9)}`),
        n(`${lpad(f.offset, 6)} ${lpad(f.size, 4)}  `),
        note,
      ),
    );
  }
  const elementary = book.layout.filter((f) => f.pic && !isOverlay(f));
  const fieldSum = elementary.reduce((sum, f) => sum + f.size, 0);
  const slack = book.layout.reduce((sum, f) => sum + f.slack_before, 0);
  const firstSync = book.layout.find((f) => f.slack_before);
  rows.push(blank());
  rows.push(
    row(
      n(' SUM OF FIELD LENGTHS '),
      h(String(fieldSum)),
      n('   + SYNC SLACK '),
      h(String(slack)),
      n('   = COMPILER RECORD LENGTH '),
      h(String(book.record_size)),
    ),
  );
  if (firstSync) {
    rows.push(
      row(
        d(
          ` NAIVE SUMMED STRUCT READS ${firstSync.name} AT +${firstSync.offset - firstSync.slack_before}` +
          `, TRUE OFFSET +${firstSync.offset}`,
        ),
      ),
    );
  }
  return rows;
}

// ------------------------------------------------------------------------- PF2 HEX

function hexPage(): Row[] {
  const { bytes, chars, owners, fields } = book.sample;
  const packed = new Set(book.layout.filter((f) => f.usage === 'COMP-3').map((f) => f.name));
  const rows: Row[] = [
    row(d(' OFFSET  00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F   EBCDIC CP-037')),
  ];
  for (let base = 0; base < bytes.length; base += 16) {
    const segs: Seg[] = [n(` +${base.toString(16).toUpperCase().padStart(4, '0')}   `)];
    for (let i = base; i < base + 16; i += 1) {
      if (i >= bytes.length) {
        segs.push(n('   '));
        continue;
      }
      const owner = owners[i];
      const cell = bytes[i];
      segs.push(owner === 'SLACK' ? I(cell) : packed.has(owner) ? h(cell) : n(cell), n(' '));
    }
    segs.push(n('  '), d(chars.slice(base, base + 16).join('')));
    rows.push(row(...segs));
  }
  rows.push(
    row(d(' LEGEND  '), I('00'), d(' SYNC SLACK   '), h('9C'), d(' COMP-3 PACKED   '), n('F1'), d(' DISPLAY / BINARY')),
  );
  rows.push(row(d(' FIELD             OFF LEN  HEX                               VALUE')));
  for (const f of fields) {
    const tone = packed.has(f.name) ? h : f.overlay ? d : n;
    rows.push(
      row(
        tone(` ${pad(f.overlay ? `>${f.name}` : f.name, 17)}${lpad(f.offset, 4)}${lpad(f.size, 4)}  `),
        tone(pad(f.hex, 34)),
        n(f.value.trimEnd()),
      ),
    );
  }
  return rows;
}

// ------------------------------------------------------------------------- PF3 VECTORS

const ok = (pass: boolean): Seg => (pass ? h('PASS') : R(' FAIL '));

function nibbleSegs(v: Comp3Vector): Seg[] {
  return v.nibbles.flatMap((nib, i) => {
    const last = i === v.nibbles.length - 1;
    const padNibble = i === 0 && v.digits % 2 === 0;
    return [last ? I(nib) : padNibble ? h(nib) : n(nib), n(' ')];
  });
}

function vectorPage(): Row[] {
  const { A, B, C, D } = DATA.vectors;
  const rows: Row[] = [row(h(' GOLDEN TEST VECTORS  specs/PRD.md SECTION 8  (COMPUTED BY engine/)')), blank()];

  rows.push(
    row(n(` A  PIC ${pad(A.pic, 17)}${lpad(A.input, 12)} -> `), h(A.hex), n(`   LEN ${A.byte_length}  SIGN ${A.sign_nibble}`)),
  );
  rows.push(row(d('    NIBBLES '), ...nibbleSegs(A), d(`   DECODED ${A.decoded}  `), ok(A.decoded === A.input)));
  rows.push(blank());

  B.forEach((v, i) => {
    const sign = v.input.startsWith('-') ? v.input : `+${v.input}`;
    rows.push(
      row(
        n(i === 0 ? ` B  PIC ${pad(`${v.pic} ZONED`, 17)}` : ' '.repeat(25)),
        n(`${lpad(sign, 7)} -> `),
        h(v.hex),
        n(`  '${v.ascii}'  DECODED ${pad(v.decoded, 7)}`),
        ok(v.decoded === v.input),
      ),
    );
  });
  rows.push(blank());

  const tagged = (keys: string[], code: 'ascii' | 'ebcdic') =>
    keys.map((k) => `${k}(${C.first_bytes[k][code]})`).join(' ');
  rows.push(row(n(` C  BATCH KEYS ${C.input.join('  ')}`)));
  rows.push(row(d('    ASCII  SORT  '), r(tagged(C.ascii, 'ascii')), d('   <- CLOUD (WRONG)')));
  rows.push(row(d('    EBCDIC SORT  '), h(tagged(C.ebcdic, 'ebcdic')), d('   <- MAINFRAME  '), ok(C.ebcdic.join() === 'acc100,ACC100,100ACC')));
  rows.push(blank());

  D.forEach((v, i) => {
    const sign = v.input.startsWith('-') ? v.input : `+${v.input}`;
    rows.push(
      row(
        n(i === 0 ? ` D  PIC ${pad(v.pic, 17)}` : ' '.repeat(25)),
        n(`${lpad(sign, 7)} -> `),
        h(v.hex),
        d('  NIBBLES '),
        ...nibbleSegs(v),
        n(` LEN ${v.byte_length} `),
        ok(v.decoded === v.input && v.nibbles[0] === '0'),
      ),
    );
  });
  rows.push(blank());
  rows.push(row(d(' E  S0C7 INJECTION: SEE PF4.   '), I('X'), d(' = SIGN NIBBLE   '), h('0'), d(' = EVEN-DIGIT 0x0 PAD NIBBLE')));
  return rows;
}

// ------------------------------------------------------------------------- PF4 S0C7

function s0c7Page(): Row[] {
  const E = DATA.vectors.E;
  const bad = E.invalid_nibble_index ?? E.nibbles.length - 1;
  const lead = '  NIBBLES      ';
  const hard = SCENARIOS.hardened.report;
  const rows: Row[] = [
    row(R(' S0C7 '), r(` DATA EXCEPTION   TEST VECTOR E   PIC ${E.pic}`)),
    blank(),
    row(n('  INPUT DUMP   '), h(E.hex.match(/../g)?.join(' ') ?? E.hex), d('   UNINITIALISED EBCDIC SPACES MOVED TO PACKED')),
    row(
      n(lead),
      ...E.nibbles.flatMap((nib, i) => [i === bad ? R(nib) : n(nib), n(' ')]),
    ),
    row(n(' '.repeat(lead.length + bad * 2)), r(`^ ${(E.invalid_nibble_kind ?? 'sign').toUpperCase()} NIBBLE ${E.invalid_nibble ?? E.sign_nibble} INVALID: ONLY C / D / F ARE SIGNS`)),
    blank(),
    row(r(' CEE3207S The system detected a data exception (System Completion Code=0C7).')),
    row(r(' IEA995I SYMPTOM DUMP OUTPUT  SYSTEM COMPLETION CODE=0C7  REASON CODE=00000007')),
    row(d(` ENGINE: ${E.error ?? ''}`)),
    blank(),
    row(d('  HEX DUMP          PIC                RESULT')),
  ];
  for (const s of DATA.s0c7_samples) {
    rows.push(
      row(
        n(`  ${pad(s.hex, 18)}${pad(s.pic, 19)}`),
        s.s0c7 ? R(' ABEND S0C7 ') : h(' OK '),
        s.s0c7 ? r(` ${s.invalid_nibble_kind} nibble ${s.invalid_nibble} @${s.invalid_nibble_index}`) : n(`  VALUE ${s.value}`),
      ),
    );
  }
  rows.push(blank());
  if (hard) {
    rows.push(
      row(
        n('  BATTERY: '),
        h(`${fmt(hard.s0c7_injected_detected)} OF ${fmt(hard.battery)}`),
        n(' CORRUPTED DUMPS ABEND IN BOTH ENGINES, '),
        hard.abend_mismatches ? R(` ${hard.abend_mismatches} MISMATCH `) : h('0 MISMATCHES'),
      ),
    );
  }
  return rows;
}

// ------------------------------------------------------------------------- PF5 FUZZER

function bar(done: number, total: number, width: number): string {
  const filled = total ? Math.floor((done * width) / total) : 0;
  return '\u2588'.repeat(filled) + '\u2591'.repeat(width - filled);
}

function fuzzPage(run: RunState): Row[] {
  const s: Scenario = SCENARIOS[run.scenario];
  const t = telemetry(s);
  if (run.phase === 'idle') {
    return [
      row(h(' SHADOW FUZZER READY')),
      blank(),
      row(n(`  GOLDEN ENGINE  INTEGER / NIBBLE ARITHMETIC     RECORDS ${fmt(DATA.records)}`)),
      row(n(`  MODERN ENGINE  DECIMAL PREC=28 ROUND_DOWN      SEED    ${DATA.seed}`)),
      blank(),
      row(d('  ENTER  '), h('DEPLOY H'), d('  TO PROMOTE services/hardened_service.py')),
      row(d('  ENTER  '), h('DEPLOY V'), d('  TO PROMOTE services/vulnerable_service.py')),
      blank(),
      row(d('  EACH DEPLOY_LAMBDA CALL IS INTERCEPTED BY THE KIRO PreToolUse HOOK.')),
    ];
  }
  if (run.phase !== 'verdict') {
    const phaseLabel = { transpile: 'BEDROCK TRANSPILE', hook: 'PreToolUse HOOK FIRED', fuzz: 'FUZZING' }[run.phase];
    return [
      row(h(` ${phaseLabel}`), n(`   ${s.service}`)),
      blank(),
      row(n('  RECORDS  '), h(bar(run.records, t.records, 40)), n(` ${lpad(fmt(run.records), 6)} / ${fmt(t.records)}`)),
      row(n('  S0C7 BAT '), h(bar(run.battery, t.battery, 40)), n(` ${lpad(fmt(run.battery), 6)} / ${fmt(t.battery)}`)),
      blank(),
      row(d('  GOLDEN: cents = balance * rate // (12 * 10^4), truncated toward zero')),
      row(d('  MODERN: Decimal  Context(prec=28, rounding=ROUND_DOWN).quantize(0.01)')),
    ];
  }
  if (s.screen) return s.screen.slice(2, 2 + BODY_ROWS).map((line) => toneLine(line));
  // Captured veto transcript (the service file was never written).
  const rows: Row[] = [
    row(R(' VETO '), r(` PreToolUse ${s.hook.tool_name} ${s.hook.target}  EXIT ${s.hook.exit_code}`)),
  ];
  const violations = s.hook.stderr.filter((l) => l.includes('Float precision violation on '));
  for (const line of s.hook.stderr.filter((l) => l.startsWith('[FAIL]'))) {
    for (const part of wrap(line)) rows.push(row(r(` ${part}`)));
  }
  rows.push(row(r(` FLOAT PRECISION VIOLATIONS (${violations.length}):`)));
  for (const line of violations) rows.push(row(r(`   ${line.trim().replace('Float precision violation on ', '')}`)));
  for (const line of s.hook.stderr.filter((l) => l.startsWith('[VETO]'))) {
    for (const part of wrap(line)) rows.push(row(r(` ${part}`)));
  }
  rows.push(blank());
  rows.push(row(d(' BLOCKED SOURCE:')));
  for (const line of CAPTURED_VETO.source_excerpt) rows.push(row(d(`   ${line}`)));
  return rows;
}

function toneLine(line: string): Row {
  if (/VETOED|EXIT CODE 2|precision violation|^\s+(candidate )?drift |S0C7 disagreement|unexpected S0C7/.test(line))
    return row(r(line));
  if (/ZERO DRIFT|PARITY VERIFIED/.test(line)) return row(h(line));
  if (/PACKED DECIMAL/.test(line)) return row(d(line));
  return row(n(line));
}

// ------------------------------------------------------------------------- frame

export interface FrameInput {
  page: PageId;
  run: RunState;
  command: string;
  message: { text: string; error: boolean } | null;
  abend: boolean;
}

export function buildScreen({ page, run, command, message, abend }: FrameInput): Row[] {
  const meta = PAGES.find((p) => p.id === page)!;
  const body = {
    ast: astPage,
    hex: hexPage,
    vec: vectorPage,
    s0c7: s0c7Page,
    fuzz: () => fuzzPage(run),
  }[page]();
  const rows = fit(body);
  if (message) rows[BODY_ROWS - 1] = row(message.error ? R(` ${message.text} `) : h(` ${message.text}`));

  const title = ` MFGHOST  ${meta.title}`;
  const right = `${meta.key.replace('F', 'PF')}  3278-2 80x24 `;
  const legend: Seg[] = [];
  for (const p of PAGES) {
    const label = `${p.key.replace('F', 'PF')}=${p.label}`;
    legend.push(p.id === page ? I(label) : d(label), d('  '));
  }
  legend.push(d('PF9=PHOSPHOR'));

  const oia = abend
    ? row(R(' X SYSTEM '), r('  PROG 0C7   S0C7 DATA EXCEPTION   [z/OS V2.5]   LPAR: PROD01'))
    : row(d('SYSTEM READY   [z/OS V2.5]   SEC: RACF-L4   LPAR: PROD01   OIA: NUMA [CONNECTED]'));

  const cursorRoom = COLS - 'COMMAND ===> '.length - 1;
  return [
    row(h(title), n(' '.repeat(Math.max(1, COLS - title.length - right.length))), d(right)),
    row(d('='.repeat(COLS))),
    ...rows,
    row(h('COMMAND ===> '), h(command.slice(-cursorRoom)), { t: '\u2588', c: 'h', blink: true }),
    row(...legend),
    oia,
  ];
}
