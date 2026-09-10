"""Tiny URL slug utility with intentionally incomplete whitespace handling."""
import re


def slugify(text):
    """Lowercase text and collapse surrounding or repeated whitespace."""
    return text.lower().replace(" ", "-")
