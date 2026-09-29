"""Configuration management for JARVIS.

Loads ``config/config.json`` (plus optional ``config/config.local.json`` for
machine specific overrides that are gitignored), merges it over a set of
built-in defaults, and exposes dotted-path get/set helpers.

Nothing in the application reads the JSON file directly - everything goes
through :class:`Config` so a missing or corrupt file never crashes JARVIS.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List

# Defaults are the single source of truth. config.json only overrides them,
# so an old config file never breaks a newer build.
DEFAULTS: Dict[str, Any] = {
    "assistant_name": "Jarvis",
    "wake_word": "hey jarvis",
    "wake_word_engine": "auto",          # auto | openwakeword | stt | hotkey | off
    "wake_word_threshold": 0.5,
    "wake_hotkey": "ctrl+alt+j",
    "language": "en-IN",

    "stt_engine": "auto",                # auto | whisper | vosk | google
    "whisper_model": "base.en",
    "whisper_compute_type": "int8",
    "whisper_beam_size": 1,
    "vosk_model_path": "",

    "tts_enabled": True,
    "tts_voice": "",
    "tts_rate": 175,
    "tts_volume": 1.0,

    "default_search_engine": "google",
    "browser": "default",

    "active_timeout": 8,
    "follow_up_enabled": True,

    "typing_interval": 0.01,
    "typing_method": "auto",             # auto | sendinput | clipboard | pyautogui
    "clipboard_threshold": 200,
    "restore_clipboard": True,
    "focus_restore_delay": 0.12,
    "auto_punctuation": True,
    "uppercase_alphanumeric_codes": True,
    "normalize_spelled_codes": True,

    "require_confirmation_for_dangerous_actions": True,
    "allow_file_operations": True,
    "sandbox_file_operations": True,

    "start_with_windows": False,
    "start_minimized": True,
    "gui_never_steals_focus": True,
    "play_sounds": True,

    "mic_device": None,
    "mic_sample_rate": 16000,
    "silence_threshold": 0,              # 0 = auto calibrate from room noise
    "silence_duration": 1.0,
    "command_start_timeout": 5.0,
    "command_max_seconds": 15.0,

    "log_level": "INFO",
    "log_typed_text": False,
    "log_retention_days": 14,

    "llm_enabled": False,
    "llm_provider": "anthropic",
    "llm_model": "claude-sonnet-4-6",
    "llm_timeout": 12,
}


def project_root() -> Path:
    """Directory that holds config/, logs/ ... works from source and from the .exe."""
    import sys

    if getattr(sys, "frozen", False):          # PyInstaller one-file / one-dir
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class Config:
    """Thread-safe settings store backed by a JSON file."""

    def __init__(self, path: str | os.PathLike | None = None) -> None:
        root = project_root()
        self.path = Path(path) if path else root / "config" / "config.json"
        self.local_path = self.path.with_name("config.local.json")
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self._listeners: List[Any] = []
        self.load()

    # ------------------------------------------------------------------ load
    def load(self) -> None:
        with self._lock:
            self._data = dict(DEFAULTS)
            for candidate in (self.path, self.local_path):
                self._data.update(self._read_json(candidate))

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            # A broken config must never stop JARVIS from starting.
            pass
        return {}

    # ------------------------------------------------------------- accessors
    def get(self, key: str, default: Any = None) -> Any:
        """Read a setting. Supports dotted paths for nested dicts."""
        with self._lock:
            node: Any = self._data
            for part in key.split("."):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    return DEFAULTS.get(key, default)
            return node

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def set(self, key: str, value: Any, save: bool = False) -> None:
        with self._lock:
            parts = key.split(".")
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        for callback in list(self._listeners):
            try:
                callback(key, value)
            except Exception:                                  # noqa: BLE001
                pass
        if save:
            self.save()

    def update(self, values: Dict[str, Any], save: bool = True) -> None:
        for key, value in values.items():
            self.set(key, value)
        if save:
            self.save()

    def as_dict(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def on_change(self, callback) -> None:
        self._listeners.append(callback)

    # ----------------------------------------------------------------- write
    def save(self) -> bool:
        """Write settings back to disk atomically. Returns True on success."""
        with self._lock:
            payload = json.dumps(self._data, indent=2, ensure_ascii=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            shutil.move(str(tmp), str(self.path))
            return True
        except OSError:
            return False


def load_json_asset(name: str, fallback: Any = None) -> Any:
    """Load a JSON file from the config/ folder (applications, websites...)."""
    path = project_root() / "config" / name
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return fallback if fallback is not None else {}


def iter_config_keys() -> Iterable[str]:
    return DEFAULTS.keys()
