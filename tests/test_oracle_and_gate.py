"""GnuCOBOL oracle, sandboxed candidate execution, the hook gate, Bedrock gating, API."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from engine.cobol_oracle import acctin_line, load_oracle, parse_acctin_line, verify_engines
from engine.comp3_packer import encode_comp3
from engine.shadow_fuzzer import (
    ParityReport,
    check_candidate,
    execute_candidate,
    generate_records,
    proposed_source,
    verify_stdin,
)

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".kiro" / "hooks" / "bin" / "verify_modernization_parity.sh"
CANDIDATES = ROOT / "tests" / "fixtures" / "candidates"
HARDENED = (ROOT / "services" / "hardened_service.py").read_text(encoding="utf-8")
FLOOR = (CANDIDATES / "round_floor.py").read_text(encoding="utf-8")
HALF_UP = (CANDIDATES / "round_half_up.py").read_text(encoding="utf-8")


def payload(tool: str, **tool_input) -> str:
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": tool_input})


def run_hook(data: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(HOOK)], input=data, text=True, capture_output=True, cwd=ROOT,
                          timeout=120, check=False)


# ----------------------------------------------------------------------------- oracle

def test_oracle_fixtures_load_and_match_the_seeded_corpus():
    data = load_oracle()
    assert data.manifest["compiler"].startswith("cobc (GnuCOBOL)")
    corpus = generate_records(len(data.records), data.manifest["seed"])
    assert [(r.account_key, r.balance_cents, r.rate_units) for r in corpus] == \
        [(r.account_key, r.balance_cents, r.rate_units) for r in data.records]


def test_python_engines_match_gnucobol_byte_for_byte():
    assert verify_engines(load_oracle()) == []


def test_cobol_truncates_toward_zero_and_writes_positive_zero():
    data = load_oracle()
    by_input = {(r.balance_cents, r.rate_units): r for r in data.records}
    tiny_negative = by_input[(-1, 1)]          # -0.01 * 0.0001 / 12 -> -0.0000000833
    assert tiny_negative.interest_comp3 == bytes.fromhex("00000000000C")
    assert tiny_negative.new_balance_zoned == "0000000000J"   # -0.01, J = -1 overpunch
    truncated = by_input[(14285714, 1200)]     # 142857.14 * 0.12 / 12 = 1428.5714
    assert truncated.interest == Decimal("1428.57")


def test_cobol_sort_is_ebcdic_order():
    keys = load_oracle().sorted_keys
    assert keys == sorted(keys, key=lambda s: s.encode("cp037"))
    assert keys != sorted(keys)


def test_acctin_line_roundtrip():
    line = acctin_line("acc100", -123456, 525)
    assert line == "acc100  -0000012345600525"
    assert parse_acctin_line(line) == ("acc100", -123456, 525)


def test_tampered_fixture_is_detected(tmp_path):
    from engine.cobol_oracle import FIXTURES, OracleError

    for name in ("manifest.json", "ACCTIN", "ACCTOUT", "KEYSOUT"):
        (tmp_path / name).write_bytes((FIXTURES / name).read_bytes())
    raw = bytearray((tmp_path / "ACCTOUT").read_bytes())
    raw[13] ^= 0x01
    (tmp_path / "ACCTOUT").write_bytes(bytes(raw))
    with pytest.raises(OracleError, match="sha256"):
        load_oracle(tmp_path)


# ----------------------------------------------------------------------------- sandbox

def test_hardened_service_passes_against_cobol():
    report = ParityReport()
    check_candidate(HARDENED, report, "hardened")
    assert report.candidate_records == 10_000
    assert report.candidate_drift == 0 and report.candidate_errors == []
    assert report.candidate_misposted == 0


def test_round_floor_passes_static_scan_but_fails_execution():
    from engine.shadow_fuzzer import scan_source

    assert scan_source(FLOOR) == []
    report = ParityReport()
    check_candidate(FLOOR, report, "floor")
    assert report.candidate_drift > 4000
    assert not report.passed
    assert any("differ from cobc" in e for e in report.candidate_errors)


def test_half_up_is_caught_for_drift_and_float_coercion():
    report = ParityReport()
    check_candidate(HALF_UP, report, "halfup")
    assert report.candidate_drift > 4000
    assert any("IEEE 754 input was accepted" in e for e in report.candidate_errors)


def test_sandbox_has_no_credentials_or_cwd_access():
    probe = ("import os\n"
             "from decimal import Decimal\n"
             "LEAKED = sorted(k for k in os.environ if k.startswith(('AWS', 'KIRO')))\n"
             "def accrue_monthly_interest(b, r):\n"
             "    if LEAKED: raise RuntimeError(LEAKED)\n"
             "    raise ValueError(os.getcwd())\n")
    run = execute_candidate(probe, [("1.00", "0.0100")])
    kind, text = run.results[0]
    assert kind == "!ValueError"                 # no credential names leaked
    assert "mg-candidate-" in text               # ran in a throwaway directory


def test_sandbox_kills_infinite_loops():
    run = execute_candidate("def accrue_monthly_interest(b, r):\n    while True:\n        pass\n",
                            [("1.00", "0.0100")])
    assert run.error and "died" in run.error


def test_candidate_cannot_forge_the_verdict_with_print():
    forged = json.dumps({"loaded": True, "results": [["Decimal", "0.00"]], "float_probe": "TypeError"})
    code = f"print({forged!r})\ndef accrue_monthly_interest(b, r):\n    return b\n"
    run = execute_candidate(code, [("100.00", "0.1200")])
    assert run.results == [["Decimal", "100.00"]]


# ----------------------------------------------------------------------------- hook gate

def test_hook_executes_fs_write_and_vetoes_subtle_decimal_bug():
    proc = run_hook(payload("fs_write", path="services/ported.py", text=FLOOR))
    assert proc.returncode == 2
    assert "Candidate veto" in proc.stderr and "GnuCOBOL" in proc.stderr


def test_hook_rebuilds_str_replace_against_the_file_on_disk():
    old = "    return monthly.quantize(CENT, rounding=ROUND_DOWN, context=FIN_CTX)"
    # decimal's rounding constants are plain strings, so no new import is needed
    new = '    return monthly.quantize(CENT, rounding="ROUND_HALF_EVEN", context=FIN_CTX)'
    assert old in HARDENED
    code, report = verify_stdin(payload("str_replace", path="services/hardened_service.py",
                                        oldStr=old, newStr=new), 10_000, 1959)
    assert code == 2 and report.candidate_drift > 0


def test_proposed_source_handles_append_and_exempt_paths():
    src, rel = proposed_source(json.loads(payload("fs_append", path="services/hardened_service.py",
                                                  text="X = 1\n")))
    assert rel == "services/hardened_service.py" and src.endswith("X = 1\n") and "def accrue" in src
    assert proposed_source(json.loads(payload("fs_write", path="tests/t.py", text=FLOOR)))[0] is None


def test_hook_passes_hardened_write():
    proc = run_hook(payload("fs_write", path="services/hardened_service.py", text=HARDENED))
    assert proc.returncode == 0, proc.stderr
    assert "candidate_drift=0" in proc.stdout


# ----------------------------------------------------------------------------- Bedrock

class FakeBedrock:
    def __init__(self, code: str):
        self.code = code
        self.calls: list[dict] = []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        body = {"content": [{"type": "thinking", "thinking": "..."},
                            {"type": "text", "text": f"```python\n{self.code}```"}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}
        return {"body": io.BytesIO(json.dumps(body).encode())}


def test_bedrock_program_mode_inlines_copybook_and_gates_output():
    from services.bedrock_transpiler import transpile

    source = (ROOT / "cobol" / "src" / "intaccr_batch.cbl").read_text(encoding="utf-8")
    bad = FakeBedrock(FLOOR)
    result = transpile(source, "program", client=bad)
    request = json.loads(bad.calls[0]["body"])
    cobol = request["messages"][0]["content"][0]["text"].split("<cobol>", 1)[1]
    assert "ACCT-ANNUAL-RATE" in cobol and "PIC 9V9(4)" in cobol
    assert "COPY INTACCR" not in cobol
    assert "temperature" not in request
    assert bad.calls[0]["modelId"] == "us.anthropic.claude-sonnet-5-5"
    assert not result.accepted and result.report.candidate_drift > 0

    good = transpile(source, "program", client=FakeBedrock(HARDENED))
    assert good.accepted


def test_bedrock_cli_vetoes_with_exit_2(monkeypatch, tmp_path, capsys):
    import services.bedrock_transpiler as bt

    monkeypatch.setattr(bt, "make_client", lambda region=None: FakeBedrock(HALF_UP))
    out = tmp_path / "svc.py"
    code = bt.main([str(ROOT / "cobol" / "src" / "intaccr_batch.cbl"), "-o", str(out)])
    assert code == 2 and not out.exists()
    assert "nothing written" in capsys.readouterr().err


# ----------------------------------------------------------------------------- cockpit API

def test_cockpit_api_engine_routes():
    from cockpit import server

    assert server.comp3({"hex": "40404040", "pic": "S9(5)V99"})["s0c7"] is True
    assert server.pack({"value": "-1234567.89", "pic": "S9(7)V99 COMP-3"})["hex"] == "123456789D"
    assert server.zoned({"text": "1234N", "pic": "S9(5)"})["value"] == "-12345"
    assert server.sort_keys({"keys": ["100ACC", "ACC100", "acc100"]})["ebcdic"] == \
        ["acc100", "ACC100", "100ACC"]
    lay = server.layout({"copybook": (ROOT / "copybooks" / "INTACCR.cpy").read_text()})
    assert lay["records"][0]["size"] == 52
    with pytest.raises(server.ApiError):
        server.pack({"value": Decimal("1.5"), "pic": "S9(3)V9"})   # numbers must be strings


def test_cockpit_verify_is_refused_when_exec_disabled():
    from cockpit import server

    with pytest.raises(server.ApiError) as err:
        server.verify({"code": HARDENED}, exec_enabled=False)
    assert err.value.status == 403
    assert server._is_loopback("127.0.0.1") and not server._is_loopback("0.0.0.0")
    result = server.verify({"code": FLOOR}, exec_enabled=True)
    assert result["exit_code"] == 2


def test_export_script_runs_and_agrees_with_hook():
    proc = subprocess.run([sys.executable, "scripts/export_ui_vectors.py"], cwd=ROOT,
                          capture_output=True, text=True, timeout=300, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "hardened=exit 0" in proc.stdout and "floor=exit 2" in proc.stdout


def test_bootstrap_hook_fails_closed(tmp_path):
    proc = subprocess.run([str(HOOK)], input="{}", text=True, capture_output=True, cwd=tmp_path,
                          timeout=30, check=False)
    assert proc.returncode == 2


def test_comp3_helper_used_by_fixture_matches():
    assert encode_comp3(Decimal("1428.57"), 11, 2) == bytes.fromhex("00000142857C")
