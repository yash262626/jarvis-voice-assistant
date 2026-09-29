"""'Start JARVIS with Windows' toggle.

Implemented with a shortcut-free registry Run entry under HKEY_CURRENT_USER,
so it needs no admin rights and is trivially reversible.
"""

from __future__ import annotations

import sys
from pathlib import Path

from utils.config import project_root
from utils.logger import get_logger

log = get_logger("utils.startup")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "JARVIS Voice Assistant"


def _command() -> str:
    """Command Windows should run at login."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    main = project_root() / "main.py"
    return f'"{interpreter}" "{main}" --minimized'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except (ImportError, OSError):
        return False


def set_enabled(enabled: bool) -> bool:
    """Add or remove the login entry. Returns True when the change applied."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
                log.info("Enabled start with Windows")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    log.info("Disabled start with Windows")
                except FileNotFoundError:
                    pass
        return True
    except (ImportError, OSError) as exc:
        log.error("Could not update startup entry: %s", exc)
        return False
