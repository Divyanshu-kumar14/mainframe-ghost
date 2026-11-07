"""Hardened AWS Lambda port of the COBOL INTEREST-ACCRUAL batch step.

COBOL source being reproduced (no ROUNDED phrase, so results truncate toward zero):

    01  ACCOUNT-IN.
        05  ACCT-KEY          PIC X(8).
        05  ACCT-BALANCE      PIC S9(9)V99 COMP-3.
        05  ACCT-ANNUAL-RATE  PIC 9V9(4).
    01  ACCOUNT-OUT.
        05  WS-INTEREST       PIC S9(9)V99 COMP-3.
        05  WS-NEW-BALANCE    PIC S9(9)V99.          *> zoned, sign overpunched
    ...
    COMPUTE WS-INTEREST    = (ACCT-BALANCE * ACCT-ANNUAL-RATE) / 12.
    COMPUTE WS-NEW-BALANCE = ACCT-BALANCE + WS-INTEREST.
    SORT ... ON ASCENDING KEY ACCT-KEY                 *> EBCDIC CP-037 order

Parity rules (specs/PRD.md Sections 4 and 5.2):
* decimal.Decimal only, explicit Context(prec=28, rounding=ROUND_DOWN).
* Results quantized with ROUND_DOWN, never the built-in rounding function.
* JSON parsed with parse_float=Decimal; IEEE 754 floats are rejected with TypeError.
* Account keys sorted by their CP-037 bytes.

The parity sentinel exercises ``accrue_monthly_interest`` directly:
    python3 engine/shadow_fuzzer.py --candidate services/hardened_service.py

Lambda handler: ``services.hardened_service.lambda_handler`` (deploy with the
``engine`` package in the same bundle).
"""

from __future__ import annotations

import json
from decimal import ROUND_DOWN, Context, Decimal

from engine.comp3_packer import S0C7Abend, coerce_decimal, decode_comp3, encode_comp3
from engine.ebcdic_codec import ebcdic_sort_key, encode_zoned

FIN_CTX = Context(prec=28, rounding=ROUND_DOWN)
CENT = Decimal("0.01")
TWELVE = Decimal(12)

BALANCE_DIGITS, BALANCE_SCALE = 11, 2   # PIC S9(9)V99
RATE_DIGITS, RATE_SCALE = 5, 4          # PIC 9V9(4)
INTEREST_DIGITS, INTEREST_SCALE = 11, 2  # PIC S9(9)V99 COMP-3
KEY_LENGTH = 8                          # PIC X(8)
MAX_ACCOUNTS = 10_000
MAX_BODY_BYTES = 2_000_000


class InputError(ValueError):
    """Request data that cannot be represented in the COBOL record layout."""


# ----------------------------------------------------------------------------- arithmetic

def accrue_monthly_interest(balance: Decimal, annual_rate: Decimal) -> Decimal:
    """COMPUTE WS-INTEREST = (BALANCE * ANNUAL-RATE) / 12, truncated to cents."""
    if not isinstance(balance, Decimal) or not isinstance(annual_rate, Decimal):
        raise TypeError("balance and annual_rate must be decimal.Decimal")
    product = FIN_CTX.multiply(balance, annual_rate)
    monthly = FIN_CTX.divide(product, TWELVE)
    return monthly.quantize(CENT, rounding=ROUND_DOWN, context=FIN_CTX)


def post_interest(balance: Decimal, interest: Decimal) -> Decimal:
    """COMPUTE WS-NEW-BALANCE = BALANCE + WS-INTEREST (exact at scale 2)."""
    return FIN_CTX.add(balance, interest).quantize(CENT, rounding=ROUND_DOWN, context=FIN_CTX)


# ----------------------------------------------------------------------------- validation

def _fixed_point(value: object, field: str, digits: int, scale: int, signed: bool) -> Decimal:
    """Validate a numeric input against its PIC. Floats raise TypeError, never coerce."""
    if isinstance(value, float):
        raise TypeError(f"{field}: IEEE 754 float rejected; send the amount as a JSON string")
    try:
        number = coerce_decimal(value)
    except TypeError as exc:
        raise TypeError(f"{field}: {exc}") from None
    except (ValueError, ArithmeticError):
        raise InputError(f"{field}: {value!r} is not a valid COBOL numeric") from None
    exponent = number.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > scale:
        raise InputError(f"{field}: more than {scale} decimal places for PIC scale {scale}")
    if number < 0 and not signed:
        raise InputError(f"{field}: negative value in an unsigned field")
    limit = Decimal(1).scaleb(digits - scale)
    if number.copy_abs() >= limit:
        raise InputError(f"{field}: {number} exceeds {digits - scale} integer digits")
    return number.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_DOWN, context=FIN_CTX)


