"""Settings dialog - so nobody has to edit Python (or JSON) to tune JARVIS."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from gui import styles
from utils import startup
from utils.logger import get_logger
from voice.microphone import Microphone

log = get_logger("gui.settings")


class SettingsDialog(QDialog):
    """Edits config/config.json and applies what can change at runtime."""

    def __init__(self, assistant, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.assistant = assistant
        self.config = assistant.config

        self.setWindowTitle("JARVIS settings")
        self.setMinimumWidth(430)
        self.setStyleSheet(styles.STYLESHEET)
        self._build()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(9)

        # --- voice ---------------------------------------------------------
        self.wake_word = QLineEdit(str(self.config.get("wake_word", "hey jarvis")))
        form.addRow("Wake word", self.wake_word)

        self.wake_threshold = QDoubleSpinBox()
        self.wake_threshold.setRange(0.1, 0.95)
        self.wake_threshold.setSingleStep(0.05)
        self.wake_threshold.setValue(float(self.config.get("wake_word_threshold", 0.5)))
        form.addRow("Wake sensitivity", self.wake_threshold)

        self.microphone = QComboBox()
        self.microphone.addItem("System default", None)
        for device in Microphone.list_devices():
            self.microphone.addItem(device["name"], device["index"])
        current = self.config.get("mic_device")
        index = self.microphone.findData(current)
        self.microphone.setCurrentIndex(max(0, index))
        form.addRow("Microphone", self.microphone)

        self.stt_engine = QComboBox()
        self.stt_engine.addItems(["auto", "whisper", "vosk", "google"])
        self.stt_engine.setCurrentText(str(self.config.get("stt_engine", "auto")))
        form.addRow("Recogniser", self.stt_engine)

        self.whisper_model = QComboBox()
        self.whisper_model.addItems(
            ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]
        )
        self.whisper_model.setCurrentText(str(self.config.get("whisper_model", "base.en")))
        form.addRow("Whisper model", self.whisper_model)

        # --- speech --------------------------------------------------------
        self.tts_enabled = QCheckBox("Speak responses out loud")
        self.tts_enabled.setChecked(bool(self.config.get("tts_enabled", True)))
        form.addRow("", self.tts_enabled)

        self.tts_voice = QComboBox()
        self.tts_voice.addItem("System default", "")
        for voice in self.assistant.tts.list_voices():
            self.tts_voice.addItem(voice, voice)
        saved_voice = str(self.config.get("tts_voice", ""))
        voice_index = self.tts_voice.findData(saved_voice)
        self.tts_voice.setCurrentIndex(max(0, voice_index))
        form.addRow("Voice", self.tts_voice)

        self.tts_rate = QSpinBox()
        self.tts_rate.setRange(80, 320)
        self.tts_rate.setValue(int(self.config.get("tts_rate", 175)))
        form.addRow("Speaking rate", self.tts_rate)

        self.tts_volume = QDoubleSpinBox()
        self.tts_volume.setRange(0.1, 1.0)
        self.tts_volume.setSingleStep(0.1)
        self.tts_volume.setValue(float(self.config.get("tts_volume", 1.0)))
        form.addRow("Volume", self.tts_volume)

        self.language = QLineEdit(str(self.config.get("language", "en-IN")))
        form.addRow("Language", self.language)

        # --- typing --------------------------------------------------------
        self.typing_method = QComboBox()
        self.typing_method.addItems(["auto", "sendinput", "clipboard", "pyautogui"])
        self.typing_method.setCurrentText(str(self.config.get("typing_method", "auto")))
        form.addRow("Typing method", self.typing_method)

        self.typing_interval = QDoubleSpinBox()
        self.typing_interval.setRange(0.0, 0.2)
        self.typing_interval.setSingleStep(0.005)
        self.typing_interval.setDecimals(3)
        self.typing_interval.setValue(float(self.config.get("typing_interval", 0.01)))
        form.addRow("Key delay (s)", self.typing_interval)

        self.auto_punctuation = QCheckBox("Convert spoken punctuation (\"comma\" -> ,)")
        self.auto_punctuation.setChecked(bool(self.config.get("auto_punctuation", True)))
        form.addRow("", self.auto_punctuation)

        self.uppercase_codes = QCheckBox("Upper-case business codes (rp0002442 -> RP0002442)")
        self.uppercase_codes.setChecked(
            bool(self.config.get("uppercase_alphanumeric_codes", True))
        )
        form.addRow("", self.uppercase_codes)

        # --- behaviour -----------------------------------------------------
        self.confirmations = QCheckBox("Confirm shutdown, restart and closing apps")
        self.confirmations.setChecked(
            bool(self.config.get("require_confirmation_for_dangerous_actions", True))
        )
        form.addRow("", self.confirmations)

        self.follow_up = QCheckBox("Keep listening briefly after each command")
        self.follow_up.setChecked(bool(self.config.get("follow_up_enabled", True)))
        form.addRow("", self.follow_up)

        self.sounds = QCheckBox("Play activation sounds")
        self.sounds.setChecked(bool(self.config.get("play_sounds", True)))
        form.addRow("", self.sounds)

        self.start_with_windows = QCheckBox("Start JARVIS when Windows starts")
        self.start_with_windows.setChecked(startup.is_enabled())
        form.addRow("", self.start_with_windows)

        self.log_typed = QCheckBox("Write dictated text into the log file")
        self.log_typed.setChecked(bool(self.config.get("log_typed_text", False)))
        form.addRow("", self.log_typed)

        layout.addLayout(form)

        hint = QLabel(
            "Recogniser and microphone changes apply after Restart JARVIS "
            "in the tray menu. Everything else takes effect immediately."
        )
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ save
    def _save(self) -> None:
        values = {
            "wake_word": self.wake_word.text().strip().lower() or "hey jarvis",
            "wake_word_threshold": round(self.wake_threshold.value(), 2),
            "mic_device": self.microphone.currentData(),
            "stt_engine": self.stt_engine.currentText(),
            "whisper_model": self.whisper_model.currentText(),
            "tts_enabled": self.tts_enabled.isChecked(),
            "tts_voice": self.tts_voice.currentData() or "",
            "tts_rate": self.tts_rate.value(),
            "tts_volume": round(self.tts_volume.value(), 2),
            "language": self.language.text().strip() or "en-IN",
            "typing_method": self.typing_method.currentText(),
            "typing_interval": round(self.typing_interval.value(), 3),
            "auto_punctuation": self.auto_punctuation.isChecked(),
            "uppercase_alphanumeric_codes": self.uppercase_codes.isChecked(),
            "require_confirmation_for_dangerous_actions": self.confirmations.isChecked(),
            "follow_up_enabled": self.follow_up.isChecked(),
            "play_sounds": self.sounds.isChecked(),
            "log_typed_text": self.log_typed.isChecked(),
            "start_with_windows": self.start_with_windows.isChecked(),
        }
        self.config.update(values, save=True)

        try:
            self.assistant.tts.reload_settings()
            self.assistant.intents.config = self.config
            startup.set_enabled(self.start_with_windows.isChecked())
        except Exception as exc:                                # noqa: BLE001
            log.warning("Could not apply all settings live: %s", exc)

        log.info("Settings saved")
        self.accept()
