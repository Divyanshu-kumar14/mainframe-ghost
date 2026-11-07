"""IBM EBCDIC CP-037 collating key and Zoned Decimal sign-overpunch codec.

* Collating: EBCDIC orders [a-z] < [A-Z] < [0-9], the
  reverse of ASCII for digits. Sort with ``ebcdic_sort_key``, never native str order.
* Zoned Decimal: the sign lives in the zone nibble of the
  last digit byte. ``+12345`` -> "1234E" (C5), ``-12345`` -> "1234N" (D5).
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from .comp3_packer import S0C7Abend, coerce_decimal, decimal_from_scaled_int, scaled_int

POSITIVE_OVERPUNCH = "{ABCDEFGHI"  # +0..+9, zone 0xC
NEGATIVE_OVERPUNCH = "}JKLMNOPQR"  # -0..-9, zone 0xD
_OVERPUNCH_DECODE: dict[str, tuple[int, int]] = {
    **{ch: (digit, 1) for digit, ch in enumerate(POSITIVE_OVERPUNCH)},
    **{ch: (digit, -1) for digit, ch in enumerate(NEGATIVE_OVERPUNCH)},
}
_ASCII_DIGITS = "0123456789"


def ebcdic_sort_key(text: str) -> bytes:
    """Sort key reproducing mainframe batch order: the CP-037 bytes of ``text``."""
    if not isinstance(text, str):
        raise TypeError("sort keys must be str")
    return text.encode("cp037")


def ebcdic_sorted(keys: Iterable[str], reverse: bool = False) -> list[str]:
    """Sort strings in IBM EBCDIC CP-037 collating order."""
    return sorted(keys, key=ebcdic_sort_key, reverse=reverse)


def _build_ascii_to_ebcdic() -> bytes:
    """256-entry translate table: Latin-1 byte value -> CP-037 byte (0x3F SUB if unmapped)."""
    table = bytearray([0x3F] * 256)
    for ebcdic_byte in range(256):
        code_point = ord(bytes([ebcdic_byte]).decode("cp037"))
        if code_point < 256:
            table[code_point] = ebcdic_byte
    return bytes(table)


# ``text.encode("latin-1").translate(ASCII_TO_EBCDIC_TABLE)`` equals ``text.encode("cp037")``
# for every character CP-037 can represent.
ASCII_TO_EBCDIC_TABLE: bytes = _build_ascii_to_ebcdic()


def encode_zoned(value: object, digits: int, scale: int = 0, signed: bool = True) -> str:
    """Encode a number as an overpunched zoned-decimal string (``PIC [S]9(digits)``)."""
    if isinstance(digits, bool) or not isinstance(digits, int) or digits < 1:
        raise ValueError("digits must be a positive int")
    if not 0 <= scale <= digits:
        raise ValueError("scale must satisfy 0 <= scale <= digits")
    dec = coerce_decimal(value)
    number = scaled_int(dec, scale)
    if number < 0 and not signed:
        raise ValueError("negative value in an unsigned zoned field")
    magnitude = str(abs(number))
    if len(magnitude) > digits:
        raise OverflowError(f"value needs {len(magnitude)} digits, field holds {digits}")
    body = magnitude.zfill(digits)
    if not signed:
        return body
    # An explicit negative zero ("-0") keeps its sign: "}" is -0, "{" is +0.
    negative = number < 0 or (number == 0 and dec == 0 and dec.is_signed())
    table = NEGATIVE_OVERPUNCH if negative else POSITIVE_OVERPUNCH
    return body[:-1] + table[int(body[-1])]


def decode_zoned(text: str, scale: int = 0) -> Decimal:
    """Decode an overpunched zoned string to Decimal. Never use int() on raw zoned text."""
    if not isinstance(text, str):
        raise TypeError("zoned text must be str")
    if not text:
        raise ValueError("empty zoned field")
    *leading, last = text
    for index, char in enumerate(leading):
        if char not in _ASCII_DIGITS:
            raise S0C7Abend(f"S0C7 Abend: invalid zoned digit {char!r} at position {index}",
                            index=index, kind="digit")
    if last in _ASCII_DIGITS:
        last_digit, sign = int(last), 1
    elif last in _OVERPUNCH_DECODE:
        last_digit, sign = _OVERPUNCH_DECODE[last]
    else:
        raise S0C7Abend(f"S0C7 Abend: invalid zoned sign character {last!r}",
                        index=len(text) - 1, kind="sign")
    number = int("".join(leading) + str(last_digit)) * sign
    return decimal_from_scaled_int(number, scale, negative=sign < 0)


def encode_zoned_bytes(value: object, digits: int, scale: int = 0, signed: bool = True) -> bytes:
    """EBCDIC bytes of an overpunched zoned field (e.g. +12345 -> F1 F2 F3 F4 C5)."""
    return encode_zoned(value, digits, scale, signed).encode("cp037")


def decode_zoned_bytes(data: bytes, scale: int = 0, signed: bool = True) -> Decimal:
    """Decode EBCDIC zoned bytes. Zones and digit nibbles are validated (S0C7 on error)."""
    raw = bytes(data)
    if not raw:
        raise ValueError("empty zoned field")
    digits: list[int] = []
    last_index = len(raw) - 1
    for index, byte in enumerate(raw):
        zone, digit = byte >> 4, byte & 0x0F
        if digit > 9:
            raise S0C7Abend(f"S0C7 Abend: invalid digit nibble 0x{digit:X} at byte {index}",
                            nibble=digit, index=index, kind="digit")
        if index < last_index and zone != 0xF:
            raise S0C7Abend(f"S0C7 Abend: invalid zone nibble 0x{zone:X} at byte {index}",
                            nibble=zone, index=index, kind="zone")
        digits.append(digit)
    last_zone = raw[-1] >> 4
    if last_zone not in (0xC, 0xD, 0xF):
        raise S0C7Abend(f"S0C7 Abend: invalid sign zone 0x{last_zone:X}",
                        nibble=last_zone, index=last_index, kind="sign")
    number = int("".join(map(str, digits)))
    negative = last_zone == 0xD and signed
    return decimal_from_scaled_int(-number if negative else number, scale, negative=negative)


__all__ = [
    "ASCII_TO_EBCDIC_TABLE", "NEGATIVE_OVERPUNCH", "POSITIVE_OVERPUNCH",
    "coerce_decimal", "decode_zoned", "decode_zoned_bytes", "ebcdic_sort_key",
    "ebcdic_sorted", "encode_zoned", "encode_zoned_bytes",
]
