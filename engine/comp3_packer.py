"""IBM System/390 packed decimal (COMP-3) encoder/decoder.

Layout rules (specs/PRD.md, Failure Mode 2):

* Length:  L = floor(D / 2) + 1 bytes for D declared digits.
* Even D:  a leading 0x0 pad nibble fills the high half of byte 0.
* Sign:    low nibble of the last byte. 0xC positive, 0xD negative,
           0xF unsigned. 0xA, 0xB, 0xE and 0x0-0x9 are rejected.
* Any invalid digit or sign nibble raises S0C7Abend (decimal data exception).

All arithmetic is exact: values are handled as Decimal tuples and Python ints.
No IEEE 754 float is ever created or accepted.
"""

from __future__ import annotations

from decimal import Decimal

POSITIVE_SIGN = 0xC
NEGATIVE_SIGN = 0xD
UNSIGNED_SIGN = 0xF
VALID_SIGNS = frozenset({POSITIVE_SIGN, NEGATIVE_SIGN, UNSIGNED_SIGN})
MAX_PACKED_DIGITS = 31


class S0C7Abend(ArithmeticError):
    """Synthetic IBM S0C7 Decimal Data Exception.

    ``nibble`` is the offending nibble value, ``index`` its position counted
    in nibbles from the high end of the field, and ``kind`` is "digit" or "sign".
    """

    def __init__(self, message: str, *, nibble: int | None = None,
                 index: int | None = None, kind: str | None = None) -> None:
        super().__init__(message)
        self.nibble = nibble
        self.index = index
        self.kind = kind


def packed_length(digits: int) -> int:
    """Byte length of a COMP-3 field with ``digits`` decimal digits."""
    _check_digits(digits)
    return digits // 2 + 1


def _check_digits(digits: int) -> None:
    if isinstance(digits, bool) or not isinstance(digits, int):
        raise TypeError("digits must be an int")
    if not 1 <= digits <= MAX_PACKED_DIGITS:
        raise ValueError(f"digits must be 1..{MAX_PACKED_DIGITS}, got {digits}")


def coerce_decimal(value: object) -> Decimal:
    """Convert int, str or Decimal to Decimal. float is rejected, never coerced."""
    if isinstance(value, float):
        raise TypeError("IEEE 754 float rejected: pass Decimal, int or str")
    if isinstance(value, bool):
        raise TypeError("bool is not a valid numeric value")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        result = Decimal(value)
    else:
        raise TypeError(f"unsupported numeric type {type(value).__name__}")
    if not result.is_finite():
        raise ValueError("NaN and Infinity are not valid COBOL numerics")
    return result


def scaled_int(value: object, scale: int) -> int:
    """Return ``value * 10**scale`` truncated toward zero (COBOL default, no ROUNDED).

    Exact integer arithmetic on the Decimal tuple, so no context or rounding mode
    can influence the result.
    """
    dec = coerce_decimal(value)
    sign, digit_tuple, exponent = dec.as_tuple()
    coefficient = int("".join(map(str, digit_tuple))) if digit_tuple else 0
    shift = exponent + scale
    if shift >= 0:
        coefficient *= 10 ** shift
    else:
        coefficient //= 10 ** (-shift)
    return -coefficient if sign and coefficient else coefficient


def decimal_from_scaled_int(number: int, scale: int, negative: bool | None = None) -> Decimal:
    """Exact Decimal with exponent ``-scale`` (AC-001.3).

    ``negative`` forces the sign flag, so a zoned "}" decodes to Decimal("-0").
    """
    digits = tuple(int(c) for c in str(abs(number)))
    sign = (number < 0) if negative is None else negative
    return Decimal((1 if sign else 0, digits, -scale))


