"""The router is the choke point: allow-list, confirmation, error containment."""

from __future__ import annotations

import pytest

from core.models import Action, ActionResult


def test_registration_and_dispatch(router):
    router.register("get_time", lambda action: ActionResult.ok("It's 5 o'clock."))
    result = router.execute(Action("get_time"))
    assert result.success
    assert result.speech == "It's 5 o'clock."


def test_unregistered_intent_fails_cleanly(router):
    result = router.execute(Action("get_time"))
    assert not result.success
    assert "don't know how" in result.speech


def test_non_allowlisted_intent_is_blocked(router):
    called = []
    router.register("run_shell_command", lambda action: called.append(1))
    result = router.execute(Action("run_shell_command", {"cmd": "format C:"}))
    assert not result.success
    assert called == [], "an intent outside the allow-list must never run"


def test_handler_exception_is_contained(router):
    def explode(action):
        raise RuntimeError("boom")

    router.register("get_time", explode)
    result = router.execute(Action("get_time"))
    assert not result.success
    assert "boom" in result.detail


def test_dangerous_intent_requires_confirmation(router):
    ran = []
    router.register("shutdown_pc", lambda action: ran.append(1) or ActionResult.ok())
    result = router.execute(Action("shutdown_pc"))
    assert result.needs_confirmation
    assert ran == []

    confirmed = router.execute(result.pending, confirmed=True)
    assert confirmed.success
    assert ran == [1]


def test_confirmation_can_be_disabled(router, config):
    config.set("require_confirmation_for_dangerous_actions", False)
    router.register("shutdown_pc", lambda action: ActionResult.ok("Shutting down."))
    assert not router.execute(Action("shutdown_pc")).needs_confirmation


def test_execute_all_stops_on_failure(router):
    calls = []
    router.register("type_text", lambda a: calls.append("type") or ActionResult.fail("no"))
    router.register("press_key", lambda a: calls.append("key") or ActionResult.ok())
    results = router.execute_all([Action("type_text", {"text": "x"}),
                                  Action("press_key", {"key": "enter"})])
    assert len(results) == 1
    assert calls == ["type"]


def test_execute_all_runs_the_chain(router):
    calls = []
    router.register("type_text", lambda a: calls.append(a.get("text")) or ActionResult.ok())
    router.register("press_key", lambda a: calls.append(a.get("key")) or ActionResult.ok())
    router.execute_all([
        Action("type_text", {"text": "Anand Trading Company"}),
        Action("press_key", {"key": "tab"}),
        Action("type_text", {"text": "Mumbai"}),
        Action("press_key", {"key": "enter"}),
    ])
    assert calls == ["Anand Trading Company", "tab", "Mumbai", "enter"]


def test_plugin_autoloading(router):
    loaded = router.load_plugins("actions")
    assert loaded >= 5
    for intent in ("type_text", "press_key", "hotkey", "open_website",
                   "web_search", "youtube_search", "open_application",
                   "create_folder", "get_time"):
        assert router.has(intent), f"{intent} was not registered"
