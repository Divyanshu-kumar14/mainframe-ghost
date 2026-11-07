# Requirements: MainframeGhost Parity Sentinel

Source of truth: `specs/PRD.md` (Sections 4, 5.1, 8). All requirements use EARS syntax.

## Glossary

- **Golden Record**: Byte-exact output of the original COBOL program as compiled and run by GnuCOBOL (`cobol/fixtures/`), plus Test Vectors A-E in PRD Section 8.
- **Candidate**: The Python service a tool call proposes to write.
- **Parity Drift**: Any difference between the Golden Record and an engine or candidate output, measured as `drifted / total` over the 10,000-record corpus.
- **S0C7**: Synthetic Decimal Data Exception raised on invalid packed/zoned nibbles.
- **Sentinel**: The PreToolUse hook `.kiro/hooks/bin/verify_modernization_parity.sh`.

## REQ-MF-001: Decimal Precision

**Statement:** *When* computing monetary calculations, the transpiled system *shall* utilize arbitrary-precision fixed-point decimal arithmetic with explicit scale matching the COBOL `PIC` declaration.

**Acceptance Criteria**
1. AC-001.1: The system *shall* use `decimal.Decimal` for every monetary value; `float` and `round()` *shall not* appear in financial code paths.
2. AC-001.2: *When* a COBOL `COMPUTE` omits `ROUNDED`, the system *shall* truncate toward zero using `ROUND_DOWN` quantized to the target `PIC` scale.
3. AC-001.3: *When* a `PIC S9(n)V9(m)` field is decoded, the resulting `Decimal` exponent *shall* equal `-m`.
4. AC-001.4: *If* a `float` is supplied at an ingestion boundary, *then* the system *shall* raise `TypeError` and *shall not* coerce it.
5. AC-001.5: *When* Zoned Decimal (`USAGE DISPLAY`) sign overpunch is decoded, the system *shall* map `{`,`A`-`I` to +0..+9 and `}`,`J`-`R` to -0..-9 (`+12345` <-> `"1234E"`, `-12345` <-> `"1234N"`).

## REQ-MF-002: Collating Parity

**Statement:** *When* sorting alphanumeric transaction batches, the transpiled system *shall* sort according to the IBM EBCDIC CP-037 collating sequence order.

**Acceptance Criteria**
1. AC-002.1: The system *shall* sort with key `str.encode("cp037")`, never native ASCII/UTF-8 string comparison.
2. AC-002.2: *When* given `["100ACC", "ACC100", "acc100"]`, the system *shall* return `["acc100", "ACC100", "100ACC"]` (Test Vector C).
3. AC-002.3: The resulting order *shall* satisfy `[a-z] < [A-Z] < [0-9]`.

## REQ-MF-003: COMP-3 Validation

**Statement:** *When* decoding `COMP-3` packed decimal fields, the system *shall* raise a synthetic S0C7 Data Exception *if* any nibble contains an invalid decimal digit (`0xA`-`0xF` in digit positions) or invalid sign code.

**Acceptance Criteria**
1. AC-003.1: The encoded byte length *shall* equal `L = floor(D/2) + 1` for `D` declared digits.
2. AC-003.2: *Where* `D` is even, the encoder *shall* prepend a `0x0` high nibble to byte 0 (`+123456` -> `01 23 45 6C`).
3. AC-003.3: The encoder *shall* emit sign `0xC` for positive signed, `0xD` for negative, and `0xF` for unsigned fields.
4. AC-003.4: The decoder *shall* accept sign nibbles `0xC`, `0xD`, `0xF` only; `0xA`, `0xB`, `0xE`, and `0x0`-`0x9` *shall* raise S0C7.
5. AC-003.5: *When* input is `40 40 40 40` for `PIC S9(5)V99 COMP-3`, the decoder *shall* raise S0C7 citing sign nibble `0x0` (Test Vector E).
6. AC-003.6: *When* `-1234567.89` is encoded as `PIC S9(7)V99 COMP-3`, the output *shall* be `12 34 56 78 9D` (Test Vector A).

## REQ-MF-004: Deployment Veto

**Statement:** *Where* modern cloud code introduces semantic drift against mainframe golden records, the Kiro PreToolUse hook *shall* terminate deployment execution with POSIX Exit Code 2.

