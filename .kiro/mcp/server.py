#!/usr/bin/env python3
"""FastMCP memory inspector for MainframeGhost (stdio transport).

Tools:
  inspect_copybook_offsets(copybook_path)          byte offsets, REDEFINES, SYNC slack
  decode_comp3_hex(hex_string, precision, scale)   nibble breakdown and S0C7 detection
  run_shadow_parity_check(source_file, sample_size) static scan + sandboxed run vs GnuCOBOL

File access is restricted to the workspace root. Candidate code never runs in this
process: it is executed by engine/candidate_runner.py in a limited child process.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastmcp import FastMCP  # noqa: E402

from engine.comp3_packer import describe_comp3  # noqa: E402
from engine.copybook_parser import CopybookError, parse_copybook  # noqa: E402
from engine.shadow_fuzzer import (  # noqa: E402
    DEFAULT_SEED,
    check_candidate,
    mentions_candidate_function,
    run_shadow,
    scan_source,
)

MAX_FILE_BYTES = 1_000_000
MAX_SAMPLE_SIZE = 1_000_000

mcp = FastMCP("mainframe-inspector")


def _workspace_file(path_text: str) -> Path:
    candidate = Path(path_text)
    resolved = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError(f"path escapes the workspace: {path_text}")
    if not resolved.is_file():
        raise FileNotFoundError(f"not a file: {path_text}")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"file too large (> {MAX_FILE_BYTES} bytes): {path_text}")
    return resolved


@mcp.tool
def inspect_copybook_offsets(copybook_path: str) -> dict:
    """Parse a COBOL copybook and report byte offsets, REDEFINES overlays and SYNC slack bytes."""
    try:
        text = _workspace_file(copybook_path).read_text(encoding="utf-8", errors="replace")
        copybook = parse_copybook(text)
    except (CopybookError, OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "records": [{"name": rec.name, "length": rec.size} for rec in copybook.records],
        "fields": copybook.layout_table(),
    }


@mcp.tool
def decode_comp3_hex(hex_string: str, precision: int, scale: int = 0) -> dict:
    """Unpack COMP-3 hex into a Decimal with nibble breakdown; flags S0C7 invalid nibbles."""
    return describe_comp3(hex_string, precision, scale)


@mcp.tool
def run_shadow_parity_check(source_file: str, sample_size: int = 10000) -> dict:
    """Scan a Python file for IEEE 754 contamination, then execute its
    accrue_monthly_interest in a sandbox and diff it against GnuCOBOL output."""
    try:
        path = _workspace_file(source_file)
        code = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    size = max(1, min(int(sample_size), MAX_SAMPLE_SIZE))
    rel = str(path.relative_to(ROOT))
    report = run_shadow(size, DEFAULT_SEED)
    report.violations.extend(scan_source(code, rel))
    if mentions_candidate_function(code):
        check_candidate(code, report, rel, size)
    result = report.as_dict()
    result["ok"] = True
    result["exit_code"] = 0 if report.passed else 2
    return result


if __name__ == "__main__":
    mcp.run()
