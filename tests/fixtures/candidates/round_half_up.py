"""Decimal port that adds a ROUNDED phrase the COBOL source does not have.

ROUND_HALF_UP is only correct where the COBOL says ``COMPUTE ... ROUNDED``.
INTACCR has no ROUNDED, so this candidate drifts by one cent on roughly half of
all accounts. It also coerces IEEE 754 input instead of rejecting it.
"""

from decimal import ROUND_HALF_UP, Decimal


def accrue_monthly_interest(balance, annual_rate):
    monthly = Decimal(str(balance)) * Decimal(str(annual_rate)) / 12
    return monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
