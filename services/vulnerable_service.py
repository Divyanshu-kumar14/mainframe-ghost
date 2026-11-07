"""Negative control service demonstrating IEEE 754 float drift and Banker's Rounding.

This file intentionally violates Mainframe parity invariants:
1. Uses IEEE 754 binary floating-point representation (`float()`).
2. Uses Python's built-in `round()` (Round-Half-Even / Banker's Rounding).
3. Uses float literals (`12.0`).

When intercepted by the Kiro PreToolUse hook (.kiro/hooks/bin/verify_modernization_parity.sh),
this file is rejected with POSIX Exit Code 2 (VETO).
"""

from __future__ import annotations

from decimal import Decimal


def accrue_monthly_interest(balance: Decimal, annual_rate: Decimal) -> Decimal:
    """Accrue interest using naive IEEE 754 floats and banker's rounding.

    BUG: about half of all accounts drift by $0.01 against the COBOL truncation.
    """
    value = round(float(balance) * float(annual_rate) / 12.0, 2)
    return Decimal(str(value))


def post_interest(balance: Decimal, interest: Decimal) -> Decimal:
    """Post interest using float addition."""
    return Decimal(str(round(float(balance) + float(interest), 2)))
