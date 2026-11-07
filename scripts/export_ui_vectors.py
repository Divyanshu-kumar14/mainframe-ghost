#!/usr/bin/env python3
"""Export real parity data from the engine into the 3270 cockpit UI.

Writes ``ui/src/data/parity_vectors.json``. Everything in it is computed here by
the actual engine, the GnuCOBOL fixtures and the PreToolUse hook script; nothing
is hand-typed:

* Golden Test Vectors A-E (.kiro/specs/mainframe_parity/requirements.md)
* copybooks/INTACCR.cpy AST, byte layout and a populated 52-byte record dump
* the GnuCOBOL oracle manifest and the COBOL program text
* for every candidate service: the real hook's exit code and transcript for a
  write of that file, plus the structured sentinel report (static scan, sandboxed
  execution against 10,000 COBOL records)

Candidates: services/hardened_service.py, services/vulnerable_service.py (if it
exists), tests/fixtures/candidates/*.py, including any Bedrock captures saved by
``services/bedrock_transpiler.py --capture``.

Run from anywhere:  python3 scripts/export_ui_vectors.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.cobol_oracle import load_oracle  # noqa: E402
from engine.comp3_packer import describe_comp3, encode_comp3, nibbles  # noqa: E402
from engine.copybook_parser import Record, parse_copybook  # noqa: E402
from engine.ebcdic_codec import decode_zoned, ebcdic_sorted, encode_zoned  # noqa: E402
from engine.shadow_fuzzer import (  # noqa: E402
    DEFAULT_RECORDS,
    DEFAULT_SEED,
    render_3270,
    verify_stdin,
)
from services.hardened_service import accrue_monthly_interest, post_interest  # noqa: E402

OUT = ROOT / "ui" / "src" / "data" / "parity_vectors.json"
COPYBOOK = ROOT / "copybooks" / "INTACCR.cpy"
COBOL_PROGRAM = ROOT / "cobol" / "src" / "intaccr_batch.cbl"
HOOK_CONFIG = ROOT / ".kiro" / "hooks" / "parity_guard.json"
HOOK_SCRIPT = ROOT / ".kiro" / "hooks" / "bin" / "verify_modernization_parity.sh"
CANDIDATE_DIR = ROOT / "tests" / "fixtures" / "candidates"

# id, file, title, one-line summary
KNOWN = [
    ("hardened", ROOT / "services" / "hardened_service.py",
     "HARDENED  Decimal ROUND_DOWN",
     "Context(prec=28, ROUND_DOWN), rejects float input, CP-037 sort"),
    ("float", ROOT / "services" / "vulnerable_service.py",
     "IEEE 754  float() + round()",
     "binary floats and banker's rounding: caught by the static scan"),
    ("floor", CANDIDATE_DIR / "round_floor.py",
     "SUBTLE  Decimal ROUND_FLOOR",
     "no float, passes a linter; wrong on every overdrawn account"),
    ("halfup", CANDIDATE_DIR / "round_half_up.py",
     "SUBTLE  Decimal ROUND_HALF_UP",
     "adds a ROUNDED the COBOL never had; coerces float input"),
]


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


def hook_payload(target: str, source: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "fs_write",
            "tool_input": {"path": target, "text": source}}


def run_hook(payload: dict) -> dict:
    """Pipe a PreToolUse fs_write payload through the real hook script."""
    proc = subprocess.run([str(HOOK_SCRIPT)], input=json.dumps(payload), text=True,
                          capture_output=True, cwd=ROOT, timeout=120, check=False)
    return {"tool_name": payload["tool_name"], "target": payload["tool_input"]["path"],
            "exit_code": proc.returncode, "stdout": proc.stdout.strip().splitlines(),
            "stderr": proc.stderr.strip().splitlines()}


def candidate_entry(cid: str, path: Path, title: str, summary: str, provenance: str,
                    meta: dict | None = None) -> dict:
    source = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(ROOT))
    # Files under tests/ are exempt from the hook, so a write is simulated to the
    # place the agent would put the service.
    target = rel if not rel.startswith("tests/") else f"services/{path.stem}.py"
    payload = hook_payload(target, source)
    code, report = verify_stdin(json.dumps(payload), DEFAULT_RECORDS, DEFAULT_SEED)
    hook = run_hook(payload)
    if hook["exit_code"] != code:
        raise SystemExit(f"hook exit {hook['exit_code']} != in-process verdict {code} for {rel}")
    return {"id": cid, "title": title, "summary": summary, "file": rel, "target": target,
            "provenance": provenance, "source": source.splitlines(),
            "report": report.as_dict(), "screen": render_3270(report).splitlines(),
            "hook": hook, "meta": meta}


def candidates() -> list[dict]:
    out = []
    for cid, path, title, summary in KNOWN:
        if path.is_file():
            out.append(candidate_entry(cid, path, title, summary,
                                       f"{path.relative_to(ROOT)} (hand-written reference)"))
    for meta_path in sorted(CANDIDATE_DIR.glob("bedrock_*.json")):
        code_path = meta_path.with_suffix(".py")
        if not code_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        prompt = meta.get("prompt", "?")
        out.append(candidate_entry(
            f"bedrock-{meta_path.stem}", code_path,
            f"BEDROCK  {prompt.upper()} PROMPT",
            f"{meta.get('model_id')} output captured {meta.get('captured_at')}",
            f"live Amazon Bedrock response, saved unedited by bedrock_transpiler --capture",
            meta))
    return out


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
    oracle = load_oracle()

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

    # Show records where truncation matters: non-zero interest, both signs.
    random_part = [r for r in oracle.records[15:] if r.interest != 0]
    first = ([r for r in random_part if r.balance_cents < 0][:2]
             + [r for r in random_part if r.balance_cents > 0][:2])
    statement = " ".join(COBOL_PROGRAM.read_text(encoding="utf-8").split())
    procedure = re.findall(r"COMPUTE [^.]*?(?= (?:COMPUTE|MOVE|WRITE|ADD) )", statement)
    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": DEFAULT_SEED,
        "records": DEFAULT_RECORDS,
        "copybook": {"name": COPYBOOK.name,
                     "source": COPYBOOK.read_text(encoding="utf-8").splitlines(),
                     "record_size": book.record().size,
                     "layout": book.layout_table(),
                     "sample": sample_record(book)},
        "oracle": {
            "compiler": oracle.manifest["compiler"],
            "runner": oracle.manifest["runner"],
            "compile": oracle.manifest["compile"],
            "records": len(oracle.records),
            "generated_at": oracle.manifest["generated_at"],
            "sha256": oracle.manifest["sha256"],
            "program": str(COBOL_PROGRAM.relative_to(ROOT)),
            "procedure": procedure,
            "sample": [{"key": r.account_key, "balance": str(r.balance),
                        "rate": str(r.annual_rate), "interest_hex": spaced(r.interest_comp3),
                        "interest": str(r.interest), "new_balance_zoned": r.new_balance_zoned}
                       for r in first],
        },
        "vectors": vectors,
        "s0c7_samples": s0c7_samples,
        "hook_config": json.loads(HOOK_CONFIG.read_text(encoding="utf-8")),
        "candidates": candidates(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    summary = ", ".join(f"{c['id']}=exit {c['hook']['exit_code']}" for c in data["candidates"])
    print(f"wrote {OUT.relative_to(ROOT)}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
