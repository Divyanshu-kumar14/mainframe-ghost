"""Golden Test Vectors A-E (specs/PRD.md Section 8) plus parser, fuzzer and hook tests."""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import pytest

from engine.comp3_packer import S0C7Abend, decode_comp3, encode_comp3, packed_length
from engine.copybook_parser import CopybookError, Record, parse_copybook
from engine.ebcdic_codec import (
    ASCII_TO_EBCDIC_TABLE,
    decode_zoned,
    decode_zoned_bytes,
    ebcdic_sorted,
    encode_zoned,
    encode_zoned_bytes,
)
from engine.shadow_fuzzer import (
    ParityReport,
    compare_record,
    generate_records,
    golden_interest_cents,
    run_shadow,
    scan_source,
    verify_stdin,
)

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".kiro" / "hooks" / "bin" / "verify_modernization_parity.sh"
FUZZER = ROOT / "engine" / "shadow_fuzzer.py"


# ------------------------------------------------------------------ Vector A

def test_vector_a_comp3_roundtrip():
    # 05 WS-BALANCE PIC S9(7)V99 COMP-3.
    digits, scale = 9, 2
    packed = encode_comp3(Decimal("-1234567.89"), digits, scale)
    assert packed_length(digits) == 5
    assert len(packed) == 5
    assert packed.hex().upper() == "123456789D"
    assert packed[-1] & 0x0F == 0xD
    assert decode_comp3(packed, digits, scale) == Decimal("-1234567.89")


# ------------------------------------------------------------------ Vector B

def test_vector_b_zoned_overpunch_positive():
    # 05 WS-AMOUNT PIC S9(5).
    assert encode_zoned_bytes(12345, 5).hex().upper() == "F1F2F3F4C5"
    text = encode_zoned(12345, 5)
    assert text == "1234E"
    assert decode_zoned(text) == 12345
    assert decode_zoned_bytes(bytes.fromhex("F1F2F3F4C5")) == 12345


def test_vector_b_zoned_overpunch_negative():
    assert encode_zoned_bytes(-12345, 5).hex().upper() == "F1F2F3F4D5"
    text = encode_zoned(-12345, 5)
    assert text == "1234N"
    assert decode_zoned(text) == -12345
    assert decode_zoned_bytes(bytes.fromhex("F1F2F3F4D5")) == -12345


def test_vector_b_naive_int_crashes_but_codec_does_not():
    with pytest.raises(ValueError):
        int("1234E")
    assert decode_zoned("1234E") == 12345


@pytest.mark.parametrize("digit", range(10))
def test_zoned_full_overpunch_matrix(digit):
    assert decode_zoned("000" + "{ABCDEFGHI"[digit]) == digit
    assert decode_zoned("000" + "}JKLMNOPQR"[digit]) == -digit


# ------------------------------------------------------------------ Vector C

def test_vector_c_ebcdic_collating_inversion():
    keys = ["100ACC", "ACC100", "acc100"]
    assert sorted(keys) == ["100ACC", "ACC100", "acc100"]            # ASCII order
    assert ebcdic_sorted(keys) == ["acc100", "ACC100", "100ACC"]     # EBCDIC CP-037 order
    assert [k.encode("cp037")[0] for k in ebcdic_sorted(keys)] == [0x81, 0xC1, 0xF1]


def test_ebcdic_class_order_lower_upper_digit():
    assert ebcdic_sorted(["9", "Z", "z", "a", "A", "0"]) == ["a", "z", "A", "Z", "0", "9"]


def test_ascii_to_ebcdic_table_matches_cp037():
    text = "Hello World 0123456789 ABCxyz"
    assert text.encode("latin-1").translate(ASCII_TO_EBCDIC_TABLE) == text.encode("cp037")


# ------------------------------------------------------------------ Vector D

@pytest.mark.parametrize(("value", "hexdump", "sign"), [
    (123456, "0123456C", 0xC),
    (-123456, "0123456D", 0xD),
])
def test_vector_d_even_digit_leading_zero_nibble(value, hexdump, sign):
    # 05 WS-ACCOUNT-ID PIC S9(6) COMP-3.
    packed = encode_comp3(value, 6)
    assert packed_length(6) == 4
    assert len(packed) == 4
    assert packed.hex().upper() == hexdump
    assert packed[0] >> 4 == 0x0
    assert packed[-1] & 0x0F == sign
    assert decode_comp3(packed, 6) == Decimal(value)


def test_unsigned_comp3_uses_f_sign():
    assert encode_comp3(123, 3, signed=False).hex().upper() == "123F"


