"""Generate assets/jarvis.ico for the executable build.

Tries Qt first, then Pillow. If neither is available the build simply goes
ahead without a custom icon - never a hard failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TARGET = Path(__file__).resolve().parent / "jarvis.ico"
COPPER = (200, 113, 55)
GRAPHITE = (26, 29, 34)


def with_qt() -> bool:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
    except ImportError:
        return False
    try:
        app = QGuiApplication.instance() or QGuiApplication(sys.argv)
        pixmap = QPixmap(256, 256)
        pixmap.fill(QColor(*GRAPHITE))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(*COPPER), 20)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(34, 34, 188, 188, 90 * 16, -260 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(*COPPER))
        painter.drawEllipse(106, 106, 44, 44)
        painter.end()
        del app
        return bool(pixmap.save(str(TARGET), "ICO"))
    except Exception:                                              # noqa: BLE001
        return False


def with_pillow() -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    try:
        image = Image.new("RGB", (256, 256), GRAPHITE)
        draw = ImageDraw.Draw(image)
        draw.arc((34, 34, 222, 222), start=190, end=90, fill=COPPER, width=20)
        draw.ellipse((106, 106, 150, 150), fill=COPPER)
        image.save(TARGET, format="ICO",
                   sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
        return True
    except Exception:                                              # noqa: BLE001
        return False


if __name__ == "__main__":
    if with_qt() or with_pillow():
        print(f"Icon written to {TARGET}")
    else:
        print("Could not generate an icon - the build will use the default one.")
