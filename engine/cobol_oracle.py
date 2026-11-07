#!/usr/bin/env python3
"""GnuCOBOL ground truth for the parity sentinel.

The Python golden engine in ``engine/shadow_fuzzer.py`` is a second implementation
written by the same author as the modern engine, so on its own it cannot prove
mainframe parity. This module runs the real COBOL program
(``cobol/src/intaccr_batch.cbl``, which COPYs ``copybooks/INTACCR.cpy``) and the
real COBOL SORT (``cobol/src/ebcsort.cbl``) under GnuCOBOL, on the same seeded
corpus, and stores the output bytes in ``cobol/fixtures/``.

The fixtures are committed, so tests, the PreToolUse hook and the cockpit compare
against COBOL output without needing Docker. Regenerate them with:

    python3 -m engine.cobol_oracle generate          # needs Docker or a local cobc
    python3 -m engine.cobol_oracle verify            # engines vs fixtures, exit 2 on drift

GnuCOBOL is not IBM Enterprise COBOL. For this program (one multiply, one divide,
truncation on store, COMP-3 and signed zoned output, an EBCDIC SORT) both
compilers must produce the same bytes; S0C7 behaviour is not modelled by GnuCOBOL
and stays covered by the Python engine only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):  # executed as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.comp3_packer import decode_comp3  # noqa: E402
from engine.ebcdic_codec import decode_zoned  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COBOL_SRC = ROOT / "cobol" / "src"
COPYBOOKS = ROOT / "copybooks"
FIXTURES = ROOT / "cobol" / "fixtures"
DOCKER_CONTEXT = ROOT / "cobol"
IMAGE = "mainframe-ghost/gnucobol:3.1.2"

KEY_LEN = 8
BALANCE_DIGITS = 11
RATE_DIGITS = 5
OUT_RECORD_LEN = 25          # X(8) + COMP-3 S9(9)V99 (6 bytes) + zoned S9(9)V99 (11 bytes)
INTEREST_SLICE = slice(8, 14)
BALANCE_SLICE = slice(14, 25)

COMPILE_AND_RUN = (
    "set -e; "
    "cobc --version | head -1 > COBC_VERSION; "
    "cobc -x -fsign=EBCDIC -I {copybooks} -o intaccr {src}/intaccr_batch.cbl; "
    "cobc -x -o ebcsort {src}/ebcsort.cbl; "
    "./intaccr > INTACCR.log; "
    "./ebcsort"
)


class OracleError(RuntimeError):
    """GnuCOBOL could not be run, or the fixtures are missing or tampered with."""


@dataclass(frozen=True)
class OracleRecord:
    account_key: str
    balance_cents: int
    rate_units: int
    interest_comp3: bytes        # raw COMP-3 bytes written by COBOL
    new_balance_zoned: str       # zoned text, EBCDIC sign overpunch (-fsign=EBCDIC)

    @property
    def interest(self) -> Decimal:
        return decode_comp3(self.interest_comp3, BALANCE_DIGITS, 2)

    @property
    def new_balance(self) -> Decimal:
        return decode_zoned(self.new_balance_zoned, 2)

    @property
    def balance(self) -> Decimal:
        return Decimal(self.balance_cents).scaleb(-2)

    @property
    def annual_rate(self) -> Decimal:
        return Decimal(self.rate_units).scaleb(-4)


@dataclass(frozen=True)
class OracleData:
    records: list[OracleRecord]
    sorted_keys: list[str]
    manifest: dict


# ----------------------------------------------------------------------------- corpus

def acctin_line(account_key: str, balance_cents: int, rate_units: int) -> str:
    """One ACCTIN line: X(8), S9(9)V99 SIGN LEADING SEPARATE, 9V9(4)."""
    if len(account_key) > KEY_LEN:
        raise ValueError(f"account key longer than {KEY_LEN}: {account_key!r}")
    sign = "-" if balance_cents < 0 else "+"
    return (account_key.ljust(KEY_LEN) + sign + str(abs(balance_cents)).rjust(BALANCE_DIGITS, "0")
            + str(rate_units).rjust(RATE_DIGITS, "0"))


def parse_acctin_line(line: str) -> tuple[str, int, int]:
    key = line[:KEY_LEN].rstrip(" ")
    sign = line[KEY_LEN]
    digits = line[KEY_LEN + 1:KEY_LEN + 1 + BALANCE_DIGITS]
    rate = line[KEY_LEN + 1 + BALANCE_DIGITS:KEY_LEN + 1 + BALANCE_DIGITS + RATE_DIGITS]
    if sign not in "+-" or not digits.isdigit() or not rate.isdigit():
        raise OracleError(f"malformed ACCTIN line: {line!r}")
    cents = int(digits)
    return key, -cents if sign == "-" else cents, int(rate)


def write_inputs(workdir: Path, records: int, seed: int) -> list:
    from engine.shadow_fuzzer import generate_records

    corpus = generate_records(records, seed)
    lines = [acctin_line(r.account_key, r.balance_cents, r.rate_units) for r in corpus]
    (workdir / "ACCTIN").write_text("\n".join(lines) + "\n", encoding="ascii")
    (workdir / "KEYSIN").write_text("\n".join(r.account_key for r in corpus) + "\n",
                                    encoding="ascii")
    return corpus


# ----------------------------------------------------------------------------- GnuCOBOL

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    probe = subprocess.run([docker, "info"], capture_output=True, text=True, check=False)
    return probe.returncode == 0


def run_gnucobol(workdir: Path) -> str:
    """Compile and run both programs in ``workdir``. Returns how they were run."""
    cobc = shutil.which("cobc")
    if cobc:
        script = COMPILE_AND_RUN.format(copybooks=COPYBOOKS, src=COBOL_SRC)
        subprocess.run(["sh", "-c", script], cwd=workdir, check=True, timeout=600)
        return f"local {cobc}"
    if not _docker_available():
        raise OracleError("GnuCOBOL not found: install cobc or start Docker")
    subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(DOCKER_CONTEXT)], check=True,
                   capture_output=True, timeout=1800)
    script = COMPILE_AND_RUN.format(copybooks="/copybooks", src="/src")
    subprocess.run(
        ["docker", "run", "--rm", "--network", "none",
         "-v", f"{workdir}:/work", "-v", f"{COBOL_SRC}:/src:ro",
         "-v", f"{COPYBOOKS}:/copybooks:ro", "-w", "/work", IMAGE, "sh", "-c", script],
        check=True, timeout=600)
    return f"docker {IMAGE} --network none"


def generate(records: int, seed: int, out_dir: Path = FIXTURES) -> dict:
    """Run GnuCOBOL on the seeded corpus and write the fixture set + manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mg-cobol-") as tmp:
        work = Path(tmp)
        work.chmod(0o777)  # the container user must be able to write here
        write_inputs(work, records, seed)
        runner = run_gnucobol(work)
        out = (work / "ACCTOUT").read_bytes()
        if len(out) != records * OUT_RECORD_LEN:
            raise OracleError(f"ACCTOUT has {len(out)} bytes, expected {records * OUT_RECORD_LEN}")
        for name in ("ACCTIN", "ACCTOUT", "KEYSOUT"):
            shutil.copyfile(work / name, out_dir / name)
        cobc_version = (work / "COBC_VERSION").read_text(encoding="utf-8").strip()
        log = (work / "INTACCR.log").read_text(encoding="utf-8").strip()
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "compiler": cobc_version,
        "runner": runner,
        "compile": ["cobc -x -fsign=EBCDIC -I copybooks cobol/src/intaccr_batch.cbl",
                    "cobc -x cobol/src/ebcsort.cbl"],
        "program_log": log,
        "seed": seed,
        "records": records,
        "record_length": OUT_RECORD_LEN,
        "sha256": {name: _sha256(out_dir / name) for name in ("ACCTIN", "ACCTOUT", "KEYSOUT")},
        "sources_sha256": {
            "cobol/src/intaccr_batch.cbl": _sha256(COBOL_SRC / "intaccr_batch.cbl"),
            "cobol/src/ebcsort.cbl": _sha256(COBOL_SRC / "ebcsort.cbl"),
            "copybooks/INTACCR.cpy": _sha256(COPYBOOKS / "INTACCR.cpy"),
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                           encoding="utf-8")
    return manifest


