"""The JARVIS dashboard.

Critically, this window is built so it *cannot* interfere with typing:

* ``WA_ShowWithoutActivating`` - showing or updating it never takes focus.
* Every widget except the manual command box has ``NoFocus``.
* Closing it hides to the tray instead of quitting.

All assistant callbacks arrive on worker threads, so they are marshalled onto
the Qt thread through :class:`SignalBridge` signals.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget,
)

from gui import styles
from gui.settings_dialog import SettingsDialog
from utils.logger import get_logger

log = get_logger("gui.window")


class SignalBridge(QObject):
    """Thread-safe bridge from the assistant's callbacks to the Qt event loop."""

    state_changed = Signal(str)
    user_text = Signal(str)
    jarvis_text = Signal(str)
    status = Signal(str)
    error = Signal(str)
    level = Signal(float)


class StateOrb(QWidget):
    """The one bold element: a copper ring that breathes with the mic level."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(74, 74)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._level = 0.0
        self._phase = 0.0
        self._color = QColor(styles.MUTED)
        self._active = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)

    def set_state(self, state: str) -> None:
        self._color = QColor(styles.state_color(state))
        self._active = state.upper() in {
            "LISTENING", "ACTIVATED", "PROCESSING", "EXECUTING", "SPEAKING", "DICTATING"
        }
        self.update()

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, float(level)))

    def _tick(self) -> None:
        self._level *= 0.82
        if self._active:
            self._phase = (self._phase + 0.18) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:                         # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        size = min(self.width(), self.height())
        margin = 8
        rect = self.rect().adjusted(margin, margin, -margin, -margin)

        painter.setPen(QPen(QColor(styles.LINE), 2))
        painter.drawEllipse(rect)

        pulse = 0.5 + 0.5 * math.sin(self._phase) if self._active else 0.0
        span = int((0.25 + 0.75 * max(self._level, pulse * 0.55)) * 360 * 16)
        pen = QPen(self._color, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -span)

        core = int(size * (0.16 + 0.05 * self._level))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect().center(), core // 2, core // 2)
        painter.end()


class MainWindow(QWidget):
    """Dashboard: state, transcript, last command and manual entry."""

    def __init__(self, assistant, app_controller=None) -> None:
        super().__init__()
        self.assistant = assistant
        self.controller = app_controller
        self.bridge = SignalBridge()

        self.setWindowTitle("JARVIS")
        self.setMinimumSize(520, 620)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(styles.STYLESHEET)

        self._build_ui()
        self._connect_signals()
        self._wire_assistant()

    # --------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # header ------------------------------------------------------------
        header = QWidget(objectName="Header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 12)
        header_layout.setSpacing(2)
        wordmark = QLabel("J A R V I S", objectName="WordMark")
        subtitle = QLabel("Voice assistant for the sales desk", objectName="SubMark")
        header_layout.addWidget(wordmark)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # state panel --------------------------------------------------------
        panel = QFrame(objectName="StatePanel")
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(16)

        self.orb = StateOrb()
        panel_layout.addWidget(self.orb)

        state_box = QVBoxLayout()
        state_box.setSpacing(3)
        self.state_label = QLabel("SLEEPING", objectName="StateName")
        self.status_label = QLabel("Starting up...", objectName="StatusLine")
        self.status_label.setWordWrap(True)
        state_box.addWidget(self.state_label)
        state_box.addWidget(self.status_label)
        state_box.addStretch(1)
        panel_layout.addLayout(state_box, 1)
        root.addWidget(panel)

        # transcript ---------------------------------------------------------
        self.transcript = QTextEdit(objectName="Transcript")
        self.transcript.setReadOnly(True)
        self.transcript.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.transcript.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Expanding)
        root.addWidget(self.transcript, 1)

        # meta ---------------------------------------------------------------
        meta = QVBoxLayout()
        meta.setSpacing(4)
        self.last_command_label = QLabel("--", objectName="MetaValue")
        self.last_command_label.setWordWrap(True)
        self.engine_label = QLabel("--", objectName="MetaValue")
        for caption, value in (("Last command", self.last_command_label),
                               ("Engines", self.engine_label)):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(caption, objectName="MetaLabel")
            label.setFixedWidth(96)
            row.addWidget(label)
            row.addWidget(value, 1)
            meta.addLayout(row)
        root.addLayout(meta)

        # manual entry --------------------------------------------------------
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText(
            "Type a command instead of speaking, then press Enter"
        )
        root.addWidget(self.command_input)

        # buttons -------------------------------------------------------------
        buttons = QHBoxLayout()
        buttons.setSpacing(9)
        self.mic_button = QPushButton("Pause microphone", objectName="Primary")
        self.wake_button = QPushButton("Wake now")
        self.settings_button = QPushButton("Settings")
        self.exit_button = QPushButton("Exit")
        for button in (self.mic_button, self.wake_button, self.settings_button,
                       self.exit_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            buttons.addWidget(button)
        root.addLayout(buttons)

    # -------------------------------------------------------------- plumbing
    def _connect_signals(self) -> None:
        self.bridge.state_changed.connect(self._on_state)
        self.bridge.user_text.connect(lambda text: self._append("You", text))
        self.bridge.jarvis_text.connect(lambda text: self._append("Jarvis", text))
        self.bridge.status.connect(self.status_label.setText)
        self.bridge.error.connect(self._on_error)
        self.bridge.level.connect(self.orb.set_level)

        self.command_input.returnPressed.connect(self._submit_typed)
        self.mic_button.clicked.connect(self._toggle_microphone)
        self.wake_button.clicked.connect(self.assistant.trigger_wake)
        self.settings_button.clicked.connect(self.open_settings)
        self.exit_button.clicked.connect(self._exit)

    def _wire_assistant(self) -> None:
        self.assistant.on_user_text = self.bridge.user_text.emit
        self.assistant.on_jarvis_text = self.bridge.jarvis_text.emit
        self.assistant.on_status = self.bridge.status.emit
        self.assistant.on_error = self.bridge.error.emit
        self.assistant.on_level = self.bridge.level.emit
        self.assistant.state.on_change(
            lambda old, new: self.bridge.state_changed.emit(str(new))
        )

    # ----------------------------------------------------------------- slots
    def _on_state(self, state: str) -> None:
        self.state_label.setText(state)
        self.state_label.setStyleSheet(f"color: {styles.state_color(state)};")
        self.orb.set_state(state)
        if self.assistant.last_command:
            self.last_command_label.setText(self.assistant.last_command)

    def _on_error(self, message: str) -> None:
        self.status_label.setText(message)
        self._append("Jarvis", message)

    def _append(self, speaker: str, text: str) -> None:
        if not text:
            return
        timestamp = dt.datetime.now().strftime("%H:%M")
        self.transcript.append(styles.transcript_line(speaker, text, timestamp))
        scrollbar = self.transcript.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        if speaker == "You":
            self.last_command_label.setText(text)

    def _submit_typed(self) -> None:
        text = self.command_input.text().strip()
        if text:
            self.command_input.clear()
            self.assistant.submit_text(text)

    def _toggle_microphone(self) -> None:
        enabled = not self.assistant.listening_enabled
        self.assistant.set_listening(enabled)
        self.mic_button.setText("Pause microphone" if enabled else "Resume microphone")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.assistant, self)
        dialog.exec()
        self.refresh_engines()

    def refresh_engines(self) -> None:
        info = self.assistant.diagnostics()
        self.engine_label.setText(
            f"wake {info['wake_engine']} / stt {info['stt_engine']} / "
            f"tts {'on' if info['tts'] else 'off'}"
        )

    def _exit(self) -> None:
        if self.controller is not None:
            self.controller.quit()

    # ---------------------------------------------------------------- window
    def closeEvent(self, event) -> None:                         # noqa: N802
        """Closing hides to the tray - JARVIS keeps listening."""
        if self.controller is not None and getattr(self.controller, "tray", None):
            event.ignore()
            self.hide()
            self.controller.tray.notify("JARVIS is still listening in the tray.")
        else:
            event.accept()

    def show_dashboard(self) -> None:
        self.show()
        self.raise_()
        self.refresh_engines()
