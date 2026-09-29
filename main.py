"""JARVIS - voice assistant for Windows.

Usage
-----
    python main.py                 start with the dashboard
    python main.py --minimized     start hidden in the system tray
    python main.py --console       no GUI; type commands in the terminal
    python main.py --text "..."    run one command and exit
    python main.py --diagnose      check microphone, engines and exit
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.config import Config                                   # noqa: E402
from utils.helpers import SingleInstance                          # noqa: E402
from utils.logger import get_logger, prune_old_logs, setup_logging  # noqa: E402

log = get_logger("main")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS voice assistant")
    parser.add_argument("--minimized", "--minimised", action="store_true",
                        dest="minimized", help="start hidden in the system tray")
    parser.add_argument("--console", action="store_true",
                        help="run without the GUI (terminal only)")
    parser.add_argument("--text", metavar="COMMAND",
                        help="execute a single command and exit")
    parser.add_argument("--diagnose", action="store_true",
                        help="report the state of every subsystem and exit")
    parser.add_argument("--config", metavar="PATH", help="use an alternative config file")
    return parser.parse_args(argv)


# --------------------------------------------------------------------------
# GUI mode
# --------------------------------------------------------------------------
class JarvisApp:
    """Owns the Qt application, the window, the tray and the assistant."""

    def __init__(self, config: Config, minimized: bool = False) -> None:
        from PySide6.QtWidgets import QApplication                # noqa: PLC0415

        from core.assistant import Assistant                      # noqa: PLC0415
        from gui.main_window import MainWindow                     # noqa: PLC0415
        from gui.system_tray import SystemTray                     # noqa: PLC0415

        self.config = config
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setApplicationName("JARVIS")
        self.app.setQuitOnLastWindowClosed(False)

        self.assistant = Assistant(config)
        self.assistant.context.memory["on_exit"] = self.quit

        self.window = MainWindow(self.assistant, self)
        self.tray = SystemTray(self.assistant, self.window, self)

        if not minimized and not config.get("start_minimized", True):
            self.window.show_dashboard()
        elif not minimized:
            self.window.show_dashboard()

    def run(self) -> int:
        from PySide6.QtCore import QTimer                          # noqa: PLC0415

        QTimer.singleShot(80, self._boot)
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        return self.app.exec()

    def _boot(self) -> None:
        self.assistant.start()
        self.window.refresh_engines()
        info = self.assistant.diagnostics()
        if not info["microphone"]:
            self.tray.notify("Microphone unavailable - check Settings.")
        elif info["wake_engine"] in {"hotkey", "none"}:
            self.tray.notify(
                f"Wake word unavailable. Use {self.config.get('wake_hotkey')} "
                "or the Wake now button."
            )

    def restart_assistant(self) -> None:
        log.info("Restarting the assistant subsystems")
        self.assistant.shutdown()
        time.sleep(0.4)
        self.config.load()

        from core.assistant import Assistant                       # noqa: PLC0415

        self.assistant = Assistant(self.config)
        self.assistant.context.memory["on_exit"] = self.quit
        self.window.assistant = self.assistant
        self.window._wire_assistant()                              # noqa: SLF001
        self.tray.assistant = self.assistant
        self.assistant.state.on_change(self.tray._on_state)        # noqa: SLF001
        self.assistant.start()
        self.window.refresh_engines()
        self.tray.notify("JARVIS restarted.")

    def quit(self) -> None:
        log.info("Exiting")
        try:
            self.assistant.shutdown()
            self.tray.hide()
        finally:
            self.app.quit()


# --------------------------------------------------------------------------
# Console mode
# --------------------------------------------------------------------------
def run_console(config: Config) -> int:
    from core.assistant import Assistant

    assistant = Assistant(config)
    assistant.on_user_text = lambda text: print(f"  You    : {text}")
    assistant.on_jarvis_text = lambda text: print(f"  Jarvis : {text}")
    assistant.on_status = lambda text: print(f"  [{text}]")
    assistant.on_error = lambda text: print(f"  !! {text}")
    assistant.context.memory["on_exit"] = lambda: None
    assistant.start()

    print("\nJARVIS is running. Say \"{}\" or type a command.".format(
        config.get("wake_word", "hey jarvis")))
    print("Type 'quit' to exit, 'wake' to activate without speaking.\n")

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line.lower() in {"quit", "exit"}:
                break
            if line.lower() == "wake":
                assistant.trigger_wake()
                continue
            if line.lower() == "status":
                print(assistant.diagnostics())
                continue
            assistant.submit_text(line)
            time.sleep(0.6)
    except KeyboardInterrupt:
        pass
    finally:
        assistant.shutdown()
    return 0


def run_once(config: Config, command: str) -> int:
    """Execute a single command without any audio - handy for testing."""
    from core.assistant import Assistant

    assistant = Assistant(config)
    assistant.on_jarvis_text = lambda text: print(f"Jarvis: {text}")
    assistant.router.load_plugins("actions")
    assistant.tracker.start()

    results = assistant._handle_command(command, spoken=False)     # noqa: SLF001
    for result in results:
        print(f"[{'ok' if result.success else 'failed'}] "
              f"{result.detail or result.speech}")
    assistant.shutdown()
    return 0 if all(result.success for result in results) else 1


def run_diagnostics(config: Config) -> int:
    from core.assistant import Assistant
    from voice.microphone import Microphone

    print("JARVIS diagnostics")
    print("-" * 46)
    print(f"Platform            : {sys.platform}")
    print(f"Python              : {sys.version.split()[0]}")

    devices = Microphone.list_devices()
    print(f"Input devices       : {len(devices)}")
    for device in devices[:6]:
        print(f"  [{device['index']}] {device['name']}")

    assistant = Assistant(config)
    assistant.start()
    time.sleep(1.0)
    for key, value in assistant.diagnostics().items():
        print(f"{key:<20}: {value}")
    print("-" * 46)
    print("Registered intents  :", ", ".join(assistant.router.intents))
    assistant.shutdown()
    return 0


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    args = parse_args(argv)
    config = Config(args.config) if args.config else Config()

    setup_logging(config)
    prune_old_logs(int(config.get("log_retention_days", 14) or 14))
    log.info("JARVIS starting (python %s on %s)", sys.version.split()[0], sys.platform)

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if args.diagnose:
        return run_diagnostics(config)
    if args.text:
        return run_once(config, args.text)

    guard = SingleInstance()
    if guard.already_running:
        print("JARVIS is already running (check the system tray).")
        log.warning("Second instance blocked")
        return 0

    if args.console:
        return run_console(config)

    try:
        app = JarvisApp(config, minimized=args.minimized)
    except ImportError as exc:
        log.error("GUI unavailable (%s) - falling back to console mode", exc)
        print(f"PySide6 is not installed ({exc}). Running in console mode.")
        return run_console(config)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
