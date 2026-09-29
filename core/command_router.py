"""Routes validated :class:`Action` objects to the handler that performs them.

Handlers register themselves, so adding ``actions/outlook_actions.py`` with a
``register(router, context)`` function is enough to teach JARVIS new tricks -
no changes to the router, engine or GUI required.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.models import Action, ActionResult
from core.safety_manager import SafetyManager
from utils.config import Config
from utils.logger import get_logger

log = get_logger("core.router")

Handler = Callable[[Action], ActionResult]


@dataclass
class ActionContext:
    """Everything an action handler is allowed to touch."""

    config: Config
    safety: SafetyManager
    tracker: Any = None            # utils.win_window.ForegroundTracker
    tts: Any = None                # voice.text_to_speech.TextToSpeech
    state: Any = None              # core.state_manager.StateManager
    assistant: Any = None          # core.assistant.Assistant (set after wiring)
    memory: Dict[str, Any] = field(default_factory=dict)


class CommandRouter:
    """Maps intent names to handlers and executes them safely."""

    def __init__(self, context: ActionContext) -> None:
        self.context = context
        self.safety = context.safety
        self._handlers: Dict[str, Handler] = {}
        self._descriptions: Dict[str, str] = {}

    # ------------------------------------------------------------ registration
    def register(self, intent: str, handler: Handler, description: str = "") -> None:
        if intent in self._handlers:
            log.debug("Replacing handler for %s", intent)
        self._handlers[intent] = handler
        self._descriptions[intent] = description
        log.debug("Registered handler: %s", intent)

    def register_many(self, mapping: Dict[str, Handler]) -> None:
        for intent, handler in mapping.items():
            self.register(intent, handler)

    def has(self, intent: str) -> bool:
        return intent in self._handlers

    @property
    def intents(self) -> List[str]:
        return sorted(self._handlers)

    def load_plugins(self, package: str = "actions") -> int:
        """Import every module in ``actions/`` and call its ``register()``."""
        loaded = 0
        try:
            module = importlib.import_module(package)
        except ImportError as exc:
            log.error("Cannot import action package %s: %s", package, exc)
            return 0

        for info in pkgutil.iter_modules(module.__path__):
            if info.name.startswith("_"):
                continue
            full_name = f"{package}.{info.name}"
            try:
                plugin = importlib.import_module(full_name)
                register = getattr(plugin, "register", None)
                if callable(register):
                    register(self, self.context)
                    loaded += 1
                else:
                    log.debug("%s has no register(); skipped", full_name)
            except Exception as exc:                            # noqa: BLE001
                log.error("Failed to load %s: %s", full_name, exc)
        log.info("Loaded %d action modules (%d intents)", loaded, len(self._handlers))
        return loaded

    # ---------------------------------------------------------------- execute
    def execute(self, action: Action, confirmed: bool = False) -> ActionResult:
        """Validate then run a single action. Never raises."""
        allowed, reason = self.safety.validate(action)
        if not allowed:
            log.warning("Rejected %s: %s", action.intent, reason)
            return ActionResult.fail(reason)

        if not confirmed and self.safety.needs_confirmation(action):
            question = self.safety.confirmation_question(action)
            log.info("Confirmation required for %s", action.intent)
            return ActionResult.confirm(question, action)

        handler = self._handlers.get(action.intent)
        if handler is None:
            log.error("No handler registered for %s", action.intent)
            return ActionResult.fail("I don't know how to do that yet.")

        try:
            result = handler(action)
        except Exception as exc:                                # noqa: BLE001
            log.exception("Handler for %s crashed", action.intent)
            return ActionResult.fail(
                "Something went wrong while running that.", detail=str(exc)
            )

        if result is None:
            return ActionResult.ok()
        log.info(
            "Executed %s -> %s", action.intent, "ok" if result.success else "failed"
        )
        return result

    def execute_all(self, actions: List[Action]) -> List[ActionResult]:
        """Run a chain ("type X, press Tab, type Y"), stopping on first failure."""
        results: List[ActionResult] = []
        for action in actions:
            result = self.execute(action)
            results.append(result)
            if result.needs_confirmation or not result.success:
                break
        return results

    def describe(self) -> Dict[str, str]:
        return dict(self._descriptions)
