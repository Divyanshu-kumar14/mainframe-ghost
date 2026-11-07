#!/usr/bin/env python3
"""Differential shadow fuzzer (the parity sentinel core).

Ground truth  : GnuCOBOL output of cobol/src/intaccr_batch.cbl and ebcsort.cbl,
                committed in cobol/fixtures/ (see engine/cobol_oracle.py).
Golden engine : integer + nibble arithmetic, independent hard-coded EBCDIC ranges.
Modern engine : decimal.Decimal (prec=28, ROUND_DOWN) + engine.comp3_packer / ebcdic_codec.
Candidate     : the service code an agent proposes to write. It is executed in a
                sandboxed child process (engine/candidate_runner.py) and its
                ``accrue_monthly_interest`` must match COBOL on every record.

For N seeded banking records the engines compute monthly interest, pack it as
COMP-3, overpunch the new balance as zoned decimal, and sort account keys in EBCDIC
order. Any byte or value difference is drift. A battery of corrupted COMP-3 dumps
checks that both engines agree on where S0C7 must fire.

Exit codes: 0 parity (0.00000% drift), 2 veto (drift, S0C7, float contamination,
candidate mismatch), 1 sentinel error. ``--verify-stdin`` reads a Kiro PreToolUse
payload. No float is created anywhere in this module.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
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
    candidate_records: int = 0
    candidate_source: str = ""
    candidate_errors: list[str] = field(default_factory=list)
    candidate_ledger_delta: Decimal = Decimal(0)   # net: sum(candidate - COBOL)
    candidate_misposted: Decimal = Decimal(0)      # gross: sum(|candidate - COBOL|)
    sandbox: str = ""
    oracle: str = ""
    oracle_mismatches: int = 0
    seed: int = DEFAULT_SEED
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
    def candidate_drift_pct(self) -> str:
        if self.candidate_records == 0:
            return "n/a"
        pct = (Decimal(self.candidate_drift) * 100 / Decimal(self.candidate_records)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN)
        return f"{pct}%"

    @property
    def passed(self) -> bool:
        return (self.drifted == 0 and self.s0c7_unexpected == 0 and not self.violations
                and not self.packed_dump_abends and not self.candidate_errors
                and self.candidate_drift == 0 and self.oracle_mismatches == 0)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (f"[{status}] drift={self.drift_pct} records={self.records} battery={self.battery} "
                f"drifted={self.drifted} sort_mismatches={self.sort_mismatches} "
                f"s0c7_unexpected={self.s0c7_unexpected} abend_mismatches={self.abend_mismatches} "
                f"s0c7_injected_detected={self.s0c7_injected_detected} "
                f"violations={len(self.violations)} oracle_mismatches={self.oracle_mismatches} "
                f"candidate_records={self.candidate_records} "
                f"candidate_drift={self.candidate_drift} "
                f"candidate_drift_pct={self.candidate_drift_pct} "
                f"candidate_ledger_delta={self.candidate_ledger_delta}")

    def as_dict(self) -> dict:
        return {
            "passed": self.passed, "drift_pct": self.drift_pct, "records": self.records,
            "battery": self.battery, "comparisons": self.comparisons, "drifted": self.drifted,
            "sort_mismatches": self.sort_mismatches, "s0c7_unexpected": self.s0c7_unexpected,
            "abend_mismatches": self.abend_mismatches,
            "s0c7_injected_detected": self.s0c7_injected_detected,
            "candidate_drift": self.candidate_drift,
            "candidate_records": self.candidate_records,
            "candidate_drift_pct": self.candidate_drift_pct,
            "candidate_ledger_delta": str(self.candidate_ledger_delta),
            "candidate_misposted": str(self.candidate_misposted),
            "candidate_source": self.candidate_source,
            "candidate_errors": self.candidate_errors,
            "sandbox": self.sandbox,
            "oracle": self.oracle,
            "oracle_mismatches": self.oracle_mismatches,
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
    report = ParityReport(seed=seed)
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
    check_oracle(report)
    return report


def check_oracle(report: ParityReport) -> None:
    """Cross-check both Python engines against the committed GnuCOBOL output."""
    from engine.cobol_oracle import OracleError, fixtures_present, load_oracle, verify_engines

    if not fixtures_present():
        report.oracle = "absent (golden engine is the reference)"
        return
    try:
        data = load_oracle()
    except OracleError as exc:
        report.oracle_mismatches += 1
        report.oracle = "tampered"
        _note(report, f"oracle: {exc}")
        return
    report.oracle = f"{data.manifest['compiler']} ({len(data.records)} records)"
    problems = verify_engines(data)
    report.oracle_mismatches += len(problems)
    for problem in problems:
        _note(report, f"oracle: {problem}")


def load_candidate(path: str):
    """Import a candidate in-process. Trusted code only (tests, export script);
    the hook, CLI and MCP server use :func:`execute_candidate` instead."""
    spec = importlib.util.spec_from_file_location("candidate_service", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, CANDIDATE_FUNCTION, None)
    if not callable(func):
        raise AttributeError(f"{path} defines no {CANDIDATE_FUNCTION}(balance, annual_rate)")
    return func


# ----------------------------------------------------------------------------- sandbox

RUNNER = Path(__file__).resolve().parent / "candidate_runner.py"
SANDBOX_TIMEOUT_S = 30
SANDBOX_CPU_S = 20
SANDBOX_MEMORY_BYTES = 1 << 30
SANDBOX_FILE_BYTES = 1 << 20
_NETNS_PREFIX = ["unshare", "--user", "--net", "--map-root-user"]
_netns_ok: bool | None = None


def netns_available() -> bool:
    """True when unprivileged user + network namespaces work on this kernel."""
    global _netns_ok
    if _netns_ok is None:
        _netns_ok = False
        if shutil.which("unshare"):
            try:
                probe = subprocess.run([*_NETNS_PREFIX, "true"], capture_output=True,
                                       timeout=5, check=False)
                _netns_ok = probe.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _netns_ok = False
    return _netns_ok


def _limit_child() -> None:  # runs in the child between fork and exec
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (SANDBOX_CPU_S, SANDBOX_CPU_S))
    resource.setrlimit(resource.RLIMIT_AS, (SANDBOX_MEMORY_BYTES, SANDBOX_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (SANDBOX_FILE_BYTES, SANDBOX_FILE_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.setsid()


@dataclass
class CandidateRun:
    loaded: bool = False
    missing: bool = False
    error: str | None = None
    results: list[list[str]] = field(default_factory=list)
    float_probe: str = "not run"
    sandbox: str = ""


def execute_candidate(source: str, cases: list[tuple[str, str]],
                      function: str = CANDIDATE_FUNCTION) -> CandidateRun:
    """Run untrusted candidate source in a separate, limited process.

    The child gets ``python -I -B``, a scrubbed environment (so no AWS or Kiro
    credentials), a throwaway working directory, rlimits on CPU, memory and file
    size, a wall-clock timeout and, when available, no network (``unshare --net``).
    """
    use_netns = netns_available()
    sandbox = ("netns+rlimits" if use_netns else "rlimits (no network namespace)") + \
        f", timeout {SANDBOX_TIMEOUT_S}s"
    with tempfile.TemporaryDirectory(prefix="mg-candidate-") as tmp:
        target = Path(tmp) / "candidate_service.py"
        target.write_text(source, encoding="utf-8")
        cmd = [sys.executable, "-I", "-B", str(RUNNER), str(target)]
        if use_netns:
            cmd = [*_NETNS_PREFIX, *cmd]
        request = json.dumps({"function": function, "cases": cases})
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": tmp}
        try:
            proc = subprocess.run(cmd, input=request, capture_output=True, text=True,
                                  cwd=tmp, env=env, timeout=SANDBOX_TIMEOUT_S,
                                  preexec_fn=_limit_child, check=False)
        except subprocess.TimeoutExpired:
            return CandidateRun(error=f"timed out after {SANDBOX_TIMEOUT_S}s", sandbox=sandbox)
        except OSError as exc:
            return CandidateRun(error=f"sandbox failed to start: {exc}", sandbox=sandbox)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        signals = {-9: "killed (CPU or memory limit)", -24: "killed (CPU limit)",
                   -25: "killed (file size limit)"}
        reason = signals.get(proc.returncode)
        if reason is None:
            tail = (proc.stderr or "").strip().splitlines()[-1:] or [f"exit {proc.returncode}"]
            reason = tail[0][:200]
        return CandidateRun(error=f"candidate process died: {reason}", sandbox=sandbox)
    return CandidateRun(loaded=bool(data.get("loaded")), missing=bool(data.get("missing")),
                        error=data.get("error"), results=data.get("results") or [],
                        float_probe=str(data.get("float_probe")), sandbox=sandbox)


_DEFINES = re.compile(rf"\b{CANDIDATE_FUNCTION}\b")


def mentions_candidate_function(source: str) -> bool:
    return bool(_DEFINES.search(source))


def reference_cases(records: int) -> tuple[list[tuple[str, str]], list[Decimal], str]:
    """Inputs and expected interest: GnuCOBOL fixtures when present, else golden engine."""
    from engine.cobol_oracle import OracleError, fixtures_present, load_oracle

    if fixtures_present():
        try:
            data = load_oracle()
            chosen = data.records[:records]
            return ([(str(r.balance), str(r.annual_rate)) for r in chosen],
                    [r.interest for r in chosen], data.manifest["compiler"])
        except OracleError:
            pass
    corpus = generate_records(records)
    cases = [(str(Decimal(r.balance_cents).scaleb(-2)), str(Decimal(r.rate_units).scaleb(-4)))
             for r in corpus]
    expected = [Decimal(golden_interest_cents(r.balance_cents, r.rate_units)).scaleb(-2)
                for r in corpus]
    return cases, expected, "golden engine"


def check_candidate(source: str, report: ParityReport, label: str,
                    records: int = DEFAULT_RECORDS) -> None:
    """Execute a proposed service in the sandbox and diff it against COBOL output."""
    cases, expected, oracle = reference_cases(records)
    run = execute_candidate(source, cases)
    report.candidate_source = label
    report.sandbox = run.sandbox
    if run.error:
        report.candidate_errors.append(f"{label}: {run.error}")
        return
    if run.missing:  # mentions the name but does not expose it: nothing to execute
        _note(report, f"{label}: no callable {CANDIDATE_FUNCTION}; static scan only")
        return
    if len(run.results) != len(cases):
        report.candidate_errors.append(f"{label}: returned {len(run.results)} results for "
                                       f"{len(cases)} records")
        return
    report.candidate_records = len(cases)
    report.comparisons += len(cases)
    for (balance, rate), want, (kind, text) in zip(cases, expected, run.results):
        ok = False
        if kind == "Decimal":
            got = Decimal(text)
            ok = got == want and got.as_tuple().exponent == -2
            delta = FIN_CTX.subtract(got, want)
            report.candidate_ledger_delta = FIN_CTX.add(report.candidate_ledger_delta, delta)
            report.candidate_misposted = FIN_CTX.add(report.candidate_misposted,
                                                     delta.copy_abs())
        if not ok:
            report.candidate_drift += 1
            report.drifted += 1
            shown = text if kind == "Decimal" else f"{kind} {text}"
            _note(report, f"candidate drift balance={balance} rate={rate}: "
                          f"COBOL={want} candidate={shown}")
    if run.float_probe != "TypeError":
        report.candidate_errors.append(
            f"{label}: IEEE 754 input was {run.float_probe}; must raise TypeError")
    if report.candidate_drift:
        report.candidate_errors.append(
            f"{label}: {report.candidate_drift} of {len(cases)} records differ from {oracle}")


def proposed_source(payload: dict, root: Path | None = None) -> tuple[str | None, str]:
    """Full post-write source of the .py file a tool call targets (None if exempt/unknown)."""
    root = root or Path.cwd()
    params = payload.get("tool_input") or payload.get("parameters") or {}
    if not isinstance(params, dict):
        return None, ""
    path = next((str(params[k]) for k in _PATH_KEYS if isinstance(params.get(k), str)), "")
    if not path.endswith(".py"):
        return None, ""
    target = Path(path) if Path(path).is_absolute() else root / path
    try:
        rel = str(target.resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        rel = path
    if _is_exempt(rel):
        return None, rel
    tool = str(payload.get("tool_name") or payload.get("tool") or "")
    existing = ""
    try:
        if target.is_file() and target.stat().st_size <= MAX_SCAN_BYTES:
            existing = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        existing = ""
    text = next((params[k] for k in ("text", "content", "file_text", "fileText")
                 if isinstance(params.get(k), str)), None)
    new = next((params[k] for k in ("newStr", "new_str", "new_string")
                if isinstance(params.get(k), str)), None)
    old = next((params[k] for k in ("oldStr", "old_str", "old_string")
                if isinstance(params.get(k), str)), None)
    if new is not None and old is not None:  # str_replace
        return (existing.replace(old, new, 1) if old and old in existing else None), rel
    if text is not None:
        return (existing + ("" if not existing or existing.endswith("\n") else "\n") + text
                if "append" in tool else text), rel
    return (existing or None), rel  # deploy-style call: the file on disk


# ----------------------------------------------------------------------------- 3270 screen

SCREEN_COLUMNS = 80
SCREEN_ROWS = 24
_P31_GREEN = "\x1b[38;2;51;255;51m"    # primary phosphor  #33ff33
_P31_DIM = "\x1b[38;2;31;138;31m"      # muted phosphor    #1f8a1f
_ABEND_RED = "\x1b[38;2;255;51;51m"    # S0C7 abend red    #ff3333
_RESET = "\x1b[0m"


def render_3270(report: ParityReport, color: bool = False) -> str:
    """Render the report as an 80x24 IBM 3270 green-phosphor screen.

    Plain ASCII when ``color`` is false, so logs and the hook stay machine readable.
    """
    sample = encode_comp3(Decimal("-1234567.89"), 9, 2)
    hex_row = " ".join(f"{b:02X}" for b in sample)
    ok = report.passed
    rows: list[tuple[str, str]] = []  # (text, style) style: g=green d=dim r=red

    def add(text: str = "", style: str = "g") -> None:
        rows.append((text[:SCREEN_COLUMNS].ljust(SCREEN_COLUMNS), style))

    add("MAINFRAMEGHOST  PARITY SENTINEL  --  COBOL ORACLE + SHADOW FUZZER")
    add("=" * SCREEN_COLUMNS, "d")
    add(f"  ORACLE . . . .  {(report.oracle or 'not checked')[:40]:<40} RECORDS : {report.records:>7}")
    add(f"  GOLDEN ENGINE   INTEGER / NIBBLE ARITHMETIC      S0C7 BAT: {report.battery:>7}")
    add(f"  MODERN ENGINE   DECIMAL PREC=28 ROUND_DOWN       SEED    : {report.seed:>7}")
    add(f"  CANDIDATE . . . {(report.candidate_source or 'none')[:40]:<40} COMPARE : {report.comparisons:>7}")
    add(f"  PACKED DECIMAL  {hex_row} | PIC S9(7)V99 COMP-3 | -1234567.89", "d")
    add()
    if report.candidate_records:
        add(f"  CANDIDATE PARITY DRIFT . . . . . . . . . . : {report.candidate_drift_pct:>12}")
    else:
        add(f"  ENGINE PARITY DRIFT  . . . . . . . . . . . : {report.drift_pct:>12}")
    add(f"  ENGINES VS GNUCOBOL MISMATCHES . . . . . . : {report.oracle_mismatches:>12}")
    add(f"  CANDIDATE VS GNUCOBOL DRIFT  . . . . . . . : "
        f"{f'{report.candidate_drift}/{report.candidate_records}':>12}")
    add(f"  EBCDIC SORT MISMATCHES . . . . . . . . . . : {report.sort_mismatches:>12}")
    add(f"  S0C7 ON VALID DATA . . . . . . . . . . . . : {report.s0c7_unexpected:>12}")
    add(f"  S0C7 INJECTED / DETECTED . . . . . . . . . : {report.s0c7_injected_detected:>12}")
    add(f"  IEEE 754 VIOLATIONS  . . . . . . . . . . . : {len(report.violations):>12}")
    if ok:
        add("  *** ZERO DRIFT -- PARITY VERIFIED -- EXIT CODE 0 ***")
    else:
        add("  *** PARITY DRIFT / S0C7 ABEND -- DEPLOYMENT VETOED -- EXIT CODE 2 ***", "r")
        details = ([str(v) for v in report.violations] + report.candidate_errors
                   + report.packed_dump_abends + report.examples)
        for line in details[:3]:
            add(f"  {line}", "r")
    while len(rows) < SCREEN_ROWS - 2:
        add()
    add("-" * SCREEN_COLUMNS, "d")
    add("SYSTEM READY   [z/OS V2.5]   SEC: RACF-L4   LPAR: PROD01   OIA: NUMA [CONNECTED]", "d")
    rows = rows[:SCREEN_ROWS]
    if not color:
        return "\n".join(text for text, _ in rows)
    styles = {"g": _P31_GREEN, "d": _P31_DIM, "r": _ABEND_RED}
    return "\n".join(f"{styles[style]}{text}{_RESET}" for text, style in rows)


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
    source, rel = proposed_source(payload)
    if source and mentions_candidate_function(source):
        check_candidate(source, report, rel or "<payload>", records)
    return (0 if report.passed else 2), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MainframeGhost dual-engine parity fuzzer")
    parser.add_argument("--records", type=int, default=DEFAULT_RECORDS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--verify-stdin", action="store_true",
                        help="read a Kiro PreToolUse JSON payload on stdin")
    parser.add_argument("--candidate", help="python file defining accrue_monthly_interest; "
                        "statically scanned, then executed in the sandbox")
    parser.add_argument("--scan", action="append", default=[], metavar="FILE",
                        help="statically scan a Python file for float contamination")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--3270", dest="screen", action="store_true",
                        help="render an 80x24 IBM 3270 green-phosphor screen")
    parser.add_argument("--no-color", action="store_true",
                        help="plain 3270 screen without ANSI color")
    args = parser.parse_args(argv)
    try:
        if args.verify_stdin:
            code, report = verify_stdin(sys.stdin.read(), args.records, args.seed)
        else:
            report = run_shadow(args.records, args.seed)
            if args.candidate:
                source = Path(args.candidate).read_text(encoding="utf-8")
                report.violations.extend(scan_source(source, args.candidate))
                check_candidate(source, report, args.candidate, args.records)
            for name in args.scan:
                report.violations.extend(
                    scan_source(Path(name).read_text(encoding="utf-8"), name))
            code = 0 if report.passed else 2
        if args.json:
            print(json.dumps(report.as_dict(), indent=2))
        elif args.screen:
            use_color = sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ
            print(render_3270(report, color=use_color))
        else:
            print(report.summary())
            for violation in report.violations:
                print(f"  {violation}")
            for dump in report.packed_dump_abends:
                print(f"  S0C7 Abend (packed dump) {dump}")
            for error in report.candidate_errors:
                print(f"  Candidate veto: {error}")
            for example in report.examples:
                print(f"  {example}")
        return code
    except Exception:  # sentinel failure is exit 1, never a silent pass
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
