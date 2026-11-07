// 3270 panels. Every value shown comes from the engine: parity_vectors.json (exported)
// or a live cockpit API response.
import { CANDIDATES, DATA, ORACLE, candidateById, type Comp3Vector, type LayoutRow } from '../data/vectors';
import type { LabResult, RunState } from './run';
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

export type PageId = 'ast' | 'hex' | 'vec' | 's0c7' | 'fuzz' | 'lab';

export const PAGES: { id: PageId; key: string; label: string; title: string }[] = [
  { id: 'ast', key: 'F1', label: 'AST', title: 'COPYBOOK AST / BYTE LAYOUT' },
  { id: 'hex', key: 'F2', label: 'HEXDUMP', title: 'EBCDIC / COMP-3 HEX DUMP' },
  { id: 'vec', key: 'F3', label: 'VECTORS', title: 'GOLDEN TEST VECTORS A-D' },
  { id: 's0c7', key: 'F4', label: 'S0C7', title: 'S0C7 DATA EXCEPTION MONITOR' },
  { id: 'fuzz', key: 'F5', label: 'SENTINEL', title: 'PreToolUse PARITY SENTINEL' },
  { id: 'lab', key: 'F6', label: 'LAB', title: 'LIVE ENGINE LAB' },
];

export interface LayoutView {
  name: string;
  recordSize: number;
  layout: LayoutRow[];
  custom: boolean;
}

export const DEFAULT_LAYOUT: LayoutView = {
  name: DATA.copybook.name,
  recordSize: DATA.copybook.record_size,
  layout: DATA.copybook.layout,
  custom: false,
};

const fmt = (value: number) => value.toLocaleString('en-US');

// ------------------------------------------------------------------------- PF1 AST

