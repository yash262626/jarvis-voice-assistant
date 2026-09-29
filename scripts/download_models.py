"""Fetch the offline models JARVIS needs, so the first launch is instant.

Run once with internet access:  python scripts\\download_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import Config                                    # noqa: E402


def download_wake_word() -> bool:
    print("[1/2] Wake word model (hey_jarvis)...")
    try:
        import openwakeword

        openwakeword.utils.download_models(["hey_jarvis"])
        print("      done.")
        return True
    except ImportError:
        print("      openwakeword is not installed - skipping.")
    except Exception as exc:                                       # noqa: BLE001
        print(f"      could not download: {exc}")
        print("      JARVIS will fall back to Ctrl+Alt+J until this succeeds.")
    return False


def download_whisper() -> bool:
    config = Config()
    size = str(config.get("whisper_model", "base.en"))
    print(f"[2/2] Speech recognition model ({size})...")
    try:
        from faster_whisper import WhisperModel

        WhisperModel(size, device="cpu",
                     compute_type=str(config.get("whisper_compute_type", "int8")))
        print("      done.")
        return True
    except ImportError:
        print("      faster-whisper is not installed - skipping.")
    except Exception as exc:                                       # noqa: BLE001
        print(f"      could not download: {exc}")
    return False


if __name__ == "__main__":
    print("Downloading JARVIS models (one time, needs internet)\n")
    ok = [download_wake_word(), download_whisper()]
    print("\nAll set." if all(ok) else
          "\nFinished with warnings - JARVIS will still start, see messages above.")
