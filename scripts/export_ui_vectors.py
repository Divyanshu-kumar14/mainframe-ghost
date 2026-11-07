#!/usr/bin/env python3
"""Export real parity vectors from the engine into the 3270 cockpit UI.

Writes ``ui/src/data/parity_vectors.json``. Everything in it is computed here by
the actual engine, services and PreToolUse hook script, nothing is hand-typed:

* Golden Test Vectors A-E (specs/PRD.md Section 8)
* copybooks/INTACCR.cpy AST, byte layout and a populated 52-byte record dump
* a 10,000-record shadow-fuzzer run against services/hardened_service.py
* the hook's real exit code and output for a write of the hardened service
* the same for services/vulnerable_service.py, only if that file exists

Run from anywhere:  python3 scripts/export_ui_vectors.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.comp3_packer import describe_comp3, encode_comp3, nibbles  # noqa: E402
from engine.copybook_parser import Record, parse_copybook  # noqa: E402
from engine.ebcdic_codec import decode_zoned, ebcdic_sorted, encode_zoned  # noqa: E402
from engine.shadow_fuzzer import (  # noqa: E402
    DEFAULT_RECORDS,
    DEFAULT_SEED,
    load_candidate,
    render_3270,
    run_shadow,
    scan_source,
)
from services.hardened_service import accrue_monthly_interest, post_interest  # noqa: E402

OUT = ROOT / "ui" / "src" / "data" / "parity_vectors.json"
COPYBOOK = ROOT / "copybooks" / "INTACCR.cpy"
HOOK_CONFIG = ROOT / ".kiro" / "hooks" / "parity_guard.json"
HOOK_SCRIPT = ROOT / ".kiro" / "hooks" / "bin" / "verify_modernization_parity.sh"
HARDENED = ROOT / "services" / "hardened_service.py"
VULNERABLE = ROOT / "services" / "vulnerable_service.py"


def spaced(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def comp3_vector(label: str, value: str, digits: int, scale: int, pic: str) -> dict:
    data = encode_comp3(Decimal(value), digits, scale)
    info = describe_comp3(data.hex(), digits, scale)
    return {"label": label, "pic": pic, "input": value, "digits": digits, "scale": scale,
            "byte_length": len(data), "hex": spaced(data),
            "nibbles": [f"{n:X}" for n in nibbles(data)],
            "sign_nibble": info["sign_nibble"], "decoded": info["value"]}


def zoned_vector(value: str) -> dict:
    text = encode_zoned(Decimal(value), 5)
    return {"input": value, "pic": "S9(5)", "hex": spaced(text.encode("cp037")),
            "ascii": text, "decoded": str(decode_zoned(text))}


def run_hook(path: Path) -> dict:
    """Pipe a PreToolUse fs_write payload for ``path`` through the real hook script."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": "fs_write",
               "tool_input": {"path": str(path.relative_to(ROOT)),
                              "text": path.read_text(encoding="utf-8")}}
    proc = subprocess.run([str(HOOK_SCRIPT)], input=json.dumps(payload), text=True,
                          capture_output=True, cwd=ROOT, timeout=120, check=False)
    return {"tool_name": "fs_write", "target": payload["tool_input"]["path"],
            "exit_code": proc.returncode, "stdout": proc.stdout.strip().splitlines(),
            "stderr": proc.stderr.strip().splitlines()}


