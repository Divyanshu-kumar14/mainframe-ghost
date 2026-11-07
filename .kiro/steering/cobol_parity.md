---
inclusion: always
---

# COBOL Parity Rules (Non-Negotiable)

These rules govern all financial and mainframe-compat code in this repository. Spec: `.kiro/specs/mainframe_parity/`.

## Arithmetic

- ALWAYS use `decimal.Decimal` for monetary and numeric COBOL fields. Construct from `str` or `int`, never from `float`.
- NEVER use IEEE 754 floating point (`float`, float literals such as `0.1`, `float()`, `math.*` on money, `numpy` float dtypes) in financial logic.
- ALWAYS use an explicit context: `decimal.Context(prec=28, rounding=ROUND_DOWN)`.
- NEVER use the built-in `round()`. Use `Decimal.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_DOWN)`. COBOL without `ROUNDED` truncates toward zero.
- Use `ROUND_HALF_UP` only where the COBOL source says `ROUNDED`.
- ALWAYS parse JSON with `json.loads(..., parse_float=Decimal)`. Bind DB numeric parameters as `Decimal` or `str`.
- Reject `float` at boundaries with `TypeError`; never coerce silently.

## Byte-level fidelity

- COMP-3 length is `L = D // 2 + 1`. For even `D`, prepend a `0x0` high nibble.
- Sign nibbles: `0xC` positive, `0xD` negative, `0xF` unsigned. Anything else, or a digit nibble above `0x9`, raises S0C7. Never silently repair.
- Zoned Decimal: translate overpunch (`{`,`A`-`I` = +0..+9; `}`,`J`-`R` = -0..-9). Never `int()` a raw zoned string or strip the trailing letter.
- Map `REDEFINES` to views over one shared `bytearray`. Never create independent fields for redefined storage.
- For `SYNCHRONIZED` binary items, insert slack bytes: align 2 (D<=4), 4 (D 5-18), 8 (COMP-2).
- Never compute record size by summing field lengths when `SYNC` is present.

## Sorting

- ALWAYS sort alphanumeric batch keys with `key=lambda s: s.encode("cp037")`. Never rely on native `str` ordering.
- Expected: `["100ACC", "ACC100", "acc100"]` sorts to `["acc100", "ACC100", "100ACC"]`.

## Governance

- Before any deploy or financial-code write, the PreToolUse hook runs `engine/shadow_fuzzer.py`. Exit code 2 is a hard veto: fix the precision or layout issue, do not bypass or edit the hook to pass.
- Do not weaken golden test vectors (A-E in `.kiro/specs/mainframe_parity/requirements.md`) to make tests pass.
- Target parity drift is exactly `0.00000%` over 10,000 records.
