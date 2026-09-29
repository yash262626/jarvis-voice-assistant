"""System tray presence so JARVIS can run in the background all day."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from gui import styles
from utils.logger import get_logger

log = get_logger("gui.tray")


def build_icon(state: str = "SLEEPING") -> QIcon:
    """Draw the tray icon at runtime - a copper ring, tinted by state."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    colour = QColor(styles.state_color(state))

    painter.setPen(QPen(QColor(styles.LINE), 5))
    painter.drawEllipse(6, 6, 52, 52)
    pen = QPen(colour, 6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawArc(6, 6, 52, 52, 90 * 16, -260 * 16)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    painter.drawEllipse(26, 26, 12, 12)
    painter.end()

    return QIcon(pixmap)


class SystemTray:
    """Tray icon plus the menu described in the project spec."""

    def __init__(self, assistant, window, controller) -> None:
        self.assistant = assistant
        self.window = window
        self.controller = controller

        self.icon = QSystemTrayIcon(build_icon("SLEEPING"))
        self.icon.setToolTip("JARVIS - say \"Hey Jarvis\"")
        self._build_menu()
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

        assistant.state.on_change(self._on_state)

    # ----------------------------------------------------------------- menu
    def _build_menu(self) -> None:
        menu = QMenu()

        title = QAction("JARVIS", menu)
        title.setEnabled(False)
        menu.addAction(title)
        menu.addSeparator()

        self.listen_action = QAction("Disable listening", menu)
        self.listen_action.triggered.connect(self._toggle_listening)
        menu.addAction(self.listen_action)

        wake_action = QAction("Wake now", menu)
        wake_action.triggered.connect(self.assistant.trigger_wake)
        menu.addAction(wake_action)

        menu.addSeparator()

        dashboard_action = QAction("Open dashboard", menu)
        dashboard_action.triggered.connect(self.window.show_dashboard)
        menu.addAction(dashboard_action)

        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        restart_action = QAction("Restart JARVIS", menu)
        restart_action.triggered.connect(self.controller.restart_assistant)
        menu.addAction(restart_action)

        menu.addSeparator()

        exit_action = QAction("Exit", menu)
        exit_action.triggered.connect(self.controller.quit)
        menu.addAction(exit_action)

        self.menu = menu
        self.icon.setContextMenu(menu)

    # ---------------------------------------------------------------- events
    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            if self.window.isVisible():
                self.window.hide()
            else:
                self.window.show_dashboard()

    def _on_state(self, old, new) -> None:
        try:
            self.icon.setIcon(build_icon(str(new)))
            self.icon.setToolTip(f"JARVIS - {new}")
        except Exception as exc:                                # noqa: BLE001
            log.debug("Tray icon update failed: %s", exc)

    def _toggle_listening(self) -> None:
        enabled = not self.assistant.listening_enabled
        self.assistant.set_listening(enabled)
        self.listen_action.setText("Disable listening" if enabled else "Enable listening")
        self.window.mic_button.setText(
            "Pause microphone" if enabled else "Resume microphone"
        )

    def _open_settings(self) -> None:
        self.window.show_dashboard()
        self.window.open_settings()

    # ------------------------------------------------------------------- API
    def notify(self, message: str, title: str = "JARVIS") -> None:
        try:
            self.icon.showMessage(title, message, build_icon("SLEEPING"), 3000)
        except Exception as exc:                                # noqa: BLE001
            log.debug("Tray notification failed: %s", exc)

    def hide(self) -> None:
        self.icon.hide()
