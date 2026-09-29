"""Thread-safe assistant state machine with change notifications."""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable, List, Optional

from utils.logger import get_logger

log = get_logger("core.state")


class State(str, Enum):
    SLEEPING = "SLEEPING"
    LISTENING = "LISTENING"
    ACTIVATED = "ACTIVATED"
    PROCESSING = "PROCESSING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    DICTATING = "DICTATING"
    CONFIRMING = "CONFIRMING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"

    def __str__(self) -> str:
        return self.value


class StateManager:
    """Holds the current state and notifies listeners (the GUI) when it changes."""

    def __init__(self, initial: State = State.SLEEPING) -> None:
        self._state = initial
        self._previous = initial
        self._changed_at = time.time()
        self._lock = threading.RLock()
        self._listeners: List[Callable[[State, State], None]] = []

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    @property
    def previous(self) -> State:
        with self._lock:
            return self._previous

    @property
    def seconds_in_state(self) -> float:
        with self._lock:
            return time.time() - self._changed_at

    def set(self, state: State) -> None:
        with self._lock:
            if state == self._state:
                return
            self._previous, self._state = self._state, state
            self._changed_at = time.time()
            old = self._previous
        log.debug("State %s -> %s", old, state)
        for listener in list(self._listeners):
            try:
                listener(old, state)
            except Exception as exc:                             # noqa: BLE001
                log.error("State listener failed: %s", exc)

    def is_(self, *states: State) -> bool:
        return self.state in states

    def on_change(self, callback: Callable[[State, State], None]) -> None:
        self._listeners.append(callback)

    def revert(self) -> None:
        self.set(self.previous)
