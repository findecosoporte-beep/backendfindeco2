"""Redondeo monetario consistente en toda la API."""

from decimal import Decimal, ROUND_HALF_UP

CENTS = Decimal('0.01')


def round_money(value: Decimal) -> Decimal:
    """Redondea a 2 decimales con HALF_UP (centavos)."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)
