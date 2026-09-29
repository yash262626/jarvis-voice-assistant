"""Wake-word detection for "Hey Jarvis".

Primary engine is **openWakeWord**, which ships a pre-trained ``hey_jarvis``
model - no training, no licence key, and the audio never leaves the machine.

If the model or its runtime is unavailable, JARVIS degrades instead of dying:

``openwakeword`` -> ``stt`` (short local transcriptions scanned for the phrase)
-> ``hotkey`` (Ctrl+Alt+J only).

Detection is suppressed while JARVIS is speaking so its own voice through the
speakers cannot re-trigger it.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional

from utils.config import Config
from utils.logger import get_logger
from voice.microphone import Microphone

log = get_logger("voice.wake")

MODEL_NAME = "hey_jarvis"
_REFRACTORY_SECONDS = 2.0      # ignore repeat triggers right after a detection


class WakeWordDetector:
    """Runs in its own thread and calls ``on_wake()`` when the phrase is heard."""

    def __init__(
        self,
        microphone: Microphone,
        config: Optional[Config] = None,
        on_wake: Optional[Callable[[], None]] = None,
        transcriber: Optional[Callable[[bytes], str]] = None,
    ) -> None:
        self.microphone = microphone
        self.config = config or Config()
        self.on_wake = on_wake or (lambda: None)
        self.transcriber = transcriber          # used by the "stt" fallback engine

        self.engine = "none"
        self._model = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._muted = threading.Event()
        self._last_fired = 0.0
        self.last_score = 0.0

    # ------------------------------------------------------------- engine set-up
    def _load_openwakeword(self) -> bool:
        try:
            import numpy as np                                   # noqa: F401,PLC0415
            from openwakeword.model import Model                 # noqa: PLC0415
        except ImportError as exc:
            log.warning("openWakeWord unavailable (%s)", exc)
            return False

        try:
            self._model = Model(wakeword_models=[MODEL_NAME], inference_framework="onnx")
        except Exception as exc:                                # noqa: BLE001
            log.warning("Wake-word model missing (%s). Attempting download...", exc)
            try:
                import openwakeword                              # noqa: PLC0415

                openwakeword.utils.download_models([MODEL_NAME])
                from openwakeword.model import Model as ReloadedModel  # noqa: PLC0415

                self._model = ReloadedModel(
                    wakeword_models=[MODEL_NAME], inference_framework="onnx"
                )
            except Exception as exc2:                           # noqa: BLE001
                log.error("Could not load the wake-word model: %s", exc2)
                return False

        log.info("Wake word engine: openWakeWord (%s)", MODEL_NAME)
        return True

    def _select_engine(self) -> str:
        preference = str(self.config.get("wake_word_engine", "auto")).lower()
        if preference in {"off", "hotkey"}:
            return preference
        if preference in {"auto", "openwakeword"} and self._load_openwakeword():
            return "openwakeword"
        if preference == "openwakeword":
            log.warning("Falling back from openWakeWord to the STT wake engine")
        if self.transcriber is not None:
            log.info("Wake word engine: STT polling")
            return "stt"
        log.warning("No wake-word engine available - use the hotkey instead")
        return "hotkey"

    # -------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        self.engine = self._select_engine()
        if self.engine in {"off", "hotkey"}:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="wake-word", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def mute(self) -> None:
        """Suspend detection (used while JARVIS speaks or handles a command)."""
        self._muted.set()

    def unmute(self) -> None:
        self._reset_model()
        self._muted.clear()

    @property
    def muted(self) -> bool:
        return self._muted.is_set()

    def _reset_model(self) -> None:
        if self._model is not None:
            try:
                self._model.reset()
            except Exception:                                   # noqa: BLE001
                pass

    # ------------------------------------------------------------------- loop
    def _run(self) -> None:
        if self.engine == "openwakeword":
            self._run_openwakeword()
        else:
            self._run_stt()

    def _fire(self, score: float) -> None:
        now = time.time()
        if now - self._last_fired < _REFRACTORY_SECONDS:
            return
        self._last_fired = now
        self.last_score = score
        log.info("Wake word detected (score %.2f)", score)
        try:
            self.on_wake()
        except Exception as exc:                                # noqa: BLE001
            log.error("Wake callback failed: %s", exc)

    def _run_openwakeword(self) -> None:  # pragma: no cover - needs audio
        import numpy as np

        threshold = float(self.config.get("wake_word_threshold", 0.5) or 0.5)
        sink = self.microphone.subscribe()
        log.info("Listening for '%s'", self.config.get("wake_word", "hey jarvis"))
        try:
            while not self._stop.is_set():
                try:
                    block = sink.get(timeout=1.0)
                except queue.Empty:
                    continue
                if self._muted.is_set():
                    continue
                try:
                    samples = np.frombuffer(block, dtype=np.int16)
                    scores = self._model.predict(samples)
                    score = max(scores.values()) if scores else 0.0
                    self.last_score = score
                    if score >= threshold:
                        self._reset_model()
                        self._fire(score)
                except Exception as exc:                        # noqa: BLE001
                    log.debug("Wake inference error: %s", exc)
                    time.sleep(0.1)
        finally:
            self.microphone.unsubscribe(sink)

    def _run_stt(self) -> None:  # pragma: no cover - needs audio
        """Fallback: transcribe short windows and look for the phrase."""
        wake = str(self.config.get("wake_word", "hey jarvis")).lower()
        needles = {wake, wake.replace("hey ", ""), "hey jarvis", "jarvis", "hey travis",
                   "hey service", "hey charvis"}
        log.info("Listening for '%s' via short transcriptions", wake)
        while not self._stop.is_set():
            if self._muted.is_set():
                time.sleep(0.2)
                continue
            audio, heard = self.microphone.record_command(
                start_timeout=1.0, max_seconds=2.5, silence_duration=0.5
            )
            if not heard or self._muted.is_set():
                continue
            try:
                text = (self.transcriber(audio) or "").lower()
            except Exception as exc:                            # noqa: BLE001
                log.debug("Wake transcription failed: %s", exc)
                continue
            if any(needle in text for needle in needles if needle):
                self._fire(1.0)