# ------------------------------------------------------------------ Vector E

def test_vector_e_s0c7_on_ebcdic_spaces():
    # 05 WS-BALANCE PIC S9(5)V99 COMP-3. Uninitialized EBCDIC spaces.
    assert packed_length(7) == 4
    with pytest.raises(S0C7Abend) as info:
        decode_comp3(bytes.fromhex("40404040"), 7, 2)
    assert info.value.kind == "sign"
    assert info.value.nibble == 0x0


def test_vector_e_fuzzer_battery_flags_the_dump_and_hook_vetoes():
    report = ParityReport()
    from engine.shadow_fuzzer import check_packed_dumps
    check_packed_dumps([{"hex": "40404040", "digits": 7, "scale": 2}], report)
    assert report.packed_dump_abends and not report.passed

    payload = {"tool_name": "fs_write", "tool_input": {
        "path": "notes.txt", "packed_fields": [{"hex": "40404040", "digits": 7, "scale": 2}]}}
    code, _ = verify_stdin(json.dumps(payload), records=200, seed=1)
    assert code == 2


@pytest.mark.parametrize("raw", ["0A", "1B3C", "12E3", "123A", "123B", "123E", "1230", "1239"])
def test_invalid_nibbles_raise_s0c7(raw):
    with pytest.raises(S0C7Abend):
        decode_comp3(bytes.fromhex(raw if len(raw) % 2 == 0 else raw + "C"))


def test_valid_sign_nibbles_accepted():
    for sign in "CDF":
        decode_comp3(bytes.fromhex("123" + sign))


# ------------------------------------------------------------------ Decimal discipline

def test_float_inputs_are_rejected_not_coerced():
    with pytest.raises(TypeError):
        encode_comp3(0.1, 5, 2)
    with pytest.raises(TypeError):
        encode_zoned(1.5, 5, 1)


def test_truncation_toward_zero_not_bankers_rounding():
    assert encode_comp3(Decimal("142.857"), 5, 2).hex().upper() == "14285C"
    assert encode_comp3(Decimal("-142.857"), 5, 2).hex().upper() == "14285D"
    assert encode_comp3(Decimal("0.125"), 3, 2).hex().upper() == "012C"
    assert Decimal("0.125").quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN) == Decimal("0.12")


def test_overflow_is_an_error():
    with pytest.raises(OverflowError):
        encode_comp3(1000, 3)


def test_decoded_exponent_matches_pic_scale():
    assert decode_comp3(bytes.fromhex("12345C"), 5, 2).as_tuple().exponent == -2


# ------------------------------------------------------------------ Copybook parser

TX_COPYBOOK = """
       01  TRANSACTION-RECORD.
           05  TX-DATE             PIC 9(8).
           05  TX-DATE-PARTS REDEFINES TX-DATE.
               10  TX-YEAR         PIC 9(4).
               10  TX-MONTH        PIC 9(2).
               10  TX-DAY          PIC 9(2).
"""

ACC_COPYBOOK = """
       01  ACCOUNT-RECORD.
           05  ACC-FLAG        PIC X(1).            *> Offset 0 (1 byte)
           05  ACC-BALANCE     PIC S9(9) COMP SYNC. *> Must align to 4-byte boundary!
"""


def test_redefines_overlay_offsets_and_write_through():
    book = parse_copybook(TX_COPYBOOK)
    rec = book.record()
    assert rec.size == 8
    fields = {row["name"]: row for row in book.layout_table()}
    assert (fields["TX-DATE"]["offset"], fields["TX-DATE"]["size"]) == (0, 8)
    assert (fields["TX-YEAR"]["offset"], fields["TX-YEAR"]["size"]) == (0, 4)
    assert (fields["TX-MONTH"]["offset"], fields["TX-MONTH"]["size"]) == (4, 2)
    assert (fields["TX-DAY"]["offset"], fields["TX-DAY"]["size"]) == (6, 2)

    record = Record(rec)
    record["TX-DATE"] = 20261107
    assert record["TX-YEAR"] == 2026
    record["TX-YEAR"] = 2027                        # alias write must update the base field
    assert record["TX-DATE"] == 20271107
    assert record.buffer.decode("cp037") == "20271107"
    view = record.view("TX-DAY")                    # memoryview slice over the same buffer
    view[:] = "31".encode("cp037")
    assert record["TX-DATE"] == 20271131


