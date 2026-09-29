"""Foreground-window tracking and focus restoration.

The whole point: when you say "type Anand Trading Company", the text must land
in *Excel*, not in the JARVIS window. A background thread remembers the last
foreground window that did not belong to JARVIS, and :meth:`ForegroundTracker.
ensure_target` puts it back in front (only if JARVIS somehow stole focus)
before any typing happens.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

from utils.logger import get_logger

IS_WINDOWS = sys.platform == "win32"
log = get_logger("utils.window")

if IS_WINDOWS:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SW_RESTORE = 9
else:  # pragma: no cover
    user32 = None
    kernel32 = None


@dataclass
class WindowInfo:
    """A snapshot of a window we may need to type into later."""

    hwnd: int = 0
    title: str = ""
    process: str = ""

    def __bool__(self) -> bool:
        return bool(self.hwnd)

    def describe(self) -> str:
        if not self.hwnd:
            return "unknown window"
        name = self.process or "application"
        return f"{name} ({self.title[:40]})" if self.title else name


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------
def get_foreground_hwnd() -> int:
    if not IS_WINDOWS:
        return 0
    try:
        return int(user32.GetForegroundWindow() or 0)
    except Exception:                                           # noqa: BLE001
        return 0


def get_window_title(hwnd: int) -> str:
    if not IS_WINDOWS or not hwnd:
        return ""
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value
    except Exception:                                           # noqa: BLE001
        return ""


def get_window_pid(hwnd: int) -> int:
    if not IS_WINDOWS or not hwnd:
        return 0
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:                                           # noqa: BLE001
        return 0


def get_process_name(pid: int) -> str:
    if not IS_WINDOWS or not pid:
        return ""
    handle = None
    try:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value)
    except Exception:                                           # noqa: BLE001
        return ""
    finally:
        if handle:
            kernel32.CloseHandle(handle)
    return ""


def is_own_window(hwnd: int) -> bool:
    """True when the window belongs to the JARVIS process itself."""
    return bool(hwnd) and get_window_pid(hwnd) == os.getpid()


def describe_window(hwnd: int) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        title=get_window_title(hwnd),
        process=get_process_name(get_window_pid(hwnd)),
    )


def get_active_window() -> WindowInfo:
    return describe_window(get_foreground_hwnd())


def force_foreground(hwnd: int) -> bool:
    """Bring ``hwnd`` to the front, working around Win32 focus-stealing rules."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        if not user32.IsWindow(hwnd):
            return False
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05)

        current = user32.GetForegroundWindow()
        if current == hwnd:
            return True

        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()
        attached = False
        if target_thread and target_thread != current_thread:
            attached = bool(user32.AttachThreadInput(current_thread, target_thread, True))
        try:
            ok = bool(user32.SetForegroundWindow(hwnd))
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, target_thread, False)
        return ok
    except Exception as exc:                                    # noqa: BLE001
        log.debug("force_foreground failed: %s", exc)
        return False


# --------------------------------------------------------------------------
# Tracker
# --------------------------------------------------------------------------
class ForegroundTracker:
    """Polls the foreground window and remembers the last non-JARVIS one."""

    def __init__(self, poll_interval: float = 0.25) -> None:
        self.poll_interval = poll_interval
        self._target = WindowInfo()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if not IS_WINDOWS or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="foreground-tracker", daemon=True
        )
        self._thread.start()
        log.debug("Foreground tracker started")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                hwnd = get_foreground_hwnd()
                if hwnd and not is_own_window(hwnd):
                    with self._lock:
                        if hwnd != self._target.hwnd:
                            self._target = describe_window(hwnd)
            except Exception:                                   # noqa: BLE001
                pass
            self._stop.wait(self.poll_interval)

    # ------------------------------------------------------------------ API
    @property
    def target(self) -> WindowInfo:
        with self._lock:
            return self._target

    def ensure_target(self, delay: float = 0.12) -> WindowInfo:
        """Make sure the user's application - not JARVIS - has keyboard focus.

        Returns the window that will receive the keystrokes.
        """
        if not IS_WINDOWS:
            return WindowInfo()

        current = get_foreground_hwnd()
        if current and not is_own_window(current):
            # The user's app is already focused: touch nothing.
            with self._lock:
                if current != self._target.hwnd:
                    self._target = describe_window(current)
                return self._target

        target = self.target
        if target.hwnd and force_foreground(target.hwnd):
            time.sleep(max(0.0, delay))
            return target
        return target
