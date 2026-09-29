"""Safety layer between "what JARVIS heard" and "what JARVIS does".

Rules:

* Only intents on :data:`ALLOWED_INTENTS` can ever reach a handler. Anything
  else - including anything an LLM invents - is dropped.
* Consequential intents (shutdown, restart, delete, mass close) must be
  confirmed out loud before they run.
* File operations are restricted to the user's own profile folder.
* There is no ``run_command`` / ``execute_shell`` intent anywhere in JARVIS,
  by design.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Set, Tuple

from core.models import Action
from utils.config import Config
from utils.logger import get_logger

log = get_logger("core.safety")

#: Every intent JARVIS is capable of performing. The list *is* the security
#: boundary - adding a handler without adding it here does nothing.
ALLOWED_INTENTS: Set[str] = {
    # applications
    "open_application", "close_application",
    # browser
    "open_website", "web_search", "youtube_search",
    # typing / keyboard
    "type_text", "press_key", "hotkey", "repeat_typing",
    # files
    "create_folder", "open_folder",
    # system
    "get_time", "get_date", "lock_pc", "sleep_pc", "restart_pc", "shutdown_pc",
    "set_volume",
    # assistant control
    "start_dictation", "stop_dictation", "sleep_assistant", "cancel", "exit_app",
    "affirm", "deny", "help", "repeat", "unknown",
}

#: Intents that always require a spoken "yes" first.
DANGEROUS_INTENTS: Set[str] = {
    "shutdown_pc", "restart_pc", "sleep_pc", "close_application",
}

CONFIRMATION_QUESTIONS = {
    "shutdown_pc": "Are you sure you want me to shut down the computer?",
    "restart_pc": "Are you sure you want me to restart the computer?",
    "sleep_pc": "Should I put the computer to sleep?",
    "close_application": "Should I close {application}?",
}

#: Folder names that must never be created/opened by voice.
_BLOCKED_PATH_PARTS = {
    "windows", "system32", "syswow64", "program files", "program files (x86)",
    "programdata", "$recycle.bin", "boot", "recovery",
}

_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class SafetyManager:
    """Validates actions before the router is allowed to execute them."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()

    # ------------------------------------------------------------------ API
    def validate(self, action: Action) -> Tuple[bool, str]:
        """Return ``(allowed, reason)``. Reason is spoken when not allowed."""
        if action.intent not in ALLOWED_INTENTS:
            log.warning("Blocked non-allowlisted intent: %s", action.intent)
            return False, "That command isn't something I'm allowed to run."

        if action.intent == "type_text":
            text = str(action.get("text", ""))
            if not text.strip():
                return False, "I didn't catch what to type."
            if len(text) > 5000:
                return False, "That text is too long to type safely."

        if action.intent in {"create_folder", "open_folder"}:
            if not self.config.get("allow_file_operations", True):
                return False, "File operations are disabled in settings."
            name = str(action.get("name", ""))
            if action.intent == "create_folder" and _UNSAFE_NAME.search(name):
                return False, "That folder name contains characters Windows won't accept."

        if action.intent == "hotkey":
            keys = [str(k).lower() for k in action.get("keys", [])]
            if not keys:
                return False, "I didn't catch that shortcut."
            if set(keys) >= {"ctrl", "alt", "delete"}:
                return False, "Windows doesn't allow me to send that shortcut."

        return True, ""

    def needs_confirmation(self, action: Action) -> bool:
        if not self.config.get("require_confirmation_for_dangerous_actions", True):
            return False
        return action.intent in DANGEROUS_INTENTS

    def confirmation_question(self, action: Action) -> str:
        template = CONFIRMATION_QUESTIONS.get(
            action.intent, "Are you sure you want me to do that?"
        )
        try:
            return template.format(**action.params)
        except (KeyError, IndexError):
            return "Are you sure you want me to do that?"

    # ------------------------------------------------------------- file paths
    def check_path(self, path: Path) -> Tuple[bool, str]:
        """Keep voice-driven file operations inside the user's own profile."""
        try:
            resolved = Path(path).expanduser().resolve()
        except (OSError, RuntimeError):
            return False, "That location doesn't look valid."

        parts = {part.lower() for part in resolved.parts}
        if parts & _BLOCKED_PATH_PARTS:
            return False, "I won't touch system folders."

        if not self.config.get("sandbox_file_operations", True):
            return True, ""

        home = Path.home().resolve()
        try:
            resolved.relative_to(home)
        except ValueError:
            return False, "I can only work inside your user folder."
        return True, ""
