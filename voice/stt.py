"""Speech recognition.

Three interchangeable engines behind one interface:

* ``whisper`` - faster-whisper, fully offline, best accuracy on business
  identifiers like RP0002442. This is the default.
* ``vosk``    - offline, very light on CPU, needs a downloaded model folder.
* ``google``  - SpeechRecognition's free web endpoint. No API key, but it
  needs internet and sends the clip to Google, so it is only a fallback.

The module is named ``stt`` rather than ``speech_recognition`` on purpose:
a file with that name would shadow the third-party package of the same name.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from core.models import Utterance
from utils.config import Config
from utils.logger import get_logger, redact

log = get_logger("voice.stt")

SAMPLE_RATE = 16000
_MIN_AUDIO_SECONDS = 0.25


class BaseEngine:
    """Interface every recogniser implements."""

    name = "base"

    def load(self) -> bool:                                      # pragma: no cover
        return False

    def transcribe(self, pcm: bytes) -> Utterance:               # pragma: no cover
        raise NotImplementedError


class WhisperEngine(BaseEngine):
    """faster-whisper: offline, accurate, CPU friendly with int8 quantisation."""

    name = "whisper"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._model = None

    def load(self) -> bool:
        try:
            from faster_whisper import WhisperModel               # noqa: PLC0415
        except ImportError as exc:
            log.warning("faster-whisper not installed (%s)", exc)
            return False
        size = str(self.config.get("whisper_model", "base.en"))
        compute = str(self.config.get("whisper_compute_type", "int8"))
        try:
            started = time.time()
            self._model = WhisperModel(size, device="cpu", compute_type=compute)
            log.info("Whisper model '%s' ready in %.1fs", size, time.time() - started)
            return True
        except Exception as exc:                                # noqa: BLE001
            log.error("Could not load Whisper model '%s': %s", size, exc)
            return False

    def transcribe(self, pcm: bytes) -> Utterance:
        import numpy as np                                       # noqa: PLC0415

        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        started = time.time()
        language = str(self.config.get("language", "en-IN")).split("-")[0]
        segments, info = self._model.transcribe(
            samples,
            language=language or "en",
            beam_size=int(self.config.get("whisper_beam_size", 1) or 1),
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=(
                "Sales coordination commands. Business codes like RP0002442, "
                "CAN000410, 29AAFCJ4954L1ZY, and company names."
            ),
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        confidence = float(getattr(info, "language_probability", 0.0) or 0.0)
        return Utterance(text=text, confidence=confidence, engine=self.name,
                         duration=time.time() - started)


class VoskEngine(BaseEngine):
    """Offline recogniser for low-spec machines."""

    name = "vosk"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._model = None

    def load(self) -> bool:
        path = str(self.config.get("vosk_model_path", "")).strip()
        if not path:
            log.info("vosk_model_path is not set; skipping Vosk")
            return False
        try:
            from vosk import Model, SetLogLevel                  # noqa: PLC0415

            SetLogLevel(-1)
            self._model = Model(path)
            log.info("Vosk model ready: %s", path)
            return True
        except Exception as exc:                                # noqa: BLE001
            log.error("Could not load Vosk model: %s", exc)
            return False

    def transcribe(self, pcm: bytes) -> Utterance:
        import json                                              # noqa: PLC0415

        from vosk import KaldiRecognizer                         # noqa: PLC0415

        started = time.time()
        recognizer = KaldiRecognizer(self._model, SAMPLE_RATE)
        recognizer.AcceptWaveform(pcm)
        payload = json.loads(recognizer.FinalResult() or "{}")
        return Utterance(text=str(payload.get("text", "")).strip(),
                         confidence=float(payload.get("conf", 0.0) or 0.0),
                         engine=self.name, duration=time.time() - started)


class GoogleEngine(BaseEngine):
    """Free web recogniser - needs internet, no key, used only as a fallback."""

    name = "google"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._recognizer = None

    def load(self) -> bool:
        try:
            import speech_recognition as sr                       # noqa: PLC0415
        except ImportError as exc:
            log.warning("SpeechRecognition not installed (%s)", exc)
            return False
        self._recognizer = sr.Recognizer()
        log.info("Google web recogniser ready (fallback)")
        return True

    def transcribe(self, pcm: bytes) -> Utterance:
        import speech_recognition as sr                           # noqa: PLC0415

        started = time.time()
        audio = sr.AudioData(pcm, SAMPLE_RATE, 2)
        language = str(self.config.get("language", "en-IN"))
        try:
            text = self._recognizer.recognize_google(audio, language=language)
        except sr.UnknownValueError:
            text = ""
        except sr.RequestError as exc:
            log.warning("Google STT unreachable: %s", exc)
            raise
        return Utterance(text=str(text).strip(), confidence=0.8, engine=self.name,
                         duration=time.time() - started)


_ENGINES = {"whisper": WhisperEngine, "vosk": VoskEngine, "google": GoogleEngine}
_AUTO_ORDER = ("whisper", "vosk", "google")


class SpeechRecognizer:
    """Loads an engine lazily and transcribes recorded PCM."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self._engine: Optional[BaseEngine] = None
        self._fallback: Optional[BaseEngine] = None
        self._lock = threading.Lock()
        self.ready = False

    # ------------------------------------------------------------------ setup
    def load(self) -> bool:
        """Load the configured engine (blocking - do it during splash)."""
        with self._lock:
            if self.ready:
                return True
            preference = str(self.config.get("stt_engine", "auto")).lower()
            order = (preference,) if preference in _ENGINES else _AUTO_ORDER

            for name in order:
                engine = _ENGINES[name](self.config)
                if engine.load():
                    self._engine = engine
                    break
            if self._engine is None:
                log.error("No speech recognition engine could be loaded")
                return False

            if self._engine.name != "google":
                spare = GoogleEngine(self.config)
                self._fallback = spare if spare.load() else None

            self.ready = True
            log.info("Speech recognition ready: %s", self._engine.name)
            return True

    @property
    def engine_name(self) -> str:
        return self._engine.name if self._engine else "none"

    # ------------------------------------------------------------- transcribe
    def transcribe(self, pcm: bytes) -> Utterance:
        """Convert PCM to text. Returns an empty Utterance instead of raising."""
        if not pcm or len(pcm) < int(SAMPLE_RATE * 2 * _MIN_AUDIO_SECONDS):
            return Utterance()
        if not self.ready and not self.load():
            return Utterance()

        try:
            result = self._engine.transcribe(pcm)
        except Exception as exc:                                # noqa: BLE001
            log.warning("%s engine failed (%s); trying fallback",
                        self.engine_name, exc)
            result = Utterance()

        if not result.text and self._fallback is not None:
            try:
                result = self._fallback.transcribe(pcm)
            except Exception as exc:                            # noqa: BLE001
                log.warning("Fallback recogniser failed: %s", exc)
                return Utterance()

        log.info("Heard: %s", redact(result.text, allow=True, keep=120))
        return result

    def transcribe_text(self, pcm: bytes) -> str:
        return self.transcribe(pcm).text
