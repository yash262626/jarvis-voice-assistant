"""Small shared helpers: URL building, application discovery, misc utilities."""

from __future__ import annotations

import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import quote_plus

from utils.logger import get_logger

log = get_logger("utils.helpers")

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
}

_DOMAIN_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?"
    r"([a-z0-9][a-z0-9\-]{0,62}(?:\.[a-z0-9][a-z0-9\-]{0,62})+)"
    r"(/[^\s]*)?$",
    re.IGNORECASE,
)


def build_search_url(query: str, engine: str = "google") -> str:
    """Percent-encode ``query`` into a search URL - never string-concatenated."""
    template = SEARCH_ENGINES.get(str(engine).lower(), SEARCH_ENGINES["google"])
    return template.format(q=quote_plus(query.strip()))


def build_youtube_search_url(query: str) -> str:
    return build_search_url(query, "youtube")


def normalise_url(text: str) -> Optional[str]:
    """Turn 'github.com' or 'go to kei-ind.com/products' into a real https URL."""
    candidate = str(text).strip().strip(".,")
    candidate = candidate.replace(" dot ", ".").replace(" slash ", "/")
    candidate = re.sub(r"\s+", "", candidate)
    if not candidate:
        return None
    match = _DOMAIN_RE.match(candidate)
    if not match:
        return None
    if candidate.lower().startswith(("http://", "https://")):
        return candidate
    return "https://" + candidate


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", strip_accents(text).lower()).strip("_")


# --------------------------------------------------------------------------
# Application discovery
# --------------------------------------------------------------------------
def _registry_app_path(executable: str) -> Optional[str]:
    """Look the exe up in HKLM/HKCU App Paths (how the Run dialog finds apps)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable}"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for flag in (0, getattr(winreg, "KEY_WOW64_32KEY", 0)):
            try:
                with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ | flag) as key:
                    value, _ = winreg.QueryValueEx(key, "")
                    value = str(value).strip('"')
                    if value and Path(value).exists():
                        return value
            except OSError:
                continue
    return None


def _start_menu_shortcut(name: str) -> Optional[str]:
    """Search the Start Menu for a matching .lnk - catches oddly installed apps."""
    if sys.platform != "win32":
        return None
    roots = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    wanted = slugify(name)
    if not wanted:
        return None
    for root in roots:
        if not root.exists():
            continue
        try:
            for shortcut in root.rglob("*.lnk"):
                if wanted in slugify(shortcut.stem):
                    return str(shortcut)
        except OSError:
            continue
    return None


def find_executable(candidates: Iterable[str], display_name: str = "") -> Optional[str]:
    """Resolve an application to something Windows can actually launch.

    Tries, in order: literal path -> PATH lookup -> App Paths registry ->
    Start Menu shortcut. Protocol handlers (``ms-settings:``) pass straight
    through.
    """
    candidates = [c for c in candidates if c]
    for candidate in candidates:
        if ":" in candidate and not Path(candidate).drive and candidate.endswith(":"):
            return candidate                      # protocol handler, e.g. ms-settings:
        path = Path(os.path.expandvars(candidate))
        if path.is_absolute() and path.exists():
            return str(path)

    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found

    for candidate in candidates:
        exe = Path(candidate).name
        found = _registry_app_path(exe)
        if found:
            return found

    for name in ([display_name] if display_name else []) + [Path(c).stem for c in candidates]:
        found = _start_menu_shortcut(name)
        if found:
            return found
    return None


# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------
def user_folder(name: str) -> Optional[Path]:
    """Resolve 'downloads', 'desktop', 'documents'... to a real path."""
    home = Path.home()
    mapping = {
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "download": home / "Downloads",
        "documents": home / "Documents",
        "document": home / "Documents",
        "pictures": home / "Pictures",
        "music": home / "Music",
        "videos": home / "Videos",
        "home": home,
        "user folder": home,
        "recycle bin": Path("shell:RecycleBinFolder"),
    }
    key = str(name).strip().lower()
    path = mapping.get(key)
    if path is None:
        return None
    if sys.platform == "win32" and key not in {"recycle bin"}:
        try:
            import ctypes
            from ctypes import wintypes

            folder_ids = {
                "desktop": 0x0000, "documents": 0x0005, "document": 0x0005,
                "music": 0x000D, "videos": 0x000E, "pictures": 0x0027,
            }
            if key in folder_ids:
                buffer = ctypes.create_unicode_buffer(260)
                if ctypes.windll.shell32.SHGetFolderPathW(
                    None, folder_ids[key], None, 0, buffer
                ) == 0 and buffer.value:
                    return Path(buffer.value)
        except Exception:                                       # noqa: BLE001
            pass
    return path


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def truncate(text: str, limit: int = 80) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


class SingleInstance:
    """Named-mutex guard so two JARVIS copies never fight over the microphone."""

    def __init__(self, name: str = "JarvisVoiceAssistantMutex") -> None:
        self.name = name
        self._handle = None
        self.already_running = False
        if sys.platform == "win32":
            try:
                import ctypes

                self._handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
                self.already_running = ctypes.windll.kernel32.GetLastError() == 183
            except Exception:                                   # noqa: BLE001
                self.already_running = False

    def release(self) -> None:
        if self._handle and sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.kernel32.ReleaseMutex(self._handle)
                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:                                   # noqa: BLE001
                pass
            self._handle = None