def sample_record(book) -> dict:
    root = book.record()
    rec = Record(root)
    balance, rate = Decimal("1234567.89"), Decimal("0.0525")
    interest = accrue_monthly_interest(balance, rate)
    values = {
        "ACCT-KEY": "ACC100", "ACCT-STATUS": "A", "ACCT-BRANCH": 1959,
        "ACCT-OPEN-DATE": 19681107, "ACCT-LEDGER-SEQ": 123456,
        "ACCT-BALANCE": balance, "ACCT-ANNUAL-RATE": rate,
        "WS-INTEREST": interest, "WS-NEW-BALANCE": post_interest(balance, interest),
    }
    for name, value in values.items():
        rec.set(name, value)
    owners = ["SLACK"] * root.size
    for fld in root.walk():
        if fld.is_elementary and not fld.is_overlay:
            for i in range(fld.offset, fld.offset + fld.size):
                owners[i] = fld.name
    fields = []
    for fld in root.walk():
        if not fld.is_elementary:
            continue
        raw = bytes(rec.buffer[fld.offset:fld.offset + fld.size])
        fields.append({"name": fld.name, "offset": fld.offset, "size": fld.size,
                       "hex": spaced(raw), "value": str(rec.get(fld.name)),
                       "overlay": fld.is_overlay})
    chars = []
    for b in rec.buffer:
        ch = bytes([b]).decode("cp037")
        chars.append(ch if ch.isascii() and (ch.isalnum() or ch in " {}") else ".")
    return {"bytes": [f"{b:02X}" for b in rec.buffer], "chars": chars, "owners": owners,
            "fields": fields}


def main() -> int:
    book = parse_copybook(COPYBOOK.read_text(encoding="utf-8"), fixed_format=True)

    keys = ["100ACC", "ACC100", "acc100"]
    vectors = {
        "A": comp3_vector("Packed decimal roundtrip", "-1234567.89", 9, 2, "S9(7)V99 COMP-3"),
        "B": [zoned_vector("12345"), zoned_vector("-12345")],
        "C": {"input": keys, "ascii": sorted(keys), "ebcdic": ebcdic_sorted(keys),
              "first_bytes": {k: {"ascii": f"{k.encode('ascii')[0]:02X}",
                                  "ebcdic": f"{k.encode('cp037')[0]:02X}"} for k in keys}},
        "D": [comp3_vector("Even digits, 0x0 pad nibble", v, 6, 0, "S9(6) COMP-3")
              for v in ("123456", "-123456")],
        "E": {"pic": "S9(5)V99 COMP-3", **describe_comp3("40404040", 7, 2)},
    }
    s0c7_samples = [{"pic": pic, **describe_comp3(hx, d, s)} for hx, d, s, pic in (
        ("40404040", 7, 2, "S9(5)V99 COMP-3"),
        ("0012345A", 7, 0, "S9(7) COMP-3"),
        ("01F3456C", 6, 0, "S9(6) COMP-3"),
        ("00000540123E", 11, 2, "S9(9)V99 COMP-3"),
        ("00000540123C", 11, 2, "S9(9)V99 COMP-3"),
    )]

    report = run_shadow(DEFAULT_RECORDS, DEFAULT_SEED, accrue_monthly_interest)
    report.violations.extend(scan_source(HARDENED.read_text(encoding="utf-8"),
                                         "services/hardened_service.py"))
    hardened = {"service": "services/hardened_service.py", "report": report.as_dict(),
                "screen": render_3270(report).splitlines(), "hook": run_hook(HARDENED)}

    vulnerable = None
    if VULNERABLE.is_file():
        bad = run_shadow(DEFAULT_RECORDS, DEFAULT_SEED, load_candidate(str(VULNERABLE)))
        bad.violations.extend(scan_source(VULNERABLE.read_text(encoding="utf-8"),
                                          "services/vulnerable_service.py"))
        vulnerable = {"service": "services/vulnerable_service.py", "report": bad.as_dict(),
                      "screen": render_3270(bad).splitlines(), "hook": run_hook(VULNERABLE)}

    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": DEFAULT_SEED,
        "records": DEFAULT_RECORDS,
        "copybook": {"name": COPYBOOK.name,
                     "source": COPYBOOK.read_text(encoding="utf-8").splitlines(),
                     "record_size": book.record().size,
                     "layout": book.layout_table(),
                     "sample": sample_record(book)},
        "vectors": vectors,
        "s0c7_samples": s0c7_samples,
        "hook_config": json.loads(HOOK_CONFIG.read_text(encoding="utf-8")),
        "hardened": hardened,
        "vulnerable": vulnerable,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  hardened hook exit={hardened['hook']['exit_code']}  "
          f"vulnerable={'live' if vulnerable else 'absent (captured transcript used)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