def _account_key(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise InputError("account_key: required non-empty string")
    try:
        encoded = value.encode("cp037")
    except UnicodeEncodeError:
        raise InputError("account_key: contains characters outside EBCDIC CP-037") from None
    if len(encoded) > KEY_LENGTH:
        raise InputError(f"account_key: longer than PIC X({KEY_LENGTH})")
    return value


def _balance(account: dict) -> Decimal:
    """Balance from a decimal string or a raw COMP-3 dump (``balance_comp3_hex``)."""
    if "balance_comp3_hex" in account:
        raw_hex = account["balance_comp3_hex"]
        if not isinstance(raw_hex, str):
            raise InputError("balance_comp3_hex: must be a hex string")
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError:
            raise InputError("balance_comp3_hex: not valid hex") from None
        try:  # S0C7Abend (an ArithmeticError) propagates to the handler as a 422
            return decode_comp3(raw, BALANCE_DIGITS, BALANCE_SCALE)
        except ValueError as exc:
            raise InputError(f"balance_comp3_hex: {exc}") from None
    if "balance" not in account:
        raise InputError("balance or balance_comp3_hex is required")
    return _fixed_point(account["balance"], "balance", BALANCE_DIGITS, BALANCE_SCALE, True)


# ----------------------------------------------------------------------------- batch step

def process_account(account: object) -> dict:
    """Run one ACCOUNT-IN record through the accrual step. All numbers leave as strings."""
    if not isinstance(account, dict):
        raise InputError("each account must be a JSON object")
    key = _account_key(account.get("account_key"))
    balance = _balance(account)
    if "annual_rate" not in account:
        raise InputError("annual_rate is required")
    rate = _fixed_point(account["annual_rate"], "annual_rate", RATE_DIGITS, RATE_SCALE, False)
    interest = accrue_monthly_interest(balance, rate)
    new_balance = post_interest(balance, interest)
    try:
        interest_packed = encode_comp3(interest, INTEREST_DIGITS, INTEREST_SCALE)
        zoned_text = encode_zoned(new_balance, BALANCE_DIGITS, BALANCE_SCALE)
    except OverflowError:
        raise InputError("new balance overflows PIC S9(9)V99 (SIZE ERROR)") from None
    return {
        "account_key": key,
        "balance": str(balance),
        "annual_rate": str(rate),
        "interest": str(interest),
        "new_balance": str(new_balance),
        "interest_comp3_hex": interest_packed.hex().upper(),
        "new_balance_zoned": zoned_text,
        "new_balance_zoned_hex": zoned_text.encode("cp037").hex().upper(),
    }


def process_batch(accounts: list) -> list[dict]:
    """Process and return accounts in EBCDIC CP-037 key order (mainframe SORT order)."""
    if len(accounts) > MAX_ACCOUNTS:
        raise InputError(f"batch exceeds {MAX_ACCOUNTS} accounts")
    results = [process_account(account) for account in accounts]
    return sorted(results, key=lambda row: ebcdic_sort_key(row["account_key"]))


# ----------------------------------------------------------------------------- Lambda

def _parse_event(event: object) -> dict:
    """API Gateway proxy event (JSON string body) or a direct-invocation dict."""
    if not isinstance(event, dict):
        raise InputError("event must be a JSON object")
    if "body" not in event:
        return event  # direct invocation; floats are caught by _fixed_point
    body = event["body"]
    if body is None:
        raise InputError("request body is empty")
    if isinstance(body, dict):
        return body
    if not isinstance(body, str):
        raise InputError("body must be a JSON string")
    if event.get("isBase64Encoded"):
        raise InputError("base64-encoded bodies are not accepted")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise InputError("request body too large")
    try:
        parsed = json.loads(body, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise InputError(f"malformed JSON: {exc.msg}") from None
    if not isinstance(parsed, dict):
        raise InputError("body must be a JSON object")
    return parsed


def _response(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def lambda_handler(event, context):  # noqa: ARG001 - Lambda signature
    """AWS Lambda entrypoint.

    Request body: ``{"accounts": [{"account_key": "ACC100", "balance": "1234.56",
    "annual_rate": "0.0525"}]}``. A single account object is also accepted.
    ``balance_comp3_hex`` may replace ``balance`` for raw mainframe dumps.
    """
    try:
        request = _parse_event(event)
        accounts = request.get("accounts", [request] if "account_key" in request else None)
        if not isinstance(accounts, list) or not accounts:
            raise InputError("accounts must be a non-empty list")
        results = process_batch(accounts)
    except S0C7Abend as exc:
        return _response(422, {"status": "ABEND", "abend": "S0C7", "error": str(exc),
                               "nibble": None if exc.nibble is None else f"0x{exc.nibble:X}",
                               "nibble_index": exc.index, "kind": exc.kind})
    except TypeError as exc:
        return _response(400, {"status": "REJECTED", "error": str(exc)})
    except InputError as exc:
        return _response(400, {"status": "REJECTED", "error": str(exc)})
    total = Decimal(0)
    for row in results:
        total = FIN_CTX.add(total, Decimal(row["interest"]))
    return _response(200, {
        "status": "SUCCESS",
        "count": len(results),
        "total_interest": str(total),
        "accounts": results,
    })
