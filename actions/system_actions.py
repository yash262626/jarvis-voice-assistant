"""Time, date, volume, power state and assistant meta-commands."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from typing import Any, Optional

from core.models import Action, ActionResult
from utils import win_input
from utils.logger import get_logger

log = get_logger("actions.system")

HELP_TEXT = (
    "You can say: open Chrome, search Google for something, search YouTube for "
    "something, type any text into the field you're in, press Enter or Tab, "
    "copy, paste, undo, start typing mode, create a folder, or ask the time."
)

_VOLUME_KEYS = {
    "up": "volumeup", "down": "volumedown",
    "mute": "volumemute", "unmute": "volumemute",
}


class SystemActions:
    """Handlers for the system and assistant-control intents."""

    def __init__(self, context: Any, runner: Optional[Any] = None,
                 backend: Optional[Any] = None) -> None:
        self.context = context
        self.config = context.config
        self._runner = runner                    # injected in unit tests
        self.backend = backend or context.memory.get("input_backend") or win_input

    # ------------------------------------------------------------------ util
    def _run(self, command: list[str]) -> bool:
        """Run one of a *fixed* set of Windows power commands."""
        if self._runner is not None:
            return bool(self._runner(command))
        if sys.platform != "win32":
            log.info("Skipping Windows-only command: %s", command)
            return False
        try:
            subprocess.Popen(command, close_fds=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        except OSError as exc:
            log.error("Command failed %s: %s", command, exc)
            return False

    # -------------------------------------------------------------- handlers
    def get_time(self, action: Action) -> ActionResult:
        now = dt.datetime.now().strftime("%I:%M %p").lstrip("0")
        return ActionResult(success=True, speech=f"It's {now}.", detail=now)

    def get_date(self, action: Action) -> ActionResult:
        today = dt.datetime.now()
        text = today.strftime("%A, %d %B %Y").replace(" 0", " ")
        return ActionResult(success=True, speech=f"Today is {text}.", detail=text)

    def lock_pc(self, action: Action) -> ActionResult:
        if sys.platform == "win32" and self._runner is None:
            try:
                import ctypes

                ctypes.windll.user32.LockWorkStation()
                return ActionResult(success=True, speech="Locking.", detail="LockWorkStation")
            except Exception as exc:                            # noqa: BLE001
                return ActionResult.fail("I couldn't lock the computer.", detail=str(exc))
        ok = self._run(["rundll32.exe", "user32.dll,LockWorkStation"])
        return (ActionResult(success=True, speech="Locking.")
                if ok else ActionResult.fail("I couldn't lock the computer."))

    def sleep_pc(self, action: Action) -> ActionResult:
        ok = self._run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return (ActionResult(success=True, speech="Going to sleep.")
                if ok else ActionResult.fail("I couldn't put the computer to sleep."))

    def restart_pc(self, action: Action) -> ActionResult:
        ok = self._run(["shutdown", "/r", "/t", "10"])
        return (ActionResult(success=True, speech="Restarting in ten seconds. "
                                                  "Say cancel shutdown to stop it.")
                if ok else ActionResult.fail("I couldn't restart the computer."))

    def shutdown_pc(self, action: Action) -> ActionResult:
        ok = self._run(["shutdown", "/s", "/t", "10"])
        return (ActionResult(success=True, speech="Shutting down in ten seconds.")
                if ok else ActionResult.fail("I couldn't shut down the computer."))

    def set_volume(self, action: Action) -> ActionResult:
        direction = str(action.get("direction", "")).lower()
        key = _VOLUME_KEYS.get(direction)
        if not key:
            return ActionResult.fail("Volume up, down or mute?")
        try:
            presses = 5 if direction in {"up", "down"} else 1
            self.backend.press_key(key, presses=presses, interval=0.02)
        except Exception as exc:                                # noqa: BLE001
            return ActionResult.fail("I couldn't change the volume.", detail=str(exc))
        return ActionResult(success=True, speech="Done.", detail=f"volume {direction}")

    def help(self, action: Action) -> ActionResult:
        return ActionResult(success=True, speech=HELP_TEXT, detail="help")

    def noop(self, action: Action) -> ActionResult:
        return ActionResult(success=True, speech="", detail=action.intent)

    def unknown(self, action: Action) -> ActionResult:
        text = str(action.get("text", "")).strip()
        log.info("Unrecognised command: %r", text)
        return ActionResult(success=False,
                            speech="Sorry, I didn't understand that.",
                            detail=f"unparsed: {text}")


def register(router: Any, context: Any) -> None:
    actions = SystemActions(context)
    context.memory["system_actions"] = actions
    router.register("get_time", actions.get_time, "Say the current time")
    router.register("get_date", actions.get_date, "Say today's date")
    router.register("lock_pc", actions.lock_pc, "Lock the workstation")
    router.register("sleep_pc", actions.sleep_pc, "Sleep the computer")
    router.register("restart_pc", actions.restart_pc, "Restart the computer")
    router.register("shutdown_pc", actions.shutdown_pc, "Shut down the computer")
    router.register("set_volume", actions.set_volume, "Change the volume")
    router.register("help", actions.help, "List example commands")
    router.register("unknown", actions.unknown, "Unrecognised command")
    for intent in ("cancel", "repeat", "affirm", "deny"):
        router.register(intent, actions.noop, "Handled by the assistant loop")