**Acceptance Criteria**
1. AC-004.1: The Sentinel *shall* read the proposed tool payload as JSON on STDIN.
2. AC-004.2: The Sentinel *shall* run the shadow fuzzer over 10,000 synthetic banking records.
3. AC-004.3: *If* parity drift is greater than `0.00000%`, *then* the Sentinel *shall* exit with code 2 and write the diagnostic to STDERR.
4. AC-004.4: *If* a `float` literal, `float()` call, or `round()` call is detected in the proposed financial code, *then* the Sentinel *shall* exit with code 2.
5. AC-004.5: *If* any S0C7 abend is raised during the run, *then* the Sentinel *shall* exit with code 2.
6. AC-004.6: *When* drift is exactly `0.00000%` and no S0C7 occurs, the Sentinel *shall* exit with code 0.
7. AC-004.7: *If* the Sentinel itself fails (parse or runtime error), *then* it *shall* exit with code 1.

## REQ-MF-006: COBOL Ground Truth

**Statement:** *When* parity is measured, the system *shall* compare against bytes produced by a real COBOL compiler running the original program, not only against a second Python implementation.

**Acceptance Criteria**
1. AC-006.1: `cobol/src/intaccr_batch.cbl` *shall* `COPY INTACCR` and compute `WS-INTEREST` and `WS-NEW-BALANCE` exactly as the copybook declares them, with no `ROUNDED` phrase.
2. AC-006.2: GnuCOBOL output for the seeded 10,000-record corpus *shall* be committed in `cobol/fixtures/` with SHA-256 digests in `manifest.json`.
3. AC-006.3: *If* a fixture does not match its digest, *then* the Sentinel *shall* treat it as drift (exit 2).
4. AC-006.4: The golden and modern engines *shall* match the COBOL `COMP-3`, zoned and `SORT` output byte for byte.

## REQ-MF-007: Execute the Proposed Code

**Statement:** *When* a tool call proposes a `.py` file that exposes `accrue_monthly_interest`, the Sentinel *shall* execute the post-write file in a sandbox and compare its result for every oracle record.

**Acceptance Criteria**
1. AC-007.1: The Sentinel *shall* rebuild the post-write file for `fs_write`, `fs_append` and `str_replace` payloads.
2. AC-007.2: The candidate *shall* run in a child process started with `python -I -B`, an empty environment, CPU / memory / file-size limits, a 30 s timeout and, where supported, no network namespace.
3. AC-007.3: *If* any record differs from GnuCOBOL in value or scale, *then* the Sentinel *shall* exit with code 2 and list example records on STDERR.
4. AC-007.4: *If* the candidate accepts a `float` argument instead of raising `TypeError`, *then* the Sentinel *shall* exit with code 2.
5. AC-007.5: *If* the candidate crashes, hangs or exceeds a limit, *then* the Sentinel *shall* exit with code 2.

## REQ-MF-005 (Supporting): Memory Layout Fidelity

Derived from PRD Failure Modes 4 and 5.

1. *When* a `REDEFINES` clause is parsed, the system *shall* map redefining items to the same byte offset as the redefined item, backed by a single shared `bytearray`.
2. *When* `SYNCHRONIZED` is specified, the system *shall* insert slack bytes so the item offset is a multiple of 2 (S9-S9(4)), 4 (S9(5)-S9(18)) for binary items, and 8 for COMP-2 items.
3. *When* an update is made via a `REDEFINES` alias, the system *shall* reflect the change in every other alias of that storage.

## Traceability

| Requirement | Failure Mode | Test Vector | Module |
| :--- | :--- | :--- | :--- |
| REQ-MF-001 | 3, 6 | B | `engine/ebcdic_codec.py`, `engine/shadow_fuzzer.py` |
| REQ-MF-002 | 1 | C | `engine/ebcdic_codec.py` |
| REQ-MF-003 | 2 | A, D, E | `engine/comp3_packer.py` |
| REQ-MF-004 | all | E | `.kiro/hooks/`, `engine/shadow_fuzzer.py` |
| REQ-MF-005 | 4, 5 | n/a | `engine/copybook_parser.py` |
| REQ-MF-006 | 1, 2, 3 | A-D | `cobol/`, `engine/cobol_oracle.py` |
| REQ-MF-007 | 1 | n/a | `engine/shadow_fuzzer.py`, `engine/candidate_runner.py` |
