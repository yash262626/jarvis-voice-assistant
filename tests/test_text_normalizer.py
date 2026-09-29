"""Business text must survive dictation intact."""

from __future__ import annotations

import pytest

from core.text_normalizer import (
    apply_punctuation, collapse_spelled_code, normalize_typed_text, uppercase_codes,
)


@pytest.mark.parametrize("spoken,expected", [
    ("Dear Sir comma", "Dear Sir,"),
    ("Please find attached the revised PO full stop", "Please find attached the revised PO."),
    ("yash at the rate example dot com", "yash@example.com"),
    ("BP hyphen CAN000410", "BP-CAN000410"),
    ("Is this correct question mark", "Is this correct?"),
])
def test_punctuation(spoken, expected):
    assert apply_punctuation(spoken) == expected


def test_punctuation_can_be_disabled():
    assert apply_punctuation("Dear Sir comma", enabled=False) == "Dear Sir comma"


@pytest.mark.parametrize("spoken,expected", [
    ("R P zero zero zero two four four two", "RP0002442"),
    ("C A N triple zero four one zero", "CAN000410"),
    ("code alpha bravo one two three", "code AB123"),
])
def test_spelled_codes(spoken, expected):
    assert collapse_spelled_code(spoken) == expected


def test_normal_sentences_are_untouched():
    for text in ["Anand Trading Company", "Bennikal Village Hoovina Hadagali",
                 "Please send the invoice today", "Mumbai Maharashtra"]:
        assert collapse_spelled_code(text) == text


@pytest.mark.parametrize("text,expected", [
    ("rp0002442", "RP0002442"),
    ("can000410", "CAN000410"),
    ("29aafcj4954l1zy", "29AAFCJ4954L1ZY"),
    ("1c800a2xcewayl33", "1C800A2XCEWAYL33"),
])
def test_uppercasing_codes(text, expected):
    assert uppercase_codes(text) == expected


def test_plain_words_keep_their_case():
    assert uppercase_codes("Anand Trading Company") == "Anand Trading Company"
    assert uppercase_codes("Mumbai") == "Mumbai"


def test_full_pipeline():
    assert normalize_typed_text("Dear Sir comma order rp0002442 confirmed full stop") == (
        "Dear Sir, order RP0002442 confirmed."
    )


def test_pipeline_respects_switches():
    text = "Dear Sir comma rp0002442"
    assert normalize_typed_text(text, auto_punctuation=False,
                                uppercase_alphanumeric=False) == text
