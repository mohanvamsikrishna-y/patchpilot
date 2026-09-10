import unittest
from slug import slugify


class SlugTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_surrounding_whitespace(self):
        self.assertEqual(slugify("  Hello World  "), "hello-world")

    def test_repeated_whitespace(self):
        self.assertEqual(slugify("Hello   World"), "hello-world")

    def test_tabs_and_newlines(self):
        self.assertEqual(slugify("Hello\tNew\nWorld"), "hello-new-world")

    def test_empty(self):
        self.assertEqual(slugify("  "), "")