function astPage(view: LayoutView): Row[] {
  const book = view.layout;
  const isOverlay = (f: LayoutRow) => book.some((g) => g.redefines && f.path.startsWith(`${g.path}.`));
  const root = book[0];
  const rows: Row[] = [
    row(
      h(` ${view.name}   01 ${root?.name ?? '?'}   RECORD LENGTH ${view.recordSize} BYTES`),
      view.custom ? d('   (PARSED LIVE)') : n(''),
    ),
    row(d(' LVL  NAME              PIC        USAGE     OFFSET  LEN  NOTES')),
  ];
  const listed = book.slice(0, BODY_ROWS - 5);
  for (const f of listed) {
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
  if (book.length > listed.length) rows.push(row(d(` ... ${book.length - listed.length} MORE FIELDS`)));
  const elementary = book.filter((f) => f.pic && !f.redefines && !isOverlay(f) && f.level !== 1);
  const fieldSum = elementary.reduce((sum, f) => sum + f.size, 0);
  const slack = book.reduce((sum, f) => sum + f.slack_before, 0);
  const firstSync = book.find((f) => f.slack_before);
  rows.push(blank());
  rows.push(
    row(
      n(' SUM OF FIELD LENGTHS '),
      h(String(fieldSum)),
      n('   + SYNC SLACK '),
      h(String(slack)),
      n('   = COMPILER RECORD LENGTH '),
      h(String(view.recordSize)),
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
  const book = DATA.copybook;
  const { bytes, chars, owners, fields } = book.sample;
  const packed = new Set(book.layout.filter((f) => f.usage === 'COMP-3').map((f) => f.name));
  const rows: Row[] = [
    row(d(` ${book.name} SAMPLE RECORD   OFFSET 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F`)),
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

function nibbleSegs(nibs: string[], digits: number): Seg[] {
  return nibs.flatMap((nib, i) => {
    const last = i === nibs.length - 1;
    const padNibble = i === 0 && digits % 2 === 0;
    return [last ? I(nib) : padNibble ? h(nib) : n(nib), n(' ')];
  });
}

function vectorPage(): Row[] {
  const { A, B, C, D } = DATA.vectors;
  const rows: Row[] = [row(h(' GOLDEN TEST VECTORS  specs/PRD.md SECTION 8  (COMPUTED BY engine/)')), blank()];
  const vec = (v: Comp3Vector) => nibbleSegs(v.nibbles, v.digits);

  rows.push(
    row(n(` A  PIC ${pad(A.pic, 17)}${lpad(A.input, 12)} -> `), h(A.hex), n(`   LEN ${A.byte_length}  SIGN ${A.sign_nibble}`)),
  );
  rows.push(row(d('    NIBBLES '), ...vec(A), d(`   DECODED ${A.decoded}  `), ok(A.decoded === A.input)));
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
        ...vec(v),
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
  const hard = candidateById('hardened')?.report;
  const rows: Row[] = [
    row(R(' S0C7 '), r(` DATA EXCEPTION   TEST VECTOR E   PIC ${E.pic}`)),
    blank(),
    row(n('  INPUT DUMP   '), h(E.hex.match(/../g)?.join(' ') ?? E.hex), d('   UNINITIALISED EBCDIC SPACES MOVED TO PACKED')),
    row(n(lead), ...E.nibbles.flatMap((nib, i) => [i === bad ? R(nib) : n(nib), n(' ')])),
    row(
      n(' '.repeat(lead.length + bad * 2)),
      r(`^ ${(E.invalid_nibble_kind ?? 'sign').toUpperCase()} NIBBLE ${E.invalid_nibble ?? E.sign_nibble} INVALID: ONLY C / D / F ARE SIGNS`),
    ),
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

// ------------------------------------------------------------------------- PF5 SENTINEL

function bar(done: number, width: number): string {
  const filled = Math.floor(Math.min(1, Math.max(0, done)) * width);
  return '\u2588'.repeat(filled) + '\u2591'.repeat(width - filled);
}

const DEPLOY_KEYS: Record<string, string> = { hardened: 'H', float: 'V', floor: 'FLOOR', halfup: 'U' };

function sentinelIdle(): Row[] {
  const rows: Row[] = [
    row(h(' SENTINEL ARMED'), d('   PreToolUse -> engine/shadow_fuzzer.py --verify-stdin')),
    blank(),
    row(n('  ORACLE   '), h(ORACLE.compiler), n(`  ${fmt(ORACLE.records)} RECS  ${ORACLE.program.replace('cobol/src/', '')}`)),
    ...ORACLE.procedure.slice(0, 2).map((line) => row(d(`           ${line}`))),
    row(n('  SANDBOX  '), d('python -I -B, empty env, rlimits CPU/MEM/FSIZE, unshare --net')),
    blank(),
    row(d('  KEY       BALANCE         RATE    COBOL WS-INTEREST COMP-3    VALUE')),
  ];
  for (const s of ORACLE.sample.slice(0, 4)) {
    rows.push(row(n(`  ${pad(s.key, 9)}${lpad(s.balance, 15)}  ${pad(s.rate, 7)} `), h(pad(s.interest_hex, 26)), n(lpad(s.interest, 12))));
  }
  rows.push(blank());
  for (const c of CANDIDATES.slice(0, 5)) {
    const key = DEPLOY_KEYS[c.id];
    rows.push(row(d('  ENTER '), h(pad(key ? `DEPLOY ${key}` : 'PANEL', 14)), n(pad(c.file, 44)), d(`EXIT ${c.hook.exit_code}`)));
  }
  return rows;
}

function sentinelPage(run: RunState): Row[] {
  if (run.phase === 'idle') return sentinelIdle();
  if (run.phase !== 'verdict' || !run.verdict) {
    const scanDone = run.phase === 'exec' ? 1 : 0.5;
    return [
      row(h(run.phase === 'scan' ? ' PreToolUse HOOK FIRED' : ' SANDBOXED EXECUTION'), n(`   ${run.label}`)),
      blank(),
      row(n('  1 STATIC IEEE 754 SCAN     '), h(bar(scanDone, 36))),
      row(n('  2 RUN CANDIDATE vs COBOL   '), h(bar(run.progress, 36)), n(` ${lpad(fmt(Math.floor(run.progress * ORACLE.records)), 6)}`)),
      blank(),
      row(d('  COBOL : COMPUTE WS-INTEREST = (ACCT-BALANCE * ACCT-ANNUAL-RATE) / 12')),
      row(d('          no ROUNDED phrase, so the quotient truncates toward zero')),
      row(d(`  CHILD : python -I -B candidate_runner.py, ${ORACLE.records.toLocaleString('en-US')} cases + float probe`)),
      blank(),
      run.error ? row(R(' ERROR '), r(` ${run.error}`)) : blank(),
    ];
  }
  return run.verdict.screen.slice(2, 2 + BODY_ROWS).map((line) => toneLine(line));
}

function toneLine(line: string): Row {
  if (/VETOED|EXIT CODE 2|precision violation|candidate drift|differ from|IEEE 754 input|died|timed out|Error|S0C7 disagreement|unexpected S0C7|oracle:/.test(line))
    return row(r(line));
  if (/ZERO DRIFT|PARITY VERIFIED/.test(line)) return row(h(line));
  if (/PACKED DECIMAL/.test(line)) return row(d(line));
  return row(n(line));
}

// ------------------------------------------------------------------------- PF6 LAB

function labHelp(): Row[] {
  return [
    row(h(' LIVE ENGINE LAB'), d('   EVERY RESULT IS COMPUTED BY engine/ VIA cockpit/server.py')),
    blank(),
    row(n('  UNPACK <hex> <pic>     '), d('UNPACK 40404040 S9(5)V99      UNPACK 123456789D S9(7)V99')),
    row(n('  PACK <value> <pic>     '), d('PACK -1234567.89 S9(7)V99     PACK 123456 S9(6)')),
    row(n('  ZONED <text> <pic>     '), d('ZONED 1234N S9(5)             ZONED 1234{ S9(3)V99')),
    row(n('  SORT <key> <key> ...   '), d('SORT 100ACC ACC100 acc100')),
    blank(),
    row(d('  COPYBOOKS: PASTE ONE IN THE SENTINEL PANEL (COPYBOOK TAB), RESULT ON PF1.')),
    row(d('  CANDIDATES: EDIT THE SOURCE IN THE SENTINEL PANEL AND RUN THE HOOK.')),
  ];
}

function labPage(lab: LabResult | null): Row[] {
  if (!lab) return labHelp();
  if (lab.kind === 'busy') return [row(h(` ${lab.command}`)), blank(), row(d('  CALLING ENGINE...'))];
  if (lab.kind === 'error') {
    return [row(h(` ${lab.command}`)), blank(), ...wrap(lab.error, COLS - 4).map((l) => row(r(`  ${l}`))), blank(), ...labHelp().slice(2)];
  }
  if (lab.kind === 'comp3') {
    const v = lab.data;
    const bad = v.invalid_nibble_index;
    const rows: Row[] = [
      row(h(` ${lab.title}`), n(`   PIC ${v.pic}`)),
      blank(),
      row(n('  BYTES    '), h(v.hex.match(/../g)?.join(' ') ?? v.hex), n(`   LENGTH ${v.byte_length}`)),
      row(n('  NIBBLES  '), ...v.nibbles.flatMap((nib, i) => [i === bad ? R(nib) : i === v.nibbles.length - 1 ? I(nib) : n(nib), n(' ')])),
      row(n('  SIGN     '), n(`${v.sign_nibble ?? '?'} ${(v.sign_class ?? '').toUpperCase()}`)),
      blank(),
    ];
    if (v.valid) rows.push(row(n('  VALUE    '), h(v.value ?? '')), blank(), row(h('  VALID PACKED DECIMAL')));
    else if (v.s0c7) {
      rows.push(row(R(' ABEND S0C7 '), r(` ${v.error ?? ''}`)));
      rows.push(row(r(' CEE3207S The system detected a data exception (System Completion Code=0C7).')));
    } else rows.push(row(R(' LAYOUT ERROR '), r(` ${v.error ?? ''}`)));
    return rows;
  }
  if (lab.kind === 'zoned') {
    const z = lab.data;
    return [
      row(h(` ZONED DECIMAL  '${z.text}'`), n(`   PIC ${z.pic}`)),
      blank(),
      row(n('  EBCDIC   '), h(z.ebcdic_hex ?? 'n/a')),
      z.valid ? row(n('  VALUE    '), h(z.value ?? '')) : row(R(' ABEND S0C7 '), r(` ${z.error ?? ''}`)),
      blank(),
      row(d('  OVERPUNCH  { A-I = +0..+9    } J-R = -0..-9   (LAST BYTE ZONE C / D)')),
    ];
  }
  const s = lab.data;
  const tag = (keys: string[], code: 'ascii' | 'ebcdic') => keys.map((k) => `${k}(${s.first_bytes[k][code]})`);
  return [
    row(h(' COLLATING SEQUENCE'), n(`   ${s.ascii.length} KEYS`)),
    blank(),
    row(d('  ASCII  ')),
    ...wrap(tag(s.ascii, 'ascii').join(' '), COLS - 6).map((l) => row(r(`    ${l}`))),
    row(d('  EBCDIC CP-037 (MAINFRAME SORT)')),
    ...wrap(tag(s.ebcdic, 'ebcdic').join(' '), COLS - 6).map((l) => row(h(`    ${l}`))),
    blank(),
    s.ascii.join() === s.ebcdic.join() ? row(h('  SAME ORDER')) : row(R(' ORDER DIFFERS '), r('  A NATIVE str SORT WOULD REORDER THE BATCH')),
  ];
}

// ------------------------------------------------------------------------- frame

export interface FrameInput {
  page: PageId;
  run: RunState;
  command: string;
  message: { text: string; error: boolean } | null;
  abend: boolean;
  layout: LayoutView;
  lab: LabResult | null;
}

export function buildScreen({ page, run, command, message, abend, layout, lab }: FrameInput): Row[] {
  const meta = PAGES.find((p) => p.id === page)!;
  const body = {
    ast: () => astPage(layout),
    hex: hexPage,
    vec: vectorPage,
    s0c7: s0c7Page,
    fuzz: () => sentinelPage(run),
    lab: () => labPage(lab),
  }[page]();
  const rows = fit(body);
  if (message) rows[BODY_ROWS - 1] = row(message.error ? R(` ${message.text} `) : h(` ${message.text}`));

  const title = ` MFGHOST  ${meta.title}`;
  const right = `${meta.key.replace('F', 'PF')}  3278-2 80x24 `;
  const legend: Seg[] = [];
  for (const p of PAGES) {
    const label = `${p.key.replace('F', 'PF')}=${p.label}`;
    legend.push(p.id === page ? I(label) : d(label), d(' '));
  }
  legend.push(d('PF9=PHOS'));

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
