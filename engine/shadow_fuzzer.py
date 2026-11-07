#!/usr/bin/env python3
"""Dual-engine differential shadow fuzzer (the parity sentinel core).

Golden engine : integer + nibble arithmetic, independent hard-coded EBCDIC ranges.
Modern engine : decimal.Decimal (prec=28, ROUND_DOWN) + engine.comp3_packer / ebcdic_codec.

For N synthetic banking records both engines compute monthly interest, pack it as
COMP-3, overpunch the new balance as zoned decimal, and sort account keys in EBCDIC
order. Any byte or value difference is drift. A battery of corrupted COMP-3 dumps
checks that both engines agree on where S0C7 must fire.

Exit codes: 0 parity (0.00000% drift), 2 veto (drift, S0C7, float contamination),
1 sentinel error. Pass records as ``--verify-stdin`` to read a Kiro PreToolUse
payload. No float is created anywhere in this module.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import random
import sys
import tokenize
import traceback
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Context, Decimal
from pathlib import Path

if __package__ in (None, ""):  # executed as a script by the hook
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.comp3_packer import S0C7Abend, decode_comp3, encode_comp3  # noqa: E402
from engine.ebcdic_codec import decode_zoned, ebcdic_sorted, encode_zoned  # noqa: E402

DEFAULT_RECORDS = 10_000
DEFAULT_SEED = 1959
BATTERY_SIZE = 500

FIN_CTX = Context(prec=28, rounding=ROUND_DOWN)
CENT = Decimal("0.01")

INTEREST_DIGITS = 11   # PIC S9(9)V99 COMP-3  (6 bytes)
BALANCE_DIGITS = 11    # PIC S9(9)V99 DISPLAY (11 bytes, overpunched)
RATE_SCALE = 4         # annual rate PIC 9V9(4), held as integer units
MAX_BALANCE_CENTS = 50_000_000_000

CANDIDATE_FUNCTION = "accrue_monthly_interest"


# ----------------------------------------------------------------------------- records

@dataclass(frozen=True)
class BankRecord:
    account_key: str
    balance_cents: int
    rate_units: int  # annual rate * 10**RATE_SCALE


_KEY_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def generate_records(count: int, seed: int = DEFAULT_SEED) -> list[BankRecord]:
    """Deterministic integer-only corpus: edge cases first, then random."""
    rng = random.Random(seed)
    edges = [
        (0, 0), (1, 1), (-1, 1), (99, 1), (-99, 1), (11, 5000), (-11, 5000),
        (14285714, 1200), (MAX_BALANCE_CENTS, 99999), (-MAX_BALANCE_CENTS, 99999),
        (100, 10000), (1, 99999), (-1, 99999), (12, 1), (-12, 1),
    ]
    records: list[BankRecord] = []
    for index in range(count):
        if index < len(edges):
            balance, rate = edges[index]
        else:
            balance = rng.randint(-MAX_BALANCE_CENTS, MAX_BALANCE_CENTS)
            if rng.randrange(100) < 50:
                balance //= rng.choice((10, 1000, 100000))
            rate = rng.randint(0, 99999) if rng.randrange(100) < 20 else rng.randint(0, 2500)
        key = "".join(rng.choice(_KEY_ALPHABET) for _ in range(rng.randint(3, 8)))
        records.append(BankRecord(key, balance, rate))
    return records


# ----------------------------------------------------------------------------- golden

_GOLDEN_RANGES = (
    ("abcdefghi", 0x81), ("jklmnopqr", 0x91), ("stuvwxyz", 0xA2),
    ("ABCDEFGHI", 0xC1), ("JKLMNOPQR", 0xD1), ("STUVWXYZ", 0xE2),
    ("0123456789", 0xF0),
)
_GOLDEN_RANK = {ch: base + i for chars, base in _GOLDEN_RANGES for i, ch in enumerate(chars)}


def golden_interest_cents(balance_cents: int, rate_units: int) -> int:
    """cents = balance_cents * rate / 12, truncated toward zero, integers only."""
    numerator = balance_cents * rate_units
    denominator = 12 * 10 ** RATE_SCALE
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def golden_pack(number: int, digits: int) -> bytes:
    """Build COMP-3 bytes nibble by nibble."""
    length = digits // 2 + 1
    text = str(abs(number)).rjust(2 * length - 1, "0")
    nibble_values = [int(c) for c in text] + [0xD if number < 0 else 0xC]
    return bytes((nibble_values[i] << 4) | nibble_values[i + 1]
                 for i in range(0, len(nibble_values), 2))


def golden_zoned(number: int, digits: int) -> bytes:
    """EBCDIC zoned bytes: F zone on all but the last, C/D zone on the last digit."""
    text = str(abs(number)).rjust(digits, "0")
    out = [0xF0 | int(c) for c in text[:-1]]
    out.append((0xD0 if number < 0 else 0xC0) | int(text[-1]))
    return bytes(out)


def golden_sorted(keys: list[str]) -> list[str]:
    return sorted(keys, key=lambda k: tuple(_GOLDEN_RANK[c] for c in k))


def golden_packed_valid(data: bytes) -> bool:
    nibbles = [n for byte in data for n in (byte >> 4, byte & 0x0F)]
    return all(n <= 9 for n in nibbles[:-1]) and nibbles[-1] in (0xC, 0xD, 0xF)


# ----------------------------------------------------------------------------- modern

def modern_interest(balance_cents: int, rate_units: int) -> Decimal:
    balance = Decimal(balance_cents).scaleb(-2, context=FIN_CTX)
    rate = Decimal(rate_units).scaleb(-RATE_SCALE, context=FIN_CTX)
    monthly = FIN_CTX.divide(FIN_CTX.multiply(balance, rate), Decimal(12))
    return monthly.quantize(CENT, rounding=ROUND_DOWN, context=FIN_CTX)


# ----------------------------------------------------------------------------- scanner

@dataclass(frozen=True)
class Violation:
    line: int
    kind: str
    detail: str
    path: str = ""

    def __str__(self) -> str:
        where = f"{self.path}:" if self.path else "line "
        return f"{self.kind} on {where}{self.line}: {self.detail}"


def _is_float_literal(text: str) -> bool:
    lowered = text.lower().replace("_", "")
    if lowered.startswith(("0x", "0o", "0b")) or lowered.endswith("j"):
        return False
    return "." in lowered or "e" in lowered


def scan_source(code: str, path: str = "") -> list[Violation]:
    """Token-level scan for IEEE 754 contamination: float(), round(), float literals.

    Token based (not ast) so partial edits such as a str_replace fragment still scan,
    and strings or comments never trigger false positives.
    """
    import textwrap

    tokens: list[tokenize.TokenInfo] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(textwrap.dedent(code)).readline):
            tokens.append(tok)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # keep tokens gathered so far
    found: list[Violation] = []
    for i, tok in enumerate(tokens):
        prev = tokens[i - 1] if i else None
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if tok.type == tokenize.NUMBER and _is_float_literal(tok.string):
            found.append(Violation(tok.start[0], "Float precision violation",
                                   f"float literal {tok.string}", path))
        elif tok.type == tokenize.NAME and tok.string in ("float", "round"):
            is_call = nxt is not None and nxt.string == "("
            is_attr = prev is not None and prev.string == "."
            is_def = prev is not None and prev.string in ("def", "class")
            if is_call and not is_attr and not is_def:
                found.append(Violation(tok.start[0], "Float precision violation",
                                       f"forbidden {tok.string}() call", path))
    return found


_EXEMPT_DIRS = {"tests", ".kiro", ".git", ".venv", "specs"}
_PATH_KEYS = ("path", "file_path", "filePath", "source_path", "target_file", "targetFile")
_CONTENT_KEYS = ("text", "newStr", "new_str", "new_string", "content", "file_text", "fileText")
MAX_SCAN_BYTES = 1_000_000


def _is_exempt(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name
    return (any(p in _EXEMPT_DIRS for p in parts[:-1])
            or name.startswith(("test_", "conftest")) or name.endswith("_test.py"))


def scan_payload(payload: dict, root: Path | None = None) -> list[Violation]:
    """Scan the Python content a tool call proposes to write or deploy."""
    root = root or Path.cwd()
    params = payload.get("tool_input") or payload.get("parameters") or {}
    if not isinstance(params, dict):
        return []
    path = next((str(params[k]) for k in _PATH_KEYS if isinstance(params.get(k), str)), "")
    if not path.endswith(".py"):
        return []
    try:
        rel = str(Path(path).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        rel = path
    if _is_exempt(rel):
        return []
    chunks = [params[k] for k in _CONTENT_KEYS if isinstance(params.get(k), str)]
    if not chunks:  # deploy-style call: scan the file on disk (read only, never executed)
        target = Path(path) if Path(path).is_absolute() else root / path
        try:
            if target.is_file() and target.stat().st_size <= MAX_SCAN_BYTES:
                chunks = [target.read_text(encoding="utf-8", errors="replace")]
        except OSError:
            chunks = []
    return [v for chunk in chunks for v in scan_source(chunk, rel)]


# ----------------------------------------------------------------------------- fuzzer

@dataclass
class ParityReport:
    records: int = 0
    battery: int = 0
    comparisons: int = 0
    drifted: int = 0
    sort_mismatches: int = 0
    s0c7_unexpected: int = 0
    abend_mismatches: int = 0
    s0c7_injected_detected: int = 0
    candidate_drift: int = 0
    violations: list[Violation] = field(default_factory=list)
    packed_dump_abends: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)

    @property
    def drift_pct(self) -> str:
        if self.comparisons == 0:
            return "0.00000%"
        pct = (Decimal(self.drifted) * 100 / Decimal(self.comparisons)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN)
        return f"{pct}%"

    @property
    def passed(self) -> bool:
        return (self.drifted == 0 and self.s0c7_unexpected == 0 and not self.violations
                and not self.packed_dump_abends)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (f"[{status}] drift={self.drift_pct} records={self.records} battery={self.battery} "
                f"drifted={self.drifted} sort_mismatches={self.sort_mismatches} "
                f"s0c7_unexpected={self.s0c7_unexpected} abend_mismatches={self.abend_mismatches} "
                f"s0c7_injected_detected={self.s0c7_injected_detected} "
                f"violations={len(self.violations)}")

    def as_dict(self) -> dict:
        return {
            "passed": self.passed, "drift_pct": self.drift_pct, "records": self.records,
            "battery": self.battery, "comparisons": self.comparisons, "drifted": self.drifted,
            "sort_mismatches": self.sort_mismatches, "s0c7_unexpected": self.s0c7_unexpected,
            "abend_mismatches": self.abend_mismatches,
            "s0c7_injected_detected": self.s0c7_injected_detected,
            "candidate_drift": self.candidate_drift,
            "violations": [str(v) for v in self.violations],
            "packed_dump_abends": self.packed_dump_abends,
            "examples": self.examples[:10],
        }


def _note(report: ParityReport, message: str) -> None:
    if len(report.examples) < 10:
        report.examples.append(message)


def compare_record(rec: BankRecord, report: ParityReport, candidate=None) -> bool:
    """Compare golden vs modern for one record. Returns True when identical."""
    g_cents = golden_interest_cents(rec.balance_cents, rec.rate_units)
    g_packed = golden_pack(g_cents, INTEREST_DIGITS)
    g_zoned = golden_zoned(rec.balance_cents + g_cents, BALANCE_DIGITS)

    interest = modern_interest(rec.balance_cents, rec.rate_units)
    new_balance = FIN_CTX.add(Decimal(rec.balance_cents).scaleb(-2, context=FIN_CTX), interest)
    try:
        m_packed = encode_comp3(interest, INTEREST_DIGITS, 2)
        m_zoned_text = encode_zoned(new_balance, BALANCE_DIGITS, 2)
        m_zoned = m_zoned_text.encode("cp037")
        round_trip_ok = (decode_comp3(m_packed, INTEREST_DIGITS, 2) == interest
                         and decode_zoned(m_zoned_text, 2) == new_balance)
    except S0C7Abend:
        report.s0c7_unexpected += 1
        _note(report, f"unexpected S0C7 on {rec}")
        return False
    same = (m_packed == g_packed and m_zoned == g_zoned and round_trip_ok
            and interest == Decimal(g_cents).scaleb(-2, context=FIN_CTX))
    if not same:
        _note(report, f"drift {rec}: golden={g_packed.hex()} modern={m_packed.hex()}")
    if candidate is not None:
        expected = Decimal(g_cents).scaleb(-2, context=FIN_CTX)
        try:
            got = candidate(Decimal(rec.balance_cents).scaleb(-2, context=FIN_CTX),
                            Decimal(rec.rate_units).scaleb(-RATE_SCALE, context=FIN_CTX))
        except Exception as exc:  # candidate is untrusted code
            got = exc
        if not isinstance(got, Decimal) or got != expected or got.as_tuple().exponent != -2:
            report.candidate_drift += 1
            _note(report, f"candidate drift {rec}: expected={expected} got={got!r}")
            same = False
    return same


def run_battery(rng: random.Random, size: int, report: ParityReport) -> None:
    """Corrupted COMP-3 dumps: golden and modern must agree on where S0C7 fires."""
    vectors: list[tuple[bytes, int, int]] = [(bytes.fromhex("40404040"), 7, 2)]  # Test Vector E
    layouts = [(5, 2), (6, 0), (7, 2), (9, 2), (11, 2)]
    while len(vectors) < size:
        digits, scale = rng.choice(layouts)
        value = rng.randint(-(10 ** digits) + 1, 10 ** digits - 1)
        data = bytearray(golden_pack(value, digits))
        roll = rng.randrange(100)
        if roll < 50:  # corrupt a digit nibble
            pos = rng.randrange(len(data))
            bad = rng.randint(0xA, 0xF)
            data[pos] = (bad << 4 | data[pos] & 0x0F) if rng.randrange(2) else (
                data[pos] & 0xF0 | bad)
        elif roll < 80:  # corrupt the sign nibble
            data[-1] = data[-1] & 0xF0 | rng.choice((0x0, 0x5, 0x9, 0xA, 0xB, 0xE))
        vectors.append((bytes(data), digits, scale))
    report.battery = len(vectors)
    for data, digits, scale in vectors:
        report.comparisons += 1
        expect_valid = golden_packed_valid(data)
        try:
            decode_comp3(data, digits, scale)
            modern_valid = True
        except S0C7Abend:
            modern_valid = False
        except ValueError:  # pad nibble / length checks are layout errors, not S0C7
            modern_valid = expect_valid
        if not modern_valid:
            report.s0c7_injected_detected += 1
        if modern_valid != expect_valid:
            report.abend_mismatches += 1
            report.drifted += 1
            if modern_valid is False:
                report.s0c7_unexpected += 1
            _note(report, f"S0C7 disagreement on {data.hex()}")


def check_packed_dumps(dumps: list, report: ParityReport) -> None:
    """Explicit COMP-3 dumps supplied in a payload; any S0C7 vetoes (Test Vector E)."""
    for item in dumps:
        if not isinstance(item, dict) or "hex" not in item:
            continue
        digits = item.get("digits")
        scale = item.get("scale", 0)
        try:
            decode_comp3(bytes.fromhex(str(item["hex"])), digits, int(scale))
        except S0C7Abend as exc:
            report.packed_dump_abends.append(f"{item['hex']}: {exc}")
        except (ValueError, TypeError) as exc:
            report.packed_dump_abends.append(f"{item['hex']}: malformed dump ({exc})")


def run_shadow(records: int = DEFAULT_RECORDS, seed: int = DEFAULT_SEED, candidate=None,
               battery: int = BATTERY_SIZE) -> ParityReport:
    report = ParityReport()
    corpus = generate_records(records, seed)
    report.records = len(corpus)
    for rec in corpus:
        report.comparisons += 1
        if not compare_record(rec, report, candidate):
            report.drifted += 1
    keys = [rec.account_key for rec in corpus]
    modern_order, golden_order = ebcdic_sorted(keys), golden_sorted(keys)
    mismatched = sum(1 for a, b in zip(modern_order, golden_order) if a != b)
    report.sort_mismatches = mismatched
    report.comparisons += len(keys)
    report.drifted += mismatched
    if mismatched:
        _note(report, f"EBCDIC sort order differs at {mismatched} positions")
    run_battery(random.Random(seed + 1), battery, report)
    return report


def load_candidate(path: str):
    """Import a candidate service module (explicit opt-in: executes the file)."""
    spec = importlib.util.spec_from_file_location("candidate_service", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, CANDIDATE_FUNCTION, None)
    if not callable(func):
        raise AttributeError(f"{path} defines no {CANDIDATE_FUNCTION}(balance, annual_rate)")
    return func


# ----------------------------------------------------------------------------- CLI

def verify_stdin(raw: str, records: int, seed: int) -> tuple[int, ParityReport]:
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    report = run_shadow(records, seed)
    report.violations.extend(scan_payload(payload))
    params = payload.get("tool_input") or payload.get("parameters") or {}
    if isinstance(params, dict) and isinstance(params.get("packed_fields"), list):
        check_packed_dumps(params["packed_fields"], report)
    return (0 if report.passed else 2), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MainframeGhost dual-engine parity fuzzer")
    parser.add_argument("--records", type=int, default=DEFAULT_RECORDS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--verify-stdin", action="store_true",
                        help="read a Kiro PreToolUse JSON payload on stdin")
    parser.add_argument("--candidate", help="python file defining accrue_monthly_interest "
                        "(executed; explicit opt-in)")
    parser.add_argument("--scan", action="append", default=[], metavar="FILE",
                        help="statically scan a Python file for float contamination")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    try:
        if args.verify_stdin:
            code, report = verify_stdin(sys.stdin.read(), args.records, args.seed)
        else:
            candidate = load_candidate(args.candidate) if args.candidate else None
            report = run_shadow(args.records, args.seed, candidate)
            for name in args.scan:
                report.violations.extend(
                    scan_source(Path(name).read_text(encoding="utf-8"), name))
            code = 0 if report.passed else 2
        if args.json:
            print(json.dumps(report.as_dict(), indent=2))
        else:
            print(report.summary())
            for violation in report.violations:
                print(f"  {violation}")
            for dump in report.packed_dump_abends:
                print(f"  S0C7 Abend (packed dump) {dump}")
            for example in report.examples:
                print(f"  {example}")
        return code
    except Exception:  # sentinel failure is exit 1, never a silent pass
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