def test_sync_slack_bytes_and_record_length():
    book = parse_copybook(ACC_COPYBOOK)
    assert book.record().size == 8                  # not 1 + 4
    rows = {row["name"]: row for row in book.layout_table()}
    assert rows["ACC-BALANCE"]["offset"] == 4
    assert rows["ACC-BALANCE"]["slack_before"] == 3
    assert rows["ACC-BALANCE"]["slack_range"] == [1, 4]

    record = Record(book.record())
    record["ACC-FLAG"] = "X"
    record["ACC-BALANCE"] = 123456
    assert record.buffer.hex().upper() == "E70000000001E240"   # PRD memory map
    assert record["ACC-BALANCE"] == 123456


@pytest.mark.parametrize(("pic", "prefix", "expected_offset", "expected_size"), [
    ("S9(4) COMP SYNC", 1, 2, 2),
    ("S9(9) COMP SYNC", 1, 4, 4),
    ("S9(18) COMP SYNC", 1, 8, 8),
    ("S9(9) COMP", 1, 1, 4),         # without SYNC no slack
    ("S9(7) COMP-3 SYNC", 1, 1, 4),  # SYNC never aligns packed decimal
])
def test_sync_alignment_rules(pic, prefix, expected_offset, expected_size):
    text = f"01 R.\n 05 A PIC X({prefix}).\n 05 B PIC {pic}.\n"
    rows = {row["name"]: row for row in parse_copybook(text).layout_table()}
    assert rows["B"]["offset"] == expected_offset
    assert rows["B"]["size"] == expected_size


def test_comp3_and_display_field_sizes_and_roundtrip():
    text = """
    01 PAY.
       05 P-AMT   PIC S9(7)V99 COMP-3.
       05 P-ID    PIC S9(6) COMP-3.
       05 P-ZONE  PIC S9(5).
       05 P-NAME  PIC X(4).
    """
    book = parse_copybook(text)
    rows = {r["name"]: r for r in book.layout_table()}
    assert (rows["P-AMT"]["size"], rows["P-ID"]["size"], rows["P-ZONE"]["size"]) == (5, 4, 5)
    assert book.record().size == 5 + 4 + 5 + 4
    rec = Record(book.record())
    rec["P-AMT"] = Decimal("-1234567.89")
    rec["P-ID"] = 123456
    rec["P-ZONE"] = -12345
    rec["P-NAME"] = "ab"
    assert rec.view("P-AMT").hex().upper() == "123456789D"
    assert rec.view("P-ID").hex().upper() == "0123456C"
    assert rec.view("P-ZONE").hex().upper() == "F1F2F3F4D5"
    assert rec["P-AMT"] == Decimal("-1234567.89")
    assert rec["P-ZONE"] == -12345
    assert rec["P-NAME"] == "ab  "


def test_group_usage_is_inherited_and_levels_up_to_49():
    text = """
    01 TOP.
       05 GRP COMP-3.
          10 A PIC S9(3).
          10 B PIC S9(4).
       05 C.
          10 D.
             15 E PIC 9(2).
    """
    rows = {r["name"]: r for r in parse_copybook(text).layout_table()}
    assert rows["A"]["usage"] == "COMP-3" and rows["A"]["size"] == 2
    assert rows["B"]["size"] == 3
    assert rows["E"]["level"] == 15 and rows["E"]["offset"] == 5


def test_unsupported_constructs_raise():
    with pytest.raises(CopybookError):
        parse_copybook("01 R.\n 05 A PIC X OCCURS 3 TIMES.\n")
    with pytest.raises(CopybookError):
        parse_copybook("01 R.\n 05 A PIC Z(5)9.\n")
    with pytest.raises(CopybookError):
        parse_copybook("01 R.\n 05 A PIC X(4).\n 05 B REDEFINES MISSING PIC X(4).\n")
    with pytest.raises(CopybookError):
        parse_copybook("01 R.\n 05 A PIC X(2).\n 05 B REDEFINES A PIC X(4).\n")


# ------------------------------------------------------------------ Shadow fuzzer

def test_golden_and_modern_agree_for_10000_records():
    report = run_shadow(10_000, seed=1959)
    assert report.records == 10_000
    assert report.drift_pct == "0.00000%"
    assert report.drifted == 0
    assert report.sort_mismatches == 0
    assert report.s0c7_unexpected == 0
    assert report.s0c7_injected_detected > 0       # the battery really exercised S0C7
    assert report.passed


def test_known_truncation_example():
    # 142,857.14 * 0.12 / 12 = 1,428.5714 dollars = 142,857.14 cents -> truncates to 142,857
    assert golden_interest_cents(14285714, 1200) == 142857
    assert golden_interest_cents(-14285714, 1200) == -142857    # toward zero, not floor


