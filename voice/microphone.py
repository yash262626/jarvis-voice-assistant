"""One microphone stream, shared by the wake-word detector and the recogniser.

Opening the device twice is the classic cause of "microphone busy" bugs, so
there is exactly one ``sounddevice.InputStream``. Consumers subscribe to a
queue and receive 80 ms blocks of 16 kHz mono int16 audio - the exact format
openWakeWord wants, and trivially convertible for Whisper.

Voice activity detection is a rolling energy gate with an auto-calibrated
noise floor, so it adapts to a noisy office without any tuning.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque
from typing import List, Optional, Tuple

from utils.config import Config
from utils.logger import get_logger

log = get_logger("voice.microphone")

BLOCK_SIZE = 1280            # 80 ms at 16 kHz - openWakeWord's expected chunk
SAMPLE_RATE = 16000
PRE_ROLL_BLOCKS = 6          # ~480 ms kept so the first syllable is never clipped
_MIN_THRESHOLD = 180.0       # int16 RMS floor; below this is silence in any room


class MicrophoneError(RuntimeError):
    """Raised when no usable capture device is available."""


class Microphone:
    """Continuous capture with fan-out to any number of consumers."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self.sample_rate = int(self.config.get("mic_sample_rate", SAMPLE_RATE) or SAMPLE_RATE)
        self.block_size = BLOCK_SIZE
        self.device = self.config.get("mic_device")

        self._stream = None
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()
        self._pre_roll: deque = deque(maxlen=PRE_ROLL_BLOCKS)
        self._noise_floor = _MIN_THRESHOLD
        self._noise_samples = 0
        self._running = False
        self._error: str = ""
        self._watchdog: Optional[threading.Thread] = None
        self._stop_watchdog = threading.Event()

    # ------------------------------------------------------------- lifecycle
    @property
    def running(self) -> bool:
        return self._running

    @property
    def error(self) -> str:
        return self._error

    def start(self) -> bool:
        """Open the capture device. Returns False (never raises) on failure."""
        if self._running:
            return True
        try:
            import numpy as np                                   # noqa: PLC0415
            import sounddevice as sd                             # noqa: PLC0415
        except ImportError as exc:
            self._error = f"Audio libraries missing: {exc}"
            log.error("%s - run: pip install -r requirements.txt", self._error)
            return False

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                device=self.device,
                channels=1,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:                                # noqa: BLE001
            self._error = str(exc)
            log.error("Could not open microphone: %s", exc)
            self._stream = None
            return False

        self._running = True
        self._error = ""
        log.info("Microphone open (%d Hz, device=%s)", self.sample_rate,
                 self.device if self.device is not None else "default")
        self._start_watchdog()
        return True

    def stop(self) -> None:
        self._stop_watchdog.set()
        self._running = False
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:                                   # noqa: BLE001
                pass
        log.info("Microphone closed")

    def _start_watchdog(self) -> None:
        """Reopen the device if it disappears (USB headset unplugged, etc.)."""
        if self._watchdog and self._watchdog.is_alive():
            return
        self._stop_watchdog.clear()

        def loop() -> None:
            while not self._stop_watchdog.wait(5.0):
                if not self._running:
                    continue
                stream = self._stream
                if stream is None or not getattr(stream, "active", False):
                    log.warning("Microphone stream stopped; reconnecting")
                    self._running = False
                    try:
                        if stream is not None:
                            stream.close()
                    except Exception:                           # noqa: BLE001
                        pass
                    self._stream = None
                    self.start()

        self._watchdog = threading.Thread(target=loop, name="mic-watchdog", daemon=True)
        self._watchdog.start()

    # --------------------------------------------------------------- capture
    def _callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover
        if status:
            log.debug("Audio status: %s", status)
        try:
            block = bytes(indata)
            self._update_noise_floor(block)
            self._pre_roll.append(block)
            with self._lock:
                subscribers = list(self._subscribers)
            for sink in subscribers:
                try:
                    sink.put_nowait(block)
                except queue.Full:
                    try:
                        sink.get_nowait()        # drop the oldest block
                        sink.put_nowait(block)
                    except queue.Empty:
                        pass
        except Exception as exc:                                # noqa: BLE001
            log.debug("Audio callback error: %s", exc)

    # ------------------------------------------------------------- consumers
    def subscribe(self, maxsize: int = 100) -> queue.Queue:
        sink: queue.Queue = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.append(sink)
        return sink

    def unsubscribe(self, sink: queue.Queue) -> None:
        with self._lock:
            if sink in self._subscribers:
                self._subscribers.remove(sink)

    # ------------------------------------------------------------------- VAD
    @staticmethod
    def rms(block: bytes) -> float:
        """Root-mean-square level of an int16 block, 0-32767."""
        if not block:
            return 0.0
        try:
            import numpy as np                                   # noqa: PLC0415

            samples = np.frombuffer(block, dtype=np.int16).astype(np.float32)
            if samples.size == 0:
                return 0.0
            return float(np.sqrt(np.mean(samples * samples)))
        except ImportError:                                      # pragma: no cover
            import array

            samples = array.array("h", block)
            if not samples:
                return 0.0
            return math.sqrt(sum(s * s for s in samples) / len(samples))

    def _update_noise_floor(self, block: bytes) -> None:
        level = self.rms(block)
        if self._noise_samples < 12:
            self._noise_floor = max(_MIN_THRESHOLD, (self._noise_floor + level) / 2)
            self._noise_samples += 1
        elif level < self._noise_floor * 2.5:
            self._noise_floor = 0.97 * self._noise_floor + 0.03 * level

    @property
    def speech_threshold(self) -> float:
        configured = float(self.config.get("silence_threshold", 0) or 0)
        if configured > 0:
            return configured
        return max(_MIN_THRESHOLD * 1.4, self._noise_floor * 3.0)

    # ----------------------------------------------------------- record turn
    def record_command(
        self,
        start_timeout: Optional[float] = None,
        max_seconds: Optional[float] = None,
        silence_duration: Optional[float] = None,
        on_level: Optional[callable] = None,
    ) -> Tuple[bytes, bool]:
        """Record one spoken phrase.

        Returns ``(pcm_bytes, heard_speech)``. Stops after ``silence_duration``
        of quiet, or ``max_seconds`` overall, or immediately if the user never
        starts speaking within ``start_timeout``.
        """
        if not self._running and not self.start():
            return b"", False

        start_timeout = float(start_timeout if start_timeout is not None
                              else self.config.get("command_start_timeout", 5.0))
        max_seconds = float(max_seconds if max_seconds is not None
                            else self.config.get("command_max_seconds", 15.0))
        silence_duration = float(silence_duration if silence_duration is not None
                                 else self.config.get("silence_duration", 1.0))

        block_seconds = self.block_size / float(self.sample_rate)
        sink = self.subscribe()
        chunks: List[bytes] = list(self._pre_roll)
        threshold = self.speech_threshold
        started = False
        quiet_for = 0.0
        began = time.time()

        try:
            while True:
                elapsed = time.time() - began
                if not started and elapsed > start_timeout:
                    break
                if elapsed > max_seconds + start_timeout:
                    break
                try:
                    block = sink.get(timeout=1.0)
                except queue.Empty:
                    if not self._running:
                        break
                    continue

                level = self.rms(block)
                if on_level is not None:
                    try:
                        on_level(min(1.0, level / 6000.0))
                    except Exception:                           # noqa: BLE001
                        pass

                chunks.append(block)
                if level >= threshold:
                    started = True
                    quiet_for = 0.0
                elif started:
                    quiet_for += block_seconds
                    if quiet_for >= silence_duration:
                        break
                if started and (time.time() - began) > max_seconds:
                    break
        finally:
            self.unsubscribe(sink)

        audio = b"".join(chunks)
        log.debug("Recorded %.2fs (speech=%s, threshold=%.0f)",
                  len(audio) / (2.0 * self.sample_rate), started, threshold)
        return audio, started

    # ----------------------------------------------------------------- info
    @staticmethod
    def list_devices() -> List[dict]:
        """Enumerate input devices for the settings dialog."""
        try:
            import sounddevice as sd                             # noqa: PLC0415

            return [
                {"index": index, "name": device["name"],
                 "channels": device["max_input_channels"]}
                for index, device in enumerate(sd.query_devices())
                if device["max_input_channels"] > 0
            ]
        except Exception as exc:                                # noqa: BLE001
            log.warning("Could not list audio devices: %s", exc)
            return []
