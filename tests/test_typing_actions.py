"""Typing must reach the user's app, never JARVIS, and never mangle codes."""

from __future__ import annotations

import pytest

from actions.typing_actions import TypingActions, register
from core.models import Action


@pytest.fixture
def typing(context, fake_input):
    return TypingActions(context, backend=fake_input)


def test_types_company_name(typing, fake_input):
    result = typing.type_text(Action("type_text", {"text": "Anand Trading Company"}))
    assert result.success
    assert result.speech == "Done."
    assert fake_input.typed == ["Anand Trading Company"]


def test_focus_is_restored_before_typing(typing, context):
    typing.type_text(Action("type_text", {"text": "RP0002442"}))
    assert context.tracker.calls == 1, "the target window must be secured first"


def test_reports_the_target_window(typing):
    result = typing.type_text(Action("type_text", {"text": "CAN000410"}))
    assert "EXCEL.EXE" in result.detail


def test_long_text_uses_the_clipboard(typing, fake_input, config):
    config.set("clipboard_threshold", 10)
    typing.type_text(Action("type_text", {"text": "x" * 50}))
    assert fake_input.pasted, "long text should be pasted, not typed key by key"


def test_short_text_uses_keystrokes(typing, fake_input, config):
    config.set("clipboard_threshold", 200)
    typing.type_text(Action("type_text", {"text": "Mumbai"}))
    assert fake_input.pasted == []
    assert fake_input.typed == ["Mumbai"]


def test_empty_text_is_rejected(typing, fake_input):
    result = typing.type_text(Action("type_text", {"text": "   "}))
    assert not result.success
    assert fake_input.typed == []


def test_repeat_typing(typing, fake_input):
    typing.type_text(Action("type_text", {"text": "29AAFCJ4954L1ZY"}))
    typing.repeat_typing(Action("repeat_typing"))
    assert fake_input.typed == ["29AAFCJ4954L1ZY", "29AAFCJ4954L1ZY"]


def test_repeat_without_history(typing):
    assert not typing.repeat_typing(Action("repeat_typing")).success


def test_backend_failure_is_handled(context, fake_input):
    from utils.win_input import InputError

    class BrokenBackend:
        def type_unicode(self, text, interval=0.0):
            raise InputError("access denied")

        def paste_text(self, *args, **kwargs):
            raise InputError("access denied")

    result = TypingActions(context, backend=BrokenBackend()).type_text(
        Action("type_text", {"text": "hello"})
    )
    assert not result.success
    assert "administrator" in result.speech.lower()


def test_register_adds_handlers(router, context):
    register(router, context)
    assert router.has("type_text")
    assert router.has("repeat_typing")
