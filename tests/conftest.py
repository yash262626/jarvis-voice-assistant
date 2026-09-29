"""Shared fixtures. No test here touches the real OS: every backend is faked."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.command_router import ActionContext, CommandRouter      # noqa: E402
from core.intent_engine import IntentEngine                       # noqa: E402
from core.safety_manager import SafetyManager                     # noqa: E402
from utils.config import Config                                   # noqa: E402


class FakeInput:
    """Stands in for utils.win_input - records instead of injecting keystrokes."""

    def __init__(self) -> None:
        self.typed: list[str] = []
        self.pasted: list[str] = []
        self.keys: list[tuple[str, int]] = []
        self.hotkeys: list[tuple[str, ...]] = []

    def type_unicode(self, text, interval=0.0):
        self.typed.append(text)
        return len(text)

    def press_key(self, key, presses=1, interval=0.0):
        self.keys.append((str(key), presses))

    def hotkey(self, *keys):
        self.hotkeys.append(tuple(str(k) for k in keys))

    def paste_text(self, text, restore=True, delay=0.0):
        self.pasted.append(text)
        self.typed.append(text)
        return True

    def get_clipboard_text(self):
        return ""

    def set_clipboard_text(self, text):
        return True


class FakeTracker:
    """Pretends Excel is the focused window."""

    def __init__(self, name="EXCEL.EXE") -> None:
        self.name = name
        self.calls = 0

    def ensure_target(self, delay=0.0):
        self.calls += 1

        class _Window:
            def describe(inner) -> str:
                return self.name

        return _Window()


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.set("typing_interval", 0)
    cfg.set("focus_restore_delay", 0)
    cfg.set("log_typed_text", False)
    return cfg


@pytest.fixture
def fake_input() -> FakeInput:
    return FakeInput()


@pytest.fixture
def context(config, fake_input) -> ActionContext:
    ctx = ActionContext(config=config, safety=SafetyManager(config),
                        tracker=FakeTracker())
    ctx.memory["input_backend"] = fake_input
    return ctx


@pytest.fixture
def router(context) -> CommandRouter:
    return CommandRouter(context)


@pytest.fixture
def engine(config) -> IntentEngine:
    return IntentEngine(config)
