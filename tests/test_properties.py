"""Property-based tests (Hypothesis) for the codecs and engines.

Strategies generate integers and decimal strings only; no binary floats are used.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.comp3_packer import S0C7Abend, decode_comp3, encode_comp3, packed_length
from engine.copybook_parser import Record, parse_copybook
from engine.ebcdic_codec import decode_zoned, decode_zoned_bytes, ebcdic_sorted, encode_zoned
from engine.shadow_fuzzer import (
    golden_interest_cents,
    golden_pack,
    golden_packed_valid,
    golden_sorted,
    golden_zoned,
    modern_interest,
)

settings.register_profile("ci", max_examples=300, deadline=None)
settings.load_profile("ci")


@st.composite
def pic_and_value(draw, max_digits: int = 18):
    digits = draw(st.integers(1, max_digits))
    scale = draw(st.integers(0, digits))
    number = draw(st.integers(-(10 ** digits) + 1, 10 ** digits - 1))
    return digits, scale, Decimal(number).scaleb(-scale)


@given(pic_and_value())
def test_comp3_roundtrip_length_and_pad_nibble(case):
    digits, scale, value = case
    data = encode_comp3(value, digits, scale)
    assert len(data) == packed_length(digits) == digits // 2 + 1
    if digits % 2 == 0:
        assert data[0] >> 4 == 0          # even D: leading 0x0 pad nibble
    assert data[-1] & 0x0F in (0xC, 0xD)
    decoded = decode_comp3(data, digits, scale)
    assert decoded == value and decoded.as_tuple().exponent == -scale


@given(pic_and_value(max_digits=11))
def test_comp3_engine_matches_independent_golden_packer(case):
    digits, scale, value = case
    number = int(value.scaleb(scale))
    assert encode_comp3(value, digits, scale) == golden_pack(number, digits)


@given(st.binary(min_size=1, max_size=10))
def test_decode_either_abends_or_agrees_with_golden_validity(data):
    valid = golden_packed_valid(data)
    try:
        decode_comp3(data)
    except S0C7Abend:
        assert not valid
    else:
        assert valid


@given(pic_and_value(max_digits=18))
def test_zoned_roundtrip_text_and_ebcdic_bytes(case):
    digits, scale, value = case
    text = encode_zoned(value, digits, scale)
    assert len(text) == digits
    assert decode_zoned(text, scale) == value
    assert decode_zoned_bytes(text.encode("cp037"), scale) == value


@given(st.integers(-(10 ** 11) + 1, 10 ** 11 - 1))
def test_zoned_matches_golden_overpunch(number):
    assert encode_zoned(Decimal(number), 11).encode("cp037") == golden_zoned(number, 11)


@given(st.integers(-50_000_000_000, 50_000_000_000), st.integers(0, 99_999))
def test_modern_interest_truncates_like_integer_golden(balance_cents, rate_units):
    interest = modern_interest(balance_cents, rate_units)
    assert interest == Decimal(golden_interest_cents(balance_cents, rate_units)).scaleb(-2)
    exact = Decimal(balance_cents * rate_units) / Decimal(12 * 10 ** 6)
    assert abs(interest) <= abs(exact)                 # toward zero, never away
    assert abs(exact - interest) < Decimal("0.01")


_KEY = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
               min_size=1, max_size=8)


@given(st.lists(_KEY, min_size=1, max_size=40))
def test_ebcdic_sort_matches_golden_rank_table(keys):
    assert ebcdic_sorted(keys) == golden_sorted(keys)


@given(st.integers(0, 99_999_999))
def test_redefines_alias_sees_every_write(date):
    book = parse_copybook(
        "01 R.\n 05 D PIC 9(8).\n 05 P REDEFINES D.\n  10 Y PIC 9(4).\n"
        "  10 M PIC 9(2).\n  10 DD PIC 9(2).\n")
    rec = Record(book.record())
    rec.set("D", date)
    text = str(date).zfill(8)
    assert (rec.get("Y"), rec.get("M"), rec.get("DD")) == \
        (int(text[:4]), int(text[4:6]), int(text[6:]))


@pytest.mark.parametrize("digits", [1, 4, 5, 9, 18])
@given(prefix=st.integers(1, 7))
def test_sync_binary_alignment(digits, prefix):
    book = parse_copybook(f"01 R.\n 05 A PIC X({prefix}).\n 05 B PIC S9({digits}) COMP SYNC.\n")
    field = next(f for f in book.layout_table() if f["name"] == "B")
    align = 2 if digits <= 4 else 4
    assert field["offset"] % align == 0
    assert field["slack_before"] == (-prefix) % align
