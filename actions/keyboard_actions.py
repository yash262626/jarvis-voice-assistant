"""Key presses and shortcuts sent to the currently focused application."""

from __future__ import annotations

import time
from typing import Any, Optional

from core.models import Action, ActionResult
from utils import win_input
from utils.logger import get_logger

log = get_logger("actions.keyboard")

_SPOKEN_NAMES = {
    "enter": "Enter", "tab": "Tab", "escape": "Escape", "backspace": "Backspace",
    "delete": "Delete", "space": "Space", "up": "Up", "down": "Down",
    "left": "Left", "right": "Right",
}

_SHORTCUT_NAMES = {
    ("ctrl", "c"): "Copied.",
    ("ctrl", "v"): "Pasted.",
    ("ctrl", "x"): "Cut.",
    ("ctrl", "z"): "Undone.",
    ("ctrl", "y"): "Redone.",
    ("ctrl", "a"): "Selected all.",
    ("ctrl", "s"): "Saved.",
}


class KeyboardActions:
    """Handlers for ``press_key`` and ``hotkey``."""

    def __init__(self, context: Any, backend: Optional[Any] = None) -> None:
        self.context = context
        self.config = context.config
        self.backend = backend or context.memory.get("input_backend") or win_input

    def _focus_target(self):
        tracker = getattr(self.context, "tracker", None)
        if tracker is None:
            return None
        try:
            return tracker.ensure_target(
                delay=float(self.config.get("focus_restore_delay", 0.12))
            )
        except Exception as exc:                                # noqa: BLE001
            log.warning("Focus restore failed: %s", exc)
            return None

    def press_key(self, action: Action) -> ActionResult:
        key = str(action.get("key", "")).strip().lower()
        times = int(action.get("times", 1) or 1)
        if not key:
            return ActionResult.fail("I didn't catch which key.")

        self._focus_target()
        try:
            self.backend.press_key(key, presses=max(1, min(times, 50)))
        except win_input.InputError as exc:
            return ActionResult.fail(f"I don't know the key '{key}'.", detail=str(exc))
        except Exception as exc:                                # noqa: BLE001
            log.exception("press_key failed")
            return ActionResult.fail("I couldn't press that key.", detail=str(exc))

        pretty = _SPOKEN_NAMES.get(key, key.upper())
        speech = "Done." if times == 1 else f"Pressed {pretty} {times} times."
        return ActionResult(success=True, speech=speech,
                            detail=f"Pressed {pretty} x{times}")

    def hotkey(self, action: Action) -> ActionResult:
        keys = [str(k).strip().lower() for k in action.get("keys", []) if str(k).strip()]
        if not keys:
            return ActionResult.fail("I didn't catch that shortcut.")

        self._focus_target()
        try:
            self.backend.hotkey(*keys)
            for follow_up in action.get("then", []) or []:
                time.sleep(0.05)
                self.backend.press_key(str(follow_up).lower())
        except win_input.InputError as exc:
            return ActionResult.fail("I couldn't send that shortcut.", detail=str(exc))
        except Exception as exc:                                # noqa: BLE001
            log.exception("hotkey failed")
            return ActionResult.fail("I couldn't send that shortcut.", detail=str(exc))

        speech = _SHORTCUT_NAMES.get(tuple(keys), "Done.")
        return ActionResult(success=True, speech=speech,
                            detail="Sent " + "+".join(k.upper() for k in keys))


def register(router: Any, context: Any) -> None:
    actions = KeyboardActions(context)
    context.memory["keyboard_actions"] = actions
    router.register("press_key", actions.press_key, "Press a single key")
    router.register("hotkey", actions.hotkey, "Send a keyboard shortcut")
