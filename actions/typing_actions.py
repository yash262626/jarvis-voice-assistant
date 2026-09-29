"""Type text into whatever application the user is actually working in.

This is the feature the whole assistant is built around: click a cell in
Excel, say "type Anand Trading Company", and the text lands in that cell.

How focus is protected
----------------------
1. The GUI is created with ``WA_ShowWithoutActivating`` and lives in the tray,
   so it does not take focus when it appears or updates.
2. A background tracker remembers the last foreground window that was not
   JARVIS.
3. Right before typing, :meth:`ForegroundTracker.ensure_target` checks who has
   focus. If it is already the user's app it changes nothing at all; only if
   JARVIS somehow grabbed focus does it hand it back.
4. Characters are injected with ``SendInput`` + ``KEYEVENTF_UNICODE``, which
   Windows delivers to the focused control exactly like real typing - so it
   works in Excel cells, browser inputs, SAP/ERP fields, Notepad and chat apps
   without any per-application integration.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from core.models import Action, ActionResult
from utils import win_input
from utils.logger import get_logger, redact

log = get_logger("actions.typing")


class TypingActions:
    """Handlers for ``type_text`` and ``repeat_typing``."""

    def __init__(self, context: Any, backend: Optional[Any] = None) -> None:
        self.context = context
        self.config = context.config
        self.backend = backend or context.memory.get("input_backend") or win_input

    # ------------------------------------------------------------------ util
    def _choose_method(self, text: str) -> str:
        """Pick between per-character injection and clipboard paste."""
        method = str(self.config.get("typing_method", "auto")).lower()
        if method != "auto":
            return method
        threshold = int(self.config.get("clipboard_threshold", 200) or 200)
        return "clipboard" if len(text) > threshold else "sendinput"

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

    # -------------------------------------------------------------- handlers
    def type_text(self, action: Action) -> ActionResult:
        text = str(action.get("text", ""))
        if not text.strip():
            return ActionResult.fail("I didn't catch what to type.")

        target = self._focus_target()
        where = target.describe() if target else "the active window"
        method = self._choose_method(text)
        interval = float(self.config.get("typing_interval", 0.01) or 0)
        allow_log = bool(self.config.get("log_typed_text", False))

        log.info("Typing %s into %s via %s", redact(text, allow_log), where, method)

        try:
            if method == "clipboard":
                ok = self.backend.paste_text(
                    text, restore=bool(self.config.get("restore_clipboard", True))
                )
                if not ok:
                    log.info("Clipboard paste failed, falling back to keystrokes")
                    self.backend.type_unicode(text, interval=interval)
            elif method == "pyautogui":
                self._type_with_pyautogui(text, interval)
            else:
                self.backend.type_unicode(text, interval=interval)
        except win_input.InputError as exc:
            log.error("Input injection refused: %s", exc)
            return ActionResult.fail(
                "I couldn't type there. If that app runs as administrator, "
                "start JARVIS as administrator too.",
                detail=str(exc),
            )
        except Exception as exc:                                # noqa: BLE001
            log.exception("Typing failed")
            return ActionResult.fail("I couldn't type that.", detail=str(exc))

        self.context.memory["last_typed"] = text
        return ActionResult(
            success=True,
            speech="Done.",
            detail=f"Typed {len(text)} characters into {where}",
            data={"characters": len(text), "target": where, "method": method},
        )

    def repeat_typing(self, action: Action) -> ActionResult:
        text = self.context.memory.get("last_typed")
        if not text:
            return ActionResult.fail("I haven't typed anything yet.")
        return self.type_text(Action("type_text", {"text": text}))

    # --------------------------------------------------------------- backends
    def _type_with_pyautogui(self, text: str, interval: float) -> None:
        try:
            import pyautogui                                     # noqa: PLC0415
        except ImportError as exc:                               # pragma: no cover
            raise win_input.InputError(
                "pyautogui is not installed; run pip install pyautogui or set "
                "typing_method back to 'auto'"
            ) from exc
        pyautogui.write(text, interval=max(0.0, interval))


def register(router: Any, context: Any) -> None:
    """Plugin entry point - called automatically by the router."""
    actions = TypingActions(context)
    context.memory["typing_actions"] = actions
    router.register("type_text", actions.type_text, "Type text at the cursor")
    router.register("repeat_typing", actions.repeat_typing, "Type the last text again")
