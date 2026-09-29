"""Launch and close Windows applications.

Resolution order for "open chrome":
``config/applications.json`` -> literal path -> PATH -> App Paths registry ->
Start Menu shortcut. So a Chrome installed somewhere unusual still opens
instead of failing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models import Action, ActionResult
from utils.config import load_json_asset
from utils.helpers import find_executable
from utils.logger import get_logger

log = get_logger("actions.application")

_NOISE = re.compile(
    r"\b(the|app|application|program|software|please|for me|window)\b", re.IGNORECASE
)

#: Spoken names that should map onto a registry key with a different name.
_ALIASES: Dict[str, str] = {
    "google chrome": "chrome", "chrome browser": "chrome", "browser": "chrome",
    "microsoft edge": "edge", "edge browser": "edge",
    "mozilla firefox": "firefox",
    "note pad": "notepad", "notepad plus plus": "notepad++",
    "calc": "calculator", "calculater": "calculator",
    "file explorer": "explorer", "windows explorer": "explorer",
    "my computer": "explorer", "this pc": "explorer",
    "taskmanager": "task manager", "task manger": "task manager",
    "cmd": "command prompt", "terminal": "command prompt",
    "ms excel": "excel", "microsoft excel": "excel", "exel": "excel",
    "ms word": "word", "microsoft word": "word",
    "ms outlook": "outlook", "microsoft outlook": "outlook",
    "power point": "powerpoint", "microsoft powerpoint": "powerpoint",
    "microsoft teams": "teams", "ms teams": "teams",
    "vscode": "vs code", "visual studio code": "vs code", "code editor": "vs code",
    "sap b one": "sap business one", "sap logon": "sap",
    "adobe acrobat": "acrobat", "pdf reader": "acrobat",
}


class ApplicationActions:
    """Handlers for ``open_application`` and ``close_application``."""

    def __init__(self, context: Any, launcher: Optional[Any] = None) -> None:
        self.context = context
        self.config = context.config
        self.registry: Dict[str, Any] = load_json_asset("applications.json", {}) or {}
        self._launcher = launcher                # injected in unit tests
        self._cache: Dict[str, str] = {}

    # ------------------------------------------------------------- resolution
    @staticmethod
    def clean_name(name: str) -> str:
        cleaned = _NOISE.sub(" ", str(name)).strip().lower()
        cleaned = re.sub(r"[^\w+\s.-]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return _ALIASES.get(cleaned, cleaned)

    def _candidates(self, name: str) -> List[str]:
        entry = self.registry.get(name)
        if entry is None:
            matches = get_close_matches(name, list(self.registry), n=1, cutoff=0.82)
            if matches:
                log.debug("Fuzzy matched %r -> %r", name, matches[0])
                entry = self.registry[matches[0]]
        if isinstance(entry, str):
            return [entry]
        if isinstance(entry, list):
            return [str(item) for item in entry]
        # Unknown app: try the spoken name as an executable.
        compact = name.replace(" ", "")
        return [f"{compact}.exe", compact, f"{name}.exe", name]

    def resolve(self, spoken: str) -> Optional[str]:
        """Return something Windows can start, or None."""
        name = self.clean_name(spoken)
        if not name:
            return None
        if name in self._cache:
            return self._cache[name]
        target = find_executable(self._candidates(name), display_name=name)
        if target:
            self._cache[name] = target
        return target

    # ---------------------------------------------------------------- launch
    def _start(self, target: str) -> bool:
        if self._launcher is not None:
            return bool(self._launcher(target))
        try:
            if target.endswith(":") or "://" in target:          # ms-settings: etc
                os.startfile(target)                             # type: ignore[attr-defined]
            elif target.lower().endswith(".lnk"):
                os.startfile(target)                             # type: ignore[attr-defined]
            elif sys.platform == "win32":
                subprocess.Popen([target], close_fds=True,
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            else:
                subprocess.Popen([target], close_fds=True)
            return True
        except (OSError, ValueError) as exc:
            log.error("Could not start %s: %s", target, exc)
            return False

    # -------------------------------------------------------------- handlers
    def open_application(self, action: Action) -> ActionResult:
        spoken = str(action.get("application", "")).strip()
        if not spoken:
            return ActionResult.fail("Which application should I open?")

        target = self.resolve(spoken)
        if not target:
            log.warning("Application not found: %s", spoken)
            return ActionResult.fail(
                f"I couldn't find {spoken} on this computer. "
                "You can add its path to config/applications.json."
            )
        if not self._start(target):
            return ActionResult.fail(f"I couldn't start {spoken}.")

        pretty = self.clean_name(spoken).title()
        return ActionResult(success=True, speech=f"Opening {pretty}.",
                            detail=f"Launched {target}", data={"path": target})

    def close_application(self, action: Action) -> ActionResult:
        spoken = str(action.get("application", "")).strip()
        if not spoken:
            return ActionResult.fail("Which application should I close?")
        if sys.platform != "win32":
            return ActionResult.fail("Closing applications requires Windows.")

        name = self.clean_name(spoken)
        target = self.resolve(spoken)
        image = Path(target).name if target else f"{name.replace(' ', '')}.exe"
        if not image.lower().endswith(".exe"):
            image = f"{Path(image).stem}.exe"

        try:
            completed = subprocess.run(
                ["taskkill", "/IM", image, "/F"],
                capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return ActionResult.fail(f"I couldn't close {name}.", detail=str(exc))

        if completed.returncode != 0:
            return ActionResult.fail(f"{name.title()} doesn't seem to be running.")
        return ActionResult(success=True, speech=f"Closed {name.title()}.",
                            detail=f"taskkill {image}")


def register(router: Any, context: Any) -> None:
    actions = ApplicationActions(context)
    context.memory["application_actions"] = actions
    router.register("open_application", actions.open_application, "Launch an application")
    router.register("close_application", actions.close_application, "Close an application")
