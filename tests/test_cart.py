from decimal import Decimal
import unittest
from cart import calculate_total


class CheckoutTests(unittest.TestCase):
    def test_preserves_cents(self):
        self.assertEqual(calculate_total(["12.99", "4.50"]), Decimal("17.49"))

    def test_half_up_rounding(self):
        self.assertEqual(calculate_total(["1.005"]), Decimal("1.01"))

    def test_discount(self):
        self.assertEqual(calculate_total(["19.99"], "0.10"), Decimal("17.99"))

    def test_empty_cart(self):
        self.assertEqual(calculate_total([]), Decimal("0.00"))

    def test_return_type(self):
        self.assertIsInstance(calculate_total(["3"]), Decimal)
