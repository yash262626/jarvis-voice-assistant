"""The assistant loop that ties every subsystem together.

    SLEEPING -> wake word -> ACTIVATED ("Yes, sir?") -> LISTENING
             -> PROCESSING (speech to text + intent) -> EXECUTING -> SPEAKING
             -> back to SLEEPING (or one short follow-up window)

Everything runs on background threads and communicates with the GUI through
plain callbacks, so the interface never blocks and never needs focus.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from core.command_router import ActionContext, CommandRouter
from core.intent_engine import IntentEngine
from core.llm_intent import LLMIntentEngine
from core.models import Action, ActionResult, Utterance
from core.safety_manager import SafetyManager
from core.state_manager import State, StateManager
from utils.config import Config
from utils.hotkey import GlobalHotkey
from utils.logger import get_logger
from utils.win_window import ForegroundTracker
from voice import sounds
from voice.microphone import Microphone
from voice.stt import SpeechRecognizer
from voice.text_to_speech import TextToSpeech
from voice.wake_word import WakeWordDetector

log = get_logger("core.assistant")

_ACK = "Yes, sir?"
_DICTATION_STOP = {
    "stop typing", "stop dictation", "stop typing mode", "exit typing mode",
    "typing mode off", "stop writing", "that's all", "thats all", "stop",
}


@dataclass
class _Event:
    kind: str                   # "wake" | "text"
    text: str = ""


class Assistant:
    """Owns the microphone, recogniser, intent engine, router and state."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self.state = StateManager()
        self.safety = SafetyManager(self.config)

        self.microphone = Microphone(self.config)
        self.tts = TextToSpeech(self.config)
        self.recognizer = SpeechRecognizer(self.config)
        self.tracker = ForegroundTracker()

        self.intents = IntentEngine(self.config)
        self.llm = LLMIntentEngine(self.config)

        self.context = ActionContext(
            config=self.config, safety=self.safety, tracker=self.tracker,
            tts=self.tts, state=self.state, assistant=self,
        )
        self.router = CommandRouter(self.context)

        self.wake = WakeWordDetector(
            self.microphone, self.config,
            on_wake=self.trigger_wake,
            transcriber=self.recognizer.transcribe_text,
        )
        self.hotkey = GlobalHotkey(
            str(self.config.get("wake_hotkey", "ctrl+alt+j")), self.trigger_wake
        )

        # ---- GUI callbacks (all optional) --------------------------------
        self.on_user_text: Optional[Callable[[str], None]] = None
        self.on_jarvis_text: Optional[Callable[[str], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_level: Optional[Callable[[float], None]] = None

        self._events: "queue.Queue[_Event]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pending: Optional[Action] = None
        self._dictating = threading.Event()
        self._listening_enabled = True
        self.last_command = ""
        self.last_response = ""
        self.started = False

    # ------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        """Boot every subsystem. Returns False only if nothing usable loaded."""
        if self.started:
            return True
        log.info("Starting JARVIS")

        self.router.load_plugins("actions")
        self.tracker.start()
        self.tts.start()
        self.tts.on_speak = lambda text: self._notify(self.on_jarvis_text, text)

        self._status("Loading speech recognition...")
        if not self.recognizer.load():
            self._error("Speech recognition could not start. "
                        "Check the install steps in README.md.")

        if not self.microphone.start():
            self._error(f"Microphone unavailable: {self.microphone.error or 'no device'}")
        else:
            self.wake.start()

        self.hotkey.start()

        self._stop.clear()
        self._worker = threading.Thread(target=self._run, name="assistant", daemon=True)
        self._worker.start()

        self.started = True
        self.state.set(State.SLEEPING)
        engine = self.wake.engine if self.wake.engine != "none" else "hotkey only"
        self._status(f"Ready - say \"{self.config.get('wake_word', 'hey jarvis')}\" "
                     f"({engine})")
        log.info("JARVIS ready (wake=%s, stt=%s)", engine, self.recognizer.engine_name)
        return True

    def shutdown(self) -> None:
        log.info("Shutting down JARVIS")
        self._stop.set()
        self._events.put(_Event("quit"))
        self.wake.stop()
        self.hotkey.stop()
        self.microphone.stop()
        self.tracker.stop()
        self.tts.stop()
        self.started = False

    # ---------------------------------------------------------------- inputs
    def trigger_wake(self) -> None:
        """Called by the wake-word detector, the hotkey or the GUI button."""
        if not self._listening_enabled:
            return
        if self.state.is_(State.SLEEPING, State.PAUSED, State.ERROR):
            self._events.put(_Event("wake"))

    def submit_text(self, text: str) -> None:
        """Run a typed command (GUI input box) without touching the microphone."""
        if text and text.strip():
            self._events.put(_Event("text", text.strip()))

    def set_listening(self, enabled: bool) -> None:
        """Enable/disable the microphone from the tray or GUI."""
        self._listening_enabled = enabled
        if enabled:
            if not self.microphone.running:
                self.microphone.start()
            self.wake.unmute()
            self.state.set(State.SLEEPING)
            self._status("Listening for the wake word")
        else:
            self.wake.mute()
            self.state.set(State.PAUSED)
            self._status("Microphone paused")

    @property
    def listening_enabled(self) -> bool:
        return self._listening_enabled

    @property
    def dictating(self) -> bool:
        return self._dictating.is_set()

    # ----------------------------------------------------------------- loop
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._events.get(timeout=0.5)
            except queue.Empty:
                continue
            if event.kind == "quit":
                break
            try:
                if event.kind == "wake":
                    self._handle_wake()
                elif event.kind == "text":
                    self._handle_command(event.text, spoken=False)
            except Exception as exc:                            # noqa: BLE001
                log.exception("Assistant loop error")
                self._error(f"Something went wrong: {exc}")
                self.state.set(State.SLEEPING)
            finally:
                self.wake.unmute()

    # ------------------------------------------------------------ wake cycle
    def _handle_wake(self) -> None:
        self.wake.mute()
        self.state.set(State.ACTIVATED)
        sounds.play("wake", bool(self.config.get("play_sounds", True)))
        self._speak(_ACK, block=True)

        heard_anything = False
        while True:
            utterance = self._listen(
                start_timeout=float(self.config.get("command_start_timeout", 5.0))
                if not heard_anything
                else float(self.config.get("active_timeout", 8))
            )
            if not utterance.text:
                if not heard_anything:
                    self._status("I didn't catch that")
                break

            heard_anything = True
            self._handle_command(utterance.text, spoken=True)

            if self._dictating.is_set():
                self._dictation_loop()
                break
            if not self.config.get("follow_up_enabled", True):
                break
            if self.state.is_(State.PAUSED):
                break

        self.state.set(State.SLEEPING)
        self._status("Listening for the wake word")

    def _listen(self, start_timeout: float) -> Utterance:
        """Record one phrase and transcribe it."""
        self.state.set(State.LISTENING)
        self.tts.wait(timeout=10)                # never record our own voice
        audio, heard = self.microphone.record_command(
            start_timeout=start_timeout,
            on_level=lambda level: self._notify(self.on_level, level),
        )
        if not heard:
            return Utterance()

        self.state.set(State.PROCESSING)
        utterance = self.recognizer.transcribe(audio)
        if utterance.text:
            self.last_command = utterance.text
            self._notify(self.on_user_text, utterance.text)
        return utterance

    # --------------------------------------------------------------- command
    def _handle_command(self, text: str, spoken: bool = True) -> List[ActionResult]:
        """Parse and execute one utterance. Returns the results for testing."""
        if not spoken:
            self.last_command = text
            self._notify(self.on_user_text, text)

        self.state.set(State.PROCESSING)

        if self._pending is not None:
            return [self._resolve_confirmation(text)]

        actions = self.intents.parse(text)
        if actions and actions[0].intent == "unknown" and self.llm.enabled:
            log.info("Rule engine missed; asking the LLM")
            llm_actions = self.llm.parse(text)
            if llm_actions:
                actions = llm_actions

        results: List[ActionResult] = []
        for action in actions:
            log.info("Intent: %s %s", action.intent, action.params or "")
            if self._handle_meta(action):
                continue

            self.state.set(State.EXECUTING)
            result = self.router.execute(action)
            results.append(result)

            if result.needs_confirmation and result.pending is not None:
                self._pending = result.pending
                self.state.set(State.CONFIRMING)
                self._speak(result.speech, block=True)
                answer = self._listen(start_timeout=6.0)
                results[-1] = self._resolve_confirmation(answer.text)
                break

            if result.speech:
                self._speak(result.speech)
            if not result.success:
                sounds.play("error", bool(self.config.get("play_sounds", True)))
                self._status(result.detail or result.speech)
                break
            self._status(result.detail or result.speech)

        return results

    def _handle_meta(self, action: Action) -> bool:
        """Handle intents the assistant owns itself. True = fully handled."""
        intent = action.intent

        if intent == "start_dictation":
            self._dictating.set()
            self.state.set(State.DICTATING)
            sounds.play("dictation", bool(self.config.get("play_sounds", True)))
            self._speak("Typing mode activated.", block=True)
            return True

        if intent == "stop_dictation":
            self._dictating.clear()
            self._speak("Typing mode stopped.")
            return True

        if intent in {"cancel", "deny"}:
            self._pending = None
            self._speak("Okay.")
            return True

        if intent == "sleep_assistant":
            self._speak("Going to sleep.")
            self.state.set(State.SLEEPING)
            return True

        if intent == "exit_app":
            self._speak("Goodbye, sir.", block=True)
            assistant_exit = self.context.memory.get("on_exit")
            if callable(assistant_exit):
                assistant_exit()
            return True

        if intent == "repeat":
            self._speak(self.last_response or "I haven't said anything yet.")
            return True

        if intent == "affirm" and self._pending is None:
            self._speak("Okay.")
            return True

        return False

    def _resolve_confirmation(self, answer: str) -> ActionResult:
        """Apply a yes/no answer to the action waiting for confirmation."""
        pending, self._pending = self._pending, None
        if pending is None:
            return ActionResult.ok("")

        actions = self.intents.parse(answer or "")
        approved = bool(actions) and actions[0].intent == "affirm"
        if not approved:
            log.info("Confirmation declined for %s", pending.intent)
            self._speak("Cancelled.")
            return ActionResult(success=True, speech="Cancelled.", detail="cancelled")

        self.state.set(State.EXECUTING)
        result = self.router.execute(pending, confirmed=True)
        if result.speech:
            self._speak(result.speech)
        self._status(result.detail or result.speech)
        return result

    # -------------------------------------------------------------- dictation
    def _dictation_loop(self) -> None:
        """Continuous typing: everything heard is typed until 'stop typing'."""
        typing = self.context.memory.get("typing_actions")
        while self._dictating.is_set() and not self._stop.is_set():
            self.state.set(State.DICTATING)
            utterance = self._listen(start_timeout=20.0)
            text = (utterance.text or "").strip()
            if not text:
                continue

            normalised = text.lower().strip(" .!,")
            if normalised in _DICTATION_STOP or normalised.startswith("stop typing"):
                self._dictating.clear()
                self._speak("Typing mode stopped.")
                break

            actions = self.intents.parse(text)
            if actions and actions[0].intent in {"press_key", "hotkey", "stop_dictation"}:
                if actions[0].intent == "stop_dictation":
                    self._dictating.clear()
                    self._speak("Typing mode stopped.")
                    break
                self.router.execute(actions[0])
                continue

            self.state.set(State.EXECUTING)
            payload = self.intents._clean_text_payload(text)     # noqa: SLF001
            result = self.router.execute(Action("type_text", {"text": payload}))
            if not result.success:
                self._speak(result.speech)
                self._status(result.detail)
            else:
                sounds.play("done", bool(self.config.get("play_sounds", True)))
                self._status(f"Typed: {payload[:60]}")

    # ---------------------------------------------------------------- output
    def _speak(self, text: str, block: bool = False) -> None:
        if not text:
            return
        self.last_response = text
        previous = self.state.state
        self.state.set(State.SPEAKING)
        self.wake.mute()
        self.tts.speak(text, block=block)
        if block:
            self.tts.wait(timeout=20)
        if self.state.is_(State.SPEAKING):
            self.state.set(previous)

    def _status(self, message: str) -> None:
        self._notify(self.on_status, message)

    def _error(self, message: str) -> None:
        log.error(message)
        self.state.set(State.ERROR)
        self._notify(self.on_error, message)

    @staticmethod
    def _notify(callback: Optional[Callable], *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as exc:                                # noqa: BLE001
            log.debug("Callback failed: %s", exc)

    # ------------------------------------------------------------------ info
    def diagnostics(self) -> dict:
        return {
            "state": str(self.state.state),
            "wake_engine": self.wake.engine,
            "stt_engine": self.recognizer.engine_name,
            "tts": self.tts.available,
            "microphone": self.microphone.running,
            "microphone_error": self.microphone.error,
            "intents": len(self.router.intents),
            "listening": self._listening_enabled,
            "dictating": self._dictating.is_set(),
        }