# ----------------------------------------------------------------------------- fixtures

_CACHE: dict[Path, OracleData] = {}


def fixtures_present(fixture_dir: Path = FIXTURES) -> bool:
    return all((fixture_dir / n).is_file() for n in ("manifest.json", "ACCTIN", "ACCTOUT",
                                                    "KEYSOUT"))


def load_oracle(fixture_dir: Path = FIXTURES) -> OracleData:
    """Load and integrity-check the committed GnuCOBOL output."""
    fixture_dir = fixture_dir.resolve()
    if fixture_dir in _CACHE:
        return _CACHE[fixture_dir]
    if not fixtures_present(fixture_dir):
        raise OracleError(f"GnuCOBOL fixtures missing in {fixture_dir}; run "
                          "python3 -m engine.cobol_oracle generate")
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["sha256"].items():
        if _sha256(fixture_dir / name) != digest:
            raise OracleError(f"fixture {name} does not match its manifest sha256")
    lines = (fixture_dir / "ACCTIN").read_text(encoding="ascii").splitlines()
    out = (fixture_dir / "ACCTOUT").read_bytes()
    if len(out) != len(lines) * OUT_RECORD_LEN:
        raise OracleError("ACCTOUT length does not match ACCTIN line count")
    records = []
    for index, line in enumerate(lines):
        key, cents, rate = parse_acctin_line(line)
        rec = out[index * OUT_RECORD_LEN:(index + 1) * OUT_RECORD_LEN]
        if rec[:KEY_LEN].decode("ascii").rstrip(" ") != key:
            raise OracleError(f"ACCTOUT record {index} key does not match ACCTIN")
        records.append(OracleRecord(key, cents, rate, bytes(rec[INTEREST_SLICE]),
                                    rec[BALANCE_SLICE].decode("ascii")))
    sorted_keys = (fixture_dir / "KEYSOUT").read_text(encoding="ascii").splitlines()
    data = OracleData(records, [k.rstrip(" ") for k in sorted_keys], manifest)
    _CACHE[fixture_dir] = data
    return data


