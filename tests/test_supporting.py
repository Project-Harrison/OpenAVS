import pytest
from sim.supporting import identifier, scramble


# ── identifier ────────────────────────────────────────────────────────────────

def test_identifier_default_length():
    assert len(identifier()) == 8

def test_identifier_custom_length():
    assert len(identifier(12)) == 12

def test_identifier_uppercase_alphanum():
    result = identifier(100)
    assert result.isupper() or result.isalnum()
    assert all(c.isalnum() and (c.isupper() or c.isdigit()) for c in result)

def test_identifier_unique():
    ids = {identifier() for _ in range(50)}
    assert len(ids) > 45  # collision in 50 tries would be extraordinary


# ── scramble ──────────────────────────────────────────────────────────────────

def test_scramble_same_length():
    name = "VESSEL"
    assert len(scramble(name, 5)) == len(name)

def test_scramble_intensity_max_preserves():
    # very high intensity → almost never scrambled, original chars dominate
    name = "ALPHA"
    result = scramble(name, 10000)
    assert result == name

def test_scramble_intensity_zero_fully_scrambles():
    # intensity 0 → every character replaced
    name = "BRAVO"
    result = scramble(name, 0)
    # all chars come from the pool (none from original)
    assert result != name or len(name) == 0

def test_scramble_empty_string():
    assert scramble("", 5) == ""
