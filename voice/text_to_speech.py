"""Speech synthesis through Windows SAPI5 (pyttsx3).

pyttsx3's engine is not thread-safe and its run loop cannot be re-entered, so
the engine lives in one dedicated worker thread fed by a queue. Callers just
call :meth:`speak` from anywhere.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, List, Optional

from utils.config import Config
from utils.logger import get_logger

log = get_logger("voice.tts")

_STOP = object()


class TextToSpeech:
    """Queued, non-blocking text to speech with a graceful silent fallback."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self._queue: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._engine = None
        self._speaking = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self.available = False
        self.on_speak: Optional[Callable[[str], None]] = None

    # -------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return self.available
        self._thread = threading.Thread(target=self._run, name="tts", daemon=True)
        self._thread.start()
        for _ in range(60):                     # wait up to ~3s for engine init
            if self.available or not self._thread.is_alive():
                break
            time.sleep(0.05)
        return self.available

    def stop(self) -> None:
        self._queue.put(_STOP)

    # ----------------------------------------------------------------- worker
    def _init_engine(self):
        import pyttsx3                                           # noqa: PLC0415

        engine = pyttsx3.init()
        self._apply_settings(engine)
        return engine

    def _apply_settings(self, engine) -> None:
        try:
            engine.setProperty("rate", int(self.config.get("tts_rate", 175) or 175))
            volume = float(self.config.get("tts_volume", 1.0) or 1.0)
            engine.setProperty("volume", max(0.0, min(1.0, volume)))
            wanted = str(self.config.get("tts_voice", "") or "").strip().lower()
            if wanted:
                for voice in engine.getProperty("voices"):
                    if wanted in voice.name.lower() or wanted in str(voice.id).lower():
                        engine.setProperty("voice", voice.id)
                        break
        except Exception as exc:                                # noqa: BLE001
            log.warning("Could not apply TTS settings: %s", exc)

    def _run(self) -> None:
        try:
            self._engine = self._init_engine()
            self.available = True
            log.info("Text to speech ready")
        except Exception as exc:                                # noqa: BLE001
            log.error("Text to speech unavailable (%s). JARVIS will stay silent.", exc)
            self.available = False

        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            text = str(item).strip()
            if not text:
                continue
            self._speaking.set()
            self._idle.clear()
            if self.on_speak:
                try:
                    self.on_speak(text)
                except Exception:                               # noqa: BLE001
                    pass
            try:
                if self.available and self._engine is not None:
                    self._engine.say(text)
                    self._engine.runAndWait()
                else:
                    time.sleep(min(3.0, 0.06 * len(text)))       # keep timing sane
            except Exception as exc:                            # noqa: BLE001
                log.warning("Speech failed: %s", exc)
                self._recover()
            finally:
                self._speaking.clear()
                if self._queue.empty():
                    self._idle.set()

        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:                                       # noqa: BLE001
            pass

    def _recover(self) -> None:
        """Rebuild the SAPI engine after a COM hiccup."""
        try:
            self._engine = self._init_engine()
            self.available = True
        except Exception:                                       # noqa: BLE001
            self.available = False

    # -------------------------------------------------------------------- API
    def speak(self, text: str, block: bool = False, timeout: float = 20.0) -> None:
        """Queue text for speaking. Never raises, never blocks by default."""
        if not text or not str(text).strip():
            return
        if not self.config.get("tts_enabled", True):
            if self.on_speak:
                try:
                    self.on_speak(str(text))
                except Exception:                               # noqa: BLE001
                    pass
            return
        if self._thread is None or not self._thread.is_alive():
            self.start()
        self._idle.clear()
        self._queue.put(str(text))
        if block:
            self.wait(timeout)

    def wait(self, timeout: float = 20.0) -> None:
        """Block until the queue has drained (used before listening again)."""
        self._idle.wait(timeout=timeout)

    @property
    def speaking(self) -> bool:
        return self._speaking.is_set() or not self._queue.empty()

    def reload_settings(self) -> None:
        if self._engine is not None:
            self._apply_settings(self._engine)

    def list_voices(self) -> List[str]:
        try:
            import pyttsx3                                       # noqa: PLC0415

            engine = self._engine or pyttsx3.init()
            return [voice.name for voice in engine.getProperty("voices")]
        except Exception as exc:                                # noqa: BLE001
            log.warning("Could not list voices: %s", exc)
            return []
