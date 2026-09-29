"""Global hotkey listener (default Ctrl+Alt+J) as a wake-word backup.

Uses RegisterHotKey + its own message loop in a dedicated thread, so it works
even when JARVIS is minimised to the tray and never needs admin rights.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable, Optional

from utils.logger import get_logger

IS_WINDOWS = sys.platform == "win32"
log = get_logger("utils.hotkey")

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODIFIERS = {
    "alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "shift": MOD_SHIFT, "win": MOD_WIN, "windows": MOD_WIN,
}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'ctrl+alt+j' -> (modifier mask, virtual key code)."""
    from utils.win_input import VK

    modifiers = 0
    key = 0
    for part in str(spec).lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        elif part in VK:
            key = VK[part]
    if not key:
        raise ValueError(f"Invalid hotkey: {spec}")
    return modifiers | MOD_NOREPEAT, key


class GlobalHotkey:
    """Fires ``callback`` (on its own thread) whenever the hotkey is pressed."""

    def __init__(self, spec: str, callback: Callable[[], None]) -> None:
        self.spec = spec
        self.callback = callback
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False

    def start(self) -> bool:
        if not IS_WINDOWS or self._running:
            return False
        try:
            parse_hotkey(self.spec)
        except ValueError as exc:
            log.warning("%s", exc)
            return False
        self._thread = threading.Thread(target=self._run, name="hotkey", daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:  # pragma: no cover - Windows only
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread_id = kernel32.GetCurrentThreadId()

        modifiers, key = parse_hotkey(self.spec)
        if not user32.RegisterHotKey(None, 1, modifiers, key):
            log.warning("Could not register hotkey %s (already in use?)", self.spec)
            return
        self._running = True
        log.info("Global hotkey registered: %s", self.spec)

        try:
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception as exc:                    # noqa: BLE001
                        log.error("Hotkey callback failed: %s", exc)
        finally:
            user32.UnregisterHotKey(None, 1)
            self._running = False

    def stop(self) -> None:  # pragma: no cover - Windows only
        if not IS_WINDOWS or not self._thread_id:
            return
        try:
            import ctypes

            ctypes.WinDLL("user32").PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        except Exception:                                       # noqa: BLE001
            pass
