"""Plausible AI port that passes a float-only linter and still corrupts the ledger.

No float, no round(): it uses decimal.Decimal and quantize, so a static IEEE 754
scan approves it. The bug is ROUND_FLOOR. COBOL without ROUNDED truncates toward
zero; ROUND_FLOOR rounds toward negative infinity, so every overdrawn account
whose interest is not a whole number of cents is charged one extra cent.
Positive-balance unit tests cannot see it. The sandboxed run against GnuCOBOL can.
"""

from decimal import ROUND_FLOOR, Decimal


def accrue_monthly_interest(balance: Decimal, annual_rate: Decimal) -> Decimal:
    if not isinstance(balance, Decimal) or not isinstance(annual_rate, Decimal):
        raise TypeError("balance and annual_rate must be decimal.Decimal")
    return (balance * annual_rate / 12).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