def encode_comp3(value: object, digits: int, scale: int = 0, signed: bool = True) -> bytes:
    """Encode ``value`` as packed decimal for ``PIC [S]9(digits-scale)V9(scale) COMP-3``."""
    _check_digits(digits)
    if not 0 <= scale <= digits:
        raise ValueError("scale must satisfy 0 <= scale <= digits")
    number = scaled_int(value, scale)
    if number < 0 and not signed:
        raise ValueError("negative value in an unsigned COMP-3 field")
    magnitude = str(abs(number))
    if len(magnitude) > digits:
        raise OverflowError(f"value needs {len(magnitude)} digits, field holds {digits}")
    length = packed_length(digits)
    digit_nibbles = magnitude.zfill(2 * length - 1)  # even D gets one leading 0 pad nibble
    if not signed:
        sign = UNSIGNED_SIGN
    else:
        sign = NEGATIVE_SIGN if number < 0 else POSITIVE_SIGN
    return bytes.fromhex(digit_nibbles + format(sign, "X"))


def nibbles(data: bytes) -> list[int]:
    """Split bytes into high/low nibbles."""
    out: list[int] = []
    for byte in data:
        out.append(byte >> 4)
        out.append(byte & 0x0F)
    return out


def decode_comp3(data: bytes, digits: int | None = None, scale: int = 0) -> Decimal:
    """Decode packed decimal bytes to Decimal, raising S0C7Abend on any bad nibble.

    When ``digits`` is given the byte length is validated against ``D // 2 + 1``
    and, for even D, the pad nibble must be 0x0.
    """
    if isinstance(data, str) or not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes-like")
    raw = bytes(data)
    if not raw:
        raise ValueError("empty packed field")
    if digits is not None:
        expected = packed_length(digits)
        if len(raw) != expected:
            raise ValueError(f"COMP-3 PIC with {digits} digits is {expected} bytes, got {len(raw)}")
    parts = nibbles(raw)
    sign_nibble = parts[-1]
    digit_nibbles = parts[:-1]
    for index, nib in enumerate(digit_nibbles):
        if nib > 9:
            raise S0C7Abend(
                f"S0C7 Abend: invalid digit nibble 0x{nib:X} at nibble {index}",
                nibble=nib, index=index, kind="digit")
    if sign_nibble not in VALID_SIGNS:
        raise S0C7Abend(
            f"S0C7 Abend: invalid sign nibble 0x{sign_nibble:X}",
            nibble=sign_nibble, index=len(parts) - 1, kind="sign")
    if digits is not None and digits % 2 == 0 and digit_nibbles[0] != 0:
        raise ValueError("non-zero pad nibble in an even-digit COMP-3 field")
    number = int("".join(map(str, digit_nibbles)))
    if sign_nibble == NEGATIVE_SIGN:
        number = -number
    return decimal_from_scaled_int(number, scale)


def describe_comp3(hex_string: str, precision: int | None = None, scale: int = 0) -> dict:
    """Non-raising nibble breakdown used by the MCP inspector."""
    cleaned = "".join(hex_string.split()).replace("0x", "").replace("0X", "")
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError as exc:
        return {"valid": False, "error": f"invalid hex: {exc}"}
    parts = nibbles(raw)
    result: dict = {
        "hex": raw.hex().upper(),
        "byte_length": len(raw),
        "nibbles": [f"{n:X}" for n in parts],
        "sign_nibble": f"0x{parts[-1]:X}" if parts else None,
        "valid": False,
        "s0c7": False,
    }
    sign_name = {POSITIVE_SIGN: "positive", NEGATIVE_SIGN: "negative", UNSIGNED_SIGN: "unsigned"}
    if parts:
        result["sign_class"] = sign_name.get(parts[-1], "INVALID")
    try:
        value = decode_comp3(raw, precision, scale)
    except S0C7Abend as exc:
        result.update(s0c7=True, error=str(exc), invalid_nibble=f"0x{exc.nibble:X}",
                      invalid_nibble_index=exc.index, invalid_nibble_kind=exc.kind)
    except (ValueError, TypeError) as exc:
        result["error"] = str(exc)
    else:
        result.update(valid=True, value=str(value))
    return result
