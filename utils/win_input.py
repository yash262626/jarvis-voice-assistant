"""Windows keyboard injection via the Win32 ``SendInput`` API.

Why not pyautogui: pyautogui maps characters to virtual-key codes, which breaks
on non-US layouts and on symbols, and it cannot type a character the current
keyboard layout has no key for. ``KEYEVENTF_UNICODE`` injects the character
itself, so "29AAFCJ4954L1ZY" or "₹" land correctly in Excel, a browser field,
SAP, WhatsApp - anything that accepts normal keyboard input.

Every function is a no-op that raises :class:`InputError` on non-Windows, so
the module can still be imported (and mocked) by the unit tests on any OS.
"""

from __future__ import annotations

import ctypes
import sys
import time
from typing import Iterable, List, Optional, Sequence

IS_WINDOWS = sys.platform == "win32"


class InputError(RuntimeError):
    """Raised when input injection is unavailable or rejected by Windows."""


# --------------------------------------------------------------------------
# Virtual key codes (plain ints so the table is importable everywhere)
# --------------------------------------------------------------------------
VK: dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "clear": 0x0C, "enter": 0x0D, "return": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12, "menu": 0x12,
    "pause": 0x13, "capslock": 0x14, "escape": 0x1B, "esc": 0x1B, "space": 0x20,
    "spacebar": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "select": 0x29, "print": 0x2A, "printscreen": 0x2C, "insert": 0x2D,
    "delete": 0x2E, "del": 0x2E, "help": 0x2F,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46, "g": 0x47,
    "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E,
    "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54, "u": 0x55,
    "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A,
    "win": 0x5B, "windows": 0x5B, "leftwin": 0x5B, "rightwin": 0x5C, "apps": 0x5D,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69, "multiply": 0x6A, "add": 0x6B,
    "subtract": 0x6D, "decimal": 0x6E, "divide": 0x6F,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "numlock": 0x90, "scrolllock": 0x91,
    "volumemute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF,
    "medianext": 0xB0, "mediaprev": 0xB1, "mediastop": 0xB2, "mediaplay": 0xB3,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}

# Keys that need the extended-key flag to behave correctly in every app.
_EXTENDED = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C,
    0x5D, 0x6F, 0x90, 0xAD, 0xAE, 0xAF,
}

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

if IS_WINDOWS:  # pragma: no cover - Windows only
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
else:  # pragma: no cover - non Windows import shim
    user32 = None
    kernel32 = None
    INPUT = None  # type: ignore[assignment]


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise InputError("Keyboard injection requires Windows")


def _key_event(vk: int = 0, scan: int = 0, flags: int = 0):  # pragma: no cover
    ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    return INPUT(type=INPUT_KEYBOARD, ki=ki)


def _send(events: Sequence) -> int:  # pragma: no cover - Windows only
    if not events:
        return 0
    array = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    if sent != len(events):
        raise InputError(
            f"SendInput delivered {sent}/{len(events)} events "
            f"(win32 error {ctypes.get_last_error()}). "
            "If the target app runs as administrator, run JARVIS as administrator too."
        )
    return sent


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def resolve_key(name: str) -> int:
    """Map a spoken/typed key name to a virtual key code."""
    key = str(name).strip().lower().replace(" ", "")
    key = {
        "arrowup": "up", "arrowdown": "down", "arrowleft": "left",
        "arrowright": "right", "uparrow": "up", "downarrow": "down",
        "leftarrow": "left", "rightarrow": "right", "returnkey": "enter",
        "enterkey": "enter", "esckey": "esc", "pgup": "pageup",
        "pgdown": "pagedown", "pagedn": "pagedown",
    }.get(key, key)
    if key not in VK:
        raise InputError(f"Unknown key: {name}")
    return VK[key]


def type_unicode(text: str, interval: float = 0.01) -> int:
    """Type ``text`` into whatever window currently has keyboard focus.

    Returns the number of characters sent. Newlines are sent as real ENTER
    presses so they work in Excel, chat apps and multi-line fields alike.
    """
    _require_windows()
    if not text:
        return 0

    typed = 0
    for char in text:
        if char == "\n":
            press_key(VK["enter"])
        elif char == "\t":
            press_key(VK["tab"])
        elif char == "\r":
            continue
        else:
            code = ord(char)
            if code > 0xFFFF:  # emoji / astral plane -> UTF-16 surrogate pair
                code -= 0x10000
                units = [0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)]
            else:
                units = [code]
            events = []
            for unit in units:
                events.append(_key_event(scan=unit, flags=KEYEVENTF_UNICODE))
                events.append(
                    _key_event(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
                )
            _send(events)
        typed += 1
        if interval > 0:
            time.sleep(interval)
    return typed


def press_key(key: int | str, presses: int = 1, interval: float = 0.04) -> None:
    """Press and release a single key ``presses`` times."""
    _require_windows()
    vk = key if isinstance(key, int) else resolve_key(key)
    flags = KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0
    for index in range(max(1, presses)):
        _send([
            _key_event(vk=vk, flags=flags),
            _key_event(vk=vk, flags=flags | KEYEVENTF_KEYUP),
        ])
        if index < presses - 1:
            time.sleep(interval)


def hotkey(*keys: int | str) -> None:
    """Press a combination such as ``hotkey('ctrl', 'c')`` (order = press order)."""
    _require_windows()
    codes: List[int] = [k if isinstance(k, int) else resolve_key(k) for k in keys]
    events = []
    for vk in codes:
        flags = KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0
        events.append(_key_event(vk=vk, flags=flags))
    for vk in reversed(codes):
        flags = KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0
        events.append(_key_event(vk=vk, flags=flags | KEYEVENTF_KEYUP))
    _send(events)


# --------------------------------------------------------------------------
# Clipboard (used by the fast paste typing strategy)
# --------------------------------------------------------------------------
def get_clipboard_text() -> Optional[str]:
    """Return clipboard text, or None when empty/unavailable."""
    _require_windows()
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                kernel32.GlobalLock.restype = ctypes.c_void_p
                pointer = kernel32.GlobalLock(ctypes.c_void_p(handle))
                if not pointer:
                    return None
                try:
                    return ctypes.c_wchar_p(pointer).value
                finally:
                    kernel32.GlobalUnlock(ctypes.c_void_p(handle))
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return None


def set_clipboard_text(text: str) -> bool:
    """Put ``text`` on the clipboard. Returns True on success."""
    _require_windows()
    data = str(text)
    size = (len(data) + 1) * ctypes.sizeof(ctypes.c_wchar)
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                kernel32.GlobalAlloc.restype = ctypes.c_void_p
                handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
                if not handle:
                    return False
                kernel32.GlobalLock.restype = ctypes.c_void_p
                pointer = kernel32.GlobalLock(ctypes.c_void_p(handle))
                if not pointer:
                    return False
                ctypes.memmove(pointer, ctypes.create_unicode_buffer(data), size)
                kernel32.GlobalUnlock(ctypes.c_void_p(handle))
                if not user32.SetClipboardData(CF_UNICODETEXT, ctypes.c_void_p(handle)):
                    return False
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return False


def paste_text(text: str, restore: bool = True, delay: float = 0.12) -> bool:
    """Type long text instantly by pasting it, then restore the old clipboard."""
    _require_windows()
    previous = get_clipboard_text() if restore else None
    if not set_clipboard_text(text):
        return False
    time.sleep(0.05)
    hotkey("ctrl", "v")
    time.sleep(delay)
    if restore and previous is not None:
        set_clipboard_text(previous)
    return True


def available() -> bool:
    """True when real input injection can be used on this machine."""
    return IS_WINDOWS
