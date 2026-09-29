"""The allow-list and sandbox are what make voice control safe to leave on."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models import Action
from core.safety_manager import ALLOWED_INTENTS, SafetyManager


@pytest.fixture
def safety(config):
    return SafetyManager(config)


def test_there_is_no_shell_intent():
    for forbidden in ("run_command", "execute_shell", "eval", "powershell", "python"):
        assert forbidden not in ALLOWED_INTENTS


def test_unknown_intent_rejected(safety):
    allowed, reason = safety.validate(Action("delete_everything"))
    assert not allowed and reason


def test_typing_intent_allowed(safety):
    allowed, _ = safety.validate(Action("type_text", {"text": "Anand Trading Company"}))
    assert allowed


def test_empty_typing_rejected(safety):
    assert not safety.validate(Action("type_text", {"text": ""}))[0]


def test_huge_typing_rejected(safety):
    assert not safety.validate(Action("type_text", {"text": "x" * 6000}))[0]


def test_ctrl_alt_delete_blocked(safety):
    assert not safety.validate(Action("hotkey", {"keys": ["ctrl", "alt", "delete"]}))[0]


def test_dangerous_intents_need_confirmation(safety):
    for intent in ("shutdown_pc", "restart_pc", "close_application"):
        assert safety.needs_confirmation(Action(intent))
    assert not safety.needs_confirmation(Action("type_text", {"text": "hi"}))


def test_confirmation_question_mentions_the_app(safety):
    question = safety.confirmation_question(
        Action("close_application", {"application": "Excel"})
    )
    assert "Excel" in question


def test_system_paths_blocked(safety):
    assert not safety.check_path(Path("C:/Windows/System32/drivers"))[0]


def test_home_paths_allowed(safety):
    assert safety.check_path(Path.home() / "Desktop" / "Sales Orders")[0]


def test_outside_home_blocked_when_sandboxed(safety, config):
    config.set("sandbox_file_operations", True)
    assert not safety.check_path(Path("/tmp/somewhere-else"))[0]


def test_illegal_folder_name(safety):
    assert not safety.validate(Action("create_folder", {"name": "bad:name*"}))[0]
