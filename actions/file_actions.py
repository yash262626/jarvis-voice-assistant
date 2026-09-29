"""Folder operations. Creation and opening only - JARVIS never deletes files."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from core.models import Action, ActionResult
from utils.helpers import user_folder
from utils.logger import get_logger

log = get_logger("actions.file")


class FileActions:
    """Handlers for ``create_folder`` and ``open_folder``."""

    def __init__(self, context: Any, opener: Optional[Any] = None) -> None:
        self.context = context
        self.config = context.config
        self.safety = context.safety
        self._opener = opener                    # injected in unit tests

    # ------------------------------------------------------------------ util
    def _reveal(self, path: Path) -> bool:
        if self._opener is not None:
            return bool(self._opener(str(path)))
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(path)], close_fds=True)
            else:
                subprocess.Popen(["xdg-open", str(path)], close_fds=True)
            return True
        except OSError as exc:
            log.error("Could not open %s: %s", path, exc)
            return False

    def _base_path(self, location: str) -> Path:
        folder = user_folder(location or "desktop")
        return folder if folder else Path.home() / "Desktop"

    # -------------------------------------------------------------- handlers
    def create_folder(self, action: Action) -> ActionResult:
        name = str(action.get("name", "")).strip().strip(".")
        location = str(action.get("location", "desktop")).strip().lower()
        if not name:
            return ActionResult.fail("What should I call the folder?")

        target = self._base_path(location) / name
        allowed, reason = self.safety.check_path(target)
        if not allowed:
            return ActionResult.fail(reason)

        if target.exists():
            return ActionResult(success=True,
                                speech=f"{name} already exists on your {location}.",
                                detail=str(target))
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.error("mkdir failed: %s", exc)
            return ActionResult.fail("I couldn't create that folder.", detail=str(exc))

        log.info("Created folder %s", target)
        return ActionResult(success=True,
                            speech=f"Created {name} on your {location}.",
                            detail=str(target), data={"path": str(target)})

    def open_folder(self, action: Action) -> ActionResult:
        name = str(action.get("name", "")).strip()
        location = str(action.get("location", "") or "").strip().lower()
        if not name:
            return ActionResult.fail("Which folder should I open?")

        known = user_folder(name)
        target = known if known else self._base_path(location or "desktop") / name

        allowed, reason = self.safety.check_path(target)
        if not allowed:
            return ActionResult.fail(reason)
        if not Path(target).exists():
            return ActionResult.fail(f"I couldn't find a folder called {name}.")
        if not self._reveal(Path(target)):
            return ActionResult.fail("I couldn't open File Explorer.")

        return ActionResult(success=True, speech=f"Opening {name}.", detail=str(target))


def register(router: Any, context: Any) -> None:
    actions = FileActions(context)
    context.memory["file_actions"] = actions
    router.register("create_folder", actions.create_folder, "Create a folder")
    router.register("open_folder", actions.open_folder, "Open a folder")
