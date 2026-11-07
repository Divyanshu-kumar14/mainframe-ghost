# Design: MainframeGhost Parity Sentinel

Source of truth: `specs/PRD.md`. Implements REQ-MF-001..005.

## 1. System Topology

```
 COBOL copybook (.cbl) / EBCDIC dumps
              |
              v
 engine/copybook_parser.py  --> AST + byte layout (offsets, REDEFINES, slack)
              |
              +--> engine/comp3_packer.py   (packed decimal codec, S0C7)
              +--> engine/ebcdic_codec.py   (CP-037 key, zoned overpunch)
              |
              v
 engine/shadow_fuzzer.py  : golden engine  vs  modernized engine
              |             10,000 synthetic banking records
              v
 .kiro/hooks/bin/verify_modernization_parity.sh   (PreToolUse)
        exit 0 = proceed | exit 2 = VETO | exit 1 = sentinel error
              ^
              |
 .kiro/mcp/server.py (FastMCP): inspect_copybook_offsets,
                                decode_comp3_hex, run_shadow_parity_check
```

Two independent engines are compared:

- **Golden engine**: integer/nibble arithmetic only (digit strings, `int`), no `Decimal` reliance for byte layout. Models IBM truncation semantics.
- **Modern engine**: `decimal.Decimal` pipeline with `Context(prec=28, rounding=ROUND_DOWN)`.

Drift = records where outputs (bytes or value) differ. Pass requires `drift == 0`.

## 2. COMP-3 (Packed Decimal)

### 2.1 Length

```
L = floor(D / 2) + 1          (D = total digits, integer + fractional)
nibbles = 2 * L
```

| PIC | D | L | Leading pad nibble |
| :--- | :-: | :-: | :-: |
| `S9(7)V99 COMP-3` | 9 | 5 | none |
| `S9(6) COMP-3` | 6 | 4 | `0x0` |
| `S9(5)V99 COMP-3` | 7 | 4 | none |
| `S9(3) COMP-3` | 3 | 2 | none |

Rule: if `D` is even, `2L = D + 2`, so one pad nibble `0x0` precedes the digits. If `D` is odd, `2L = D + 1` and the digits plus sign fill the field exactly.

### 2.2 Sign nibbles

| Nibble | Meaning | Valid |
| :-: | :--- | :-: |
| `0xC` | positive (preferred) | yes |
| `0xD` | negative | yes |
| `0xF` | unsigned / positive | yes |
| `0xA`, `0xB`, `0xE` | alternate signs, rejected by this sentinel | no (S0C7) |
| `0x0`-`0x9` | digit values in the sign position | no (S0C7) |

Digit nibbles must be `0x0`-`0x9`; `0xA`-`0xF` in a digit position raises S0C7.

### 2.3 Encode

```
scaled  = int(abs(value).scaleb(scale))       # truncation toward zero
digits  = str(scaled).zfill(2*L - 1)          # 2L-1 digit nibbles
if len(str(scaled)) > D: overflow error
bytes   = fromhex(digits + sign_nibble)
```

### 2.4 Byte maps

Test Vector A, `PIC S9(7)V99 COMP-3`, value `-1234567.89`:

```
Byte:    [0]  [1]  [2]  [3]  [4]
Hex:      12   34   56   78   9D
Nibble:  1 2  3 4  5 6  7 8  9 D
         digits (9)            ^sign D
```

Test Vector D, `PIC S9(6) COMP-3`, value `+123456`:

```
Byte:    [0]  [1]  [2]  [3]
Hex:      01   23   45   6C
Nibble:  0 1  2 3  4 5  6 C
         ^pad                ^sign C
```

Test Vector E, `PIC S9(5)V99 COMP-3`, bytes `40 40 40 40`:

```
Byte:    [0]  [1]  [2]  [3]
Hex:      40   40   40   40
Nibble:  4 0  4 0  4 0  4 0
Digits at nibbles 0..6 -> 4,0,4,0,4,0,4 : the low nibbles of bytes 0-2 are 0x0 (valid digits)
Sign nibble (byte 3 low) = 0x0 -> INVALID -> S0C7
```

## 3. Zoned Decimal (USAGE DISPLAY)

Sign is overpunched in the zone (high) nibble of the last byte: `0xC` positive, `0xD` negative, `0xF` unsigned.

| Digit | Positive (0xC zone) | Negative (0xD zone) |
| :-: | :-: | :-: |
| 0 | `{` 0xC0 | `}` 0xD0 |
| 1 | `A` 0xC1 | `J` 0xD1 |
| 2 | `B` 0xC2 | `K` 0xD2 |
| 3 | `C` 0xC3 | `L` 0xD3 |
| 4 | `D` 0xC4 | `M` 0xD4 |
| 5 | `E` 0xC5 | `N` 0xD5 |
| 6 | `F` 0xC6 | `O` 0xD6 |
| 7 | `G` 0xC7 | `P` 0xD7 |
| 8 | `H` 0xC8 | `Q` 0xD8 |
| 9 | `I` 0xC9 | `R` 0xD9 |

Test Vector B, `PIC S9(5)`:

```
+12345 : F1 F2 F3 F4 C5  -> "1234E"
-12345 : F1 F2 F3 F4 D5  -> "1234N"
```

## 4. EBCDIC CP-037 Collating Table

Sort key: `s.encode("cp037")` (bytewise compare). Relevant ranges:

| Class | Chars | Hex range |
| :--- | :--- | :--- |
| lowercase | a-i / j-r / s-z | `81-89` / `91-99` / `A2-A9` |
| uppercase | A-I / J-R / S-Z | `C1-C9` / `D1-D9` / `E2-E9` |
| digits | 0-9 | `F0-F9` |

Total order for alphanumerics: `a-z < A-Z < 0-9`. Note the gaps (`8A-90`, `9A-A1`, `AA-C0`, `CA-D0`, `DA-E1`, `EA-EF`) are non-alphanumeric in CP-037, so contiguity of letters must not be assumed.

Test Vector C:

```
Input : ["100ACC", "ACC100", "acc100"]
First byte: 0xF1 (1), 0xC1 (A), 0x81 (a)
EBCDIC order: acc100 (0x81) < ACC100 (0xC1) < 100ACC (0xF1)
ASCII  order: 100ACC (0x31) < ACC100 (0x41) < acc100 (0x61)
```

## 5. Copybook Memory Model

### 5.1 PIC sizes

| Usage | Size (bytes) |
| :--- | :--- |
| `DISPLAY` | digits (+ none for sign, overpunched) / character count for `X` |
| `COMP-3` | `floor(D/2) + 1` |
| `COMP` / `BINARY` | D 1-4 -> 2; D 5-9 -> 4; D 10-18 -> 8 |

### 5.2 REDEFINES overlay

A redefining item starts at the offset of the item it redefines and consumes no new storage. Group size is the max of the redefined and redefining extents.

```
01 TRANSACTION-RECORD.
   05 TX-DATE        PIC 9(8).            offset 0, len 8
   05 TX-DATE-PARTS REDEFINES TX-DATE.    offset 0, len 8
      10 TX-YEAR     PIC 9(4).            offset 0, len 4
      10 TX-MONTH    PIC 9(2).            offset 4, len 2
      10 TX-DAY      PIC 9(2).            offset 6, len 2

Offset:   0   1   2   3   4   5   6   7
Memory: '2' '0' '2' '6' '1' '1' '0' '7'
TX-DATE   [===========================]
TX-YEAR   [===============]
TX-MONTH                  [=====]
TX-DAY                            [=====]
```

All aliases are views onto one `bytearray`; no per-field heap copies.

### 5.3 SYNCHRONIZED alignment

```
align  = 2 if binary D<=4 ; 4 if 5<=D<=18 ; 4 for COMP-1 ; 8 for COMP-2
slack  = (-offset) mod align
offset' = offset + slack
```

Slack bytes are `0x00`, are part of the enclosing group size, and are not addressable data. Record length is rounded per compiler rules only between fields; this design does not add trailing record padding.

```
01 ACCOUNT-RECORD.
   05 ACC-FLAG     PIC X(1).               offset 0, len 1
   05 ACC-BALANCE  PIC S9(9) COMP SYNC.    slack 3 -> offset 4, len 4

Offset: 0     1     2     3     4     5     6     7
Hex:    E7    00    00    00    00    01    E2    40
        FLAG  [---- slack ----] [--- ACC-BALANCE ---]
Record length = 8
```

## 6. Financial Arithmetic

- Context: `Context(prec=28, rounding=ROUND_DOWN)`.
- Final assignment: `value.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_DOWN)`.
- Banned: `float`, `round()`, `math.*` on money, `json.loads` without `parse_float=Decimal`.

## 7. Shadow Fuzzer

1. Seeded RNG (`random.Random(seed)`), default seed fixed for reproducibility, N = 10,000.
2. Each record: `(balance, annual_rate, field layout)` built from integers, so no floats are generated.
3. Golden engine: integer arithmetic with explicit truncation. Modern engine: `Decimal` + `ROUND_DOWN`.
4. Compare packed bytes, zoned strings, and values. Report `drift_pct = 100 * drifted / total` formatted to 5 decimals.
5. Inject negative control (known float-based engine) in tests to prove the comparator detects drift.
6. Exit codes: `0` pass, `2` drift/S0C7/float contamination, `1` internal error.

## 8. Hook Contract

- Config: `.kiro/hooks/parity_guard.json` (`PreToolUse`, command action, `timeout` as sibling of `action`).
- Script: `.kiro/hooks/bin/verify_modernization_parity.sh`, runs from the workspace root, reads JSON on STDIN.
- Semantics: exit 2 blocks the tool and returns STDERR to the agent. Other non-zero codes are non-blocking in Kiro, so drift must always map to exit 2.
- Bootstrap: while `engine/shadow_fuzzer.py` does not exist, the script warns and exits 0 so scaffolding is not deadlocked.

## 9. MCP Inspector

`.kiro/mcp/server.py` (FastMCP) exposes `inspect_copybook_offsets`, `decode_comp3_hex`, `run_shadow_parity_check`, delegating to the `engine/` modules.
