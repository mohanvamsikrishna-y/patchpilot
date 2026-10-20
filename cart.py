"""Tiny checkout module with an intentionally seeded rounding bug."""
from decimal import Decimal, ROUND_HALF_UP


def calculate_total(prices, discount=0):
    """Return the discounted total, rounded to cents using half-up rounding."""
    subtotal = sum(Decimal(str(price)) for price in prices)
    amount = subtotal * (Decimal("1") - Decimal(str(discount)))
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