# ----------------------------------------------------------------------------- verify

def verify_engines(data: OracleData) -> list[str]:
    """Compare the Python golden and modern engines byte-for-byte with COBOL output."""
    from engine.comp3_packer import encode_comp3
    from engine.ebcdic_codec import ebcdic_sorted, encode_zoned
    from engine.shadow_fuzzer import (
        golden_interest_cents,
        golden_pack,
        golden_sorted,
        golden_zoned,
        modern_interest,
    )

    problems: list[str] = []
    for rec in data.records:
        g_cents = golden_interest_cents(rec.balance_cents, rec.rate_units)
        if golden_pack(g_cents, BALANCE_DIGITS) != rec.interest_comp3:
            problems.append(f"golden COMP-3 differs from COBOL for {rec.account_key}")
        if golden_zoned(rec.balance_cents + g_cents, BALANCE_DIGITS) != \
                rec.new_balance_zoned.encode("cp037"):
            problems.append(f"golden zoned differs from COBOL for {rec.account_key}")
        interest = modern_interest(rec.balance_cents, rec.rate_units)
        if encode_comp3(interest, BALANCE_DIGITS, 2) != rec.interest_comp3:
            problems.append(f"modern COMP-3 differs from COBOL for {rec.account_key}")
        if encode_zoned(rec.balance + interest, BALANCE_DIGITS, 2) != rec.new_balance_zoned:
            problems.append(f"modern zoned differs from COBOL for {rec.account_key}")
        if len(problems) >= 10:
            break
    keys = [rec.account_key for rec in data.records]
    if ebcdic_sorted(keys) != data.sorted_keys:
        problems.append("modern EBCDIC sort differs from COBOL SORT")
    if golden_sorted(keys) != data.sorted_keys:
        problems.append("golden EBCDIC sort differs from COBOL SORT")
    return problems


def main(argv: list[str] | None = None) -> int:
    from engine.shadow_fuzzer import DEFAULT_RECORDS, DEFAULT_SEED

    parser = argparse.ArgumentParser(description="GnuCOBOL ground-truth oracle")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="run GnuCOBOL and rewrite cobol/fixtures/")
    gen.add_argument("--records", type=int, default=DEFAULT_RECORDS)
    gen.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sub.add_parser("verify", help="compare the Python engines with the fixtures")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate(args.records, args.seed)
            print(f"[OK] {manifest['compiler']} via {manifest['runner']}: "
                  f"{manifest['records']} records -> {FIXTURES.relative_to(ROOT)}")
        data = load_oracle()
        problems = verify_engines(data)
    except (OracleError, subprocess.CalledProcessError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"[DRIFT] {problem}", file=sys.stderr)
    if problems:
        return 2
    print(f"[PASS] golden + modern engines match {data.manifest['compiler']} byte-for-byte "
          f"on {len(data.records)} records and the EBCDIC SORT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
