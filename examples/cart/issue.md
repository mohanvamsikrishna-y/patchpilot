Checkout loses cents and rounds midpoint prices incorrectly

Customers report that a cart containing 12.99 and 4.50 returns 17 instead of
17.49. The contract requires a Decimal rounded to two decimal places using
ROUND_HALF_UP. A price of 1.005 must become 1.01. Preserve discounts and the
empty-cart behavior. Fix the implementation without weakening the tests.
