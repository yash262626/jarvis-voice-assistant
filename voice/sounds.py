"""Short non-speech cues so you know JARVIS heard you before it speaks."""

from __future__ import annotations

import sys
import threading

from utils.logger import get_logger

log = get_logger("voice.sounds")

_TONES = {
    "wake": ((880, 90), (1170, 110)),      # rising: I'm listening
    "done": ((1170, 70),),                 # short blip: action finished
    "error": ((420, 160),),                # low buzz: something failed
    "dictation": ((660, 80), (880, 80), (1170, 90)),
}


def play(name: str, enabled: bool = True) -> None:
    """Play a cue asynchronously. Silently does nothing off Windows."""
    if not enabled or sys.platform != "win32":
        return
    tones = _TONES.get(name)
    if not tones:
        return

    def worker() -> None:
        try:
            import winsound                                      # noqa: PLC0415

            for frequency, duration in tones:
                winsound.Beep(frequency, duration)
        except Exception as exc:                                # noqa: BLE001
            log.debug("Could not play cue %s: %s", name, exc)

    threading.Thread(target=worker, name=f"cue-{name}", daemon=True).start()