def test_negative_control_float_engine_is_detected_as_drift():
    """A float based candidate must show drift; proves the comparator can fail."""
    def float_candidate(balance: Decimal, annual_rate: Decimal) -> Decimal:
        value = float(balance) * float(annual_rate) / 12
        return Decimal(str(round(value, 2)))             # banker's rounding on a float

    report = ParityReport()
    records = generate_records(10_000, seed=1959)
    drifted = 0
    for rec in records:
        report.comparisons += 1
        if not compare_record(rec, report, float_candidate):
            drifted += 1
    assert drifted > 0
    assert report.candidate_drift == drifted


def test_correct_candidate_has_zero_drift():
    from engine.shadow_fuzzer import FIN_CTX, CENT
    from decimal import ROUND_DOWN

    def good(balance: Decimal, annual_rate: Decimal) -> Decimal:
        interest = FIN_CTX.divide(FIN_CTX.multiply(balance, annual_rate), Decimal(12))
        return interest.quantize(CENT, rounding=ROUND_DOWN, context=FIN_CTX)

    report = ParityReport()
    assert all(compare_record(r, report, good) for r in generate_records(2_000, seed=7))
    assert report.candidate_drift == 0


# ------------------------------------------------------------------ Contamination scanner

def test_scanner_flags_float_round_and_literals_with_line_numbers():
    code = "from decimal import Decimal\n\nrate = 0.05\nx = float(y)\nz = round(q, 2)\n"
    found = scan_source(code, "svc.py")
    assert [(v.line, v.detail) for v in found] == [
        (3, "float literal 0.05"), (4, "forbidden float() call"), (5, "forbidden round() call")]


def test_scanner_ignores_strings_comments_methods_and_annotations():
    code = (
        '# uses 0.5 and float(x) in a comment\n'
        'msg = "round(1.5) is banned, float(3)"\n'
        'def f(v: float) -> float:\n    return isinstance(v, float)\n'
        'amount = Decimal("0.10") + obj.round(2)\n'
        'big = 0xFF + 10\n'
    )
    assert scan_source(code) == []


def test_scanner_handles_indented_fragments():
    assert len(scan_source("    total = price * 1.5\n")) == 1


def test_engine_modules_are_float_free():
    for module in (ROOT / "engine").glob("*.py"):
        assert scan_source(module.read_text(encoding="utf-8"), module.name) == [], module.name


# ------------------------------------------------------------------ Hook script contract

def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([str(HOOK)], input=json.dumps(payload), text=True,
                          capture_output=True, cwd=ROOT, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "MAINFRAME_GHOST_PYTHON": sys.executable})


def test_hook_is_executable():
    assert HOOK.exists() and HOOK.stat().st_mode & 0o111


def test_hook_exit_0_on_clean_payload():
    result = _run_hook({"tool_name": "fs_write", "tool_input": {
        "path": "services/interest.py",
        "text": "from decimal import Decimal\nRATE = Decimal('0.05')\n"}})
    assert result.returncode == 0, result.stderr
    assert "[PASS]" in result.stdout


def test_hook_exit_2_on_float_contamination():
    result = _run_hook({"tool_name": "fs_write", "tool_input": {
        "path": "services/interest.py",
        "text": "def accrue(b):\n    return round(b * 0.05 / 12, 2)\n"}})
    assert result.returncode == 2
    assert "[VETO]" in result.stderr
    assert "Float precision violation" in result.stderr


def test_hook_uses_prd_payload_shape_too():
    result = _run_hook({"tool": "deploy_lambda", "parameters": {
        "function_name": "InterestAccrualService",
        "source_path": "engine/comp3_packer.py"}})
    assert result.returncode == 0, result.stderr


def test_hook_exit_2_on_s0c7_dump():
    result = _run_hook({"tool_name": "execute_bash", "tool_input": {
        "command": "ls", "packed_fields": [{"hex": "40404040", "digits": 7, "scale": 2}]}})
    assert result.returncode == 2
    assert "S0C7" in result.stderr


def test_fuzzer_cli_exit_codes():
    ok = subprocess.run([sys.executable, str(FUZZER), "--records", "500"],
                        capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert ok.returncode == 0 and "drift=0.00000%" in ok.stdout
    bad = subprocess.run([sys.executable, str(FUZZER), "--records", "10", "--candidate", "/nonexistent.py"],
                         capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert bad.returncode == 1                      # sentinel error, never a silent pass
