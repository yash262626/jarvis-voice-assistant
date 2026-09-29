"""Visual language for the JARVIS window.

Grounded in the work it supports: a sales desk in the wire and cable trade.
The accent is copper - the conductor itself - against annealed graphite, not
the usual sci-fi cyan. State readouts and echoed commands are set in a
monospace face on purpose: when the thing you just dictated is ``RP0002442``,
fixed-width digits let you verify it at a glance instead of squinting.
"""

from __future__ import annotations

# --- palette --------------------------------------------------------------
INK = "#14161A"          # window base, deep graphite
PANEL = "#1B1E24"        # raised surfaces
LINE = "#2A2F38"         # hairline rules
TEXT = "#E6E3DE"         # warm off-white, easier on the eye than pure white
MUTED = "#8A8F98"        # secondary text
COPPER = "#C87137"       # the accent: conductor copper
COPPER_DIM = "#7A4622"
SIGNAL = "#6FA97A"       # ready / success
AMBER = "#D6A03A"        # working
ALERT = "#C05A4E"        # error

STATE_COLORS = {
    "SLEEPING": MUTED,
    "LISTENING": COPPER,
    "ACTIVATED": COPPER,
    "PROCESSING": AMBER,
    "EXECUTING": AMBER,
    "SPEAKING": SIGNAL,
    "DICTATING": SIGNAL,
    "CONFIRMING": AMBER,
    "PAUSED": MUTED,
    "ERROR": ALERT,
}

BODY_FONT = "Segoe UI"
MONO_FONT = "Cascadia Mono, Consolas, monospace"

STYLESHEET = f"""
QWidget {{
    background: {INK};
    color: {TEXT};
    font-family: "{BODY_FONT}";
    font-size: 13px;
}}

#Header {{
    background: {INK};
    border-bottom: 1px solid {LINE};
}}
#WordMark {{
    font-family: {MONO_FONT};
    font-size: 15px;
    letter-spacing: 3px;
    color: {TEXT};
}}
#SubMark {{
    color: {MUTED};
    font-size: 11px;
}}

#StatePanel {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 10px;
}}
#StateName {{
    font-family: {MONO_FONT};
    font-size: 17px;
    letter-spacing: 2px;
}}
#StatusLine {{
    color: {MUTED};
    font-size: 12px;
}}

#Transcript {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 13px;
}}

#MetaLabel {{
    color: {MUTED};
    font-size: 11px;
}}
#MetaValue {{
    font-family: {MONO_FONT};
    font-size: 12px;
    color: {TEXT};
}}

QLineEdit {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {COPPER_DIM};
}}
QLineEdit:focus {{
    border: 1px solid {COPPER};
}}

QPushButton {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 8px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    border-color: {COPPER_DIM};
}}
QPushButton:pressed {{
    background: {LINE};
}}
QPushButton#Primary {{
    background: {COPPER_DIM};
    border-color: {COPPER};
}}
QPushButton#Primary:hover {{
    background: {COPPER};
}}
QPushButton:disabled {{
    color: {MUTED};
    border-color: {LINE};
}}

QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 20px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL};
    border: 1px solid {LINE};
    selection-background-color: {COPPER_DIM};
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {LINE};
    border-radius: 4px;
    background: {PANEL};
}}
QCheckBox::indicator:checked {{
    background: {COPPER};
    border-color: {COPPER};
}}

QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {LINE}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {COPPER_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QMenu {{
    background: {PANEL};
    border: 1px solid {LINE};
    padding: 6px;
}}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {COPPER_DIM}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 8px; }}

QLabel#DialogHint {{ color: {MUTED}; font-size: 11px; }}
"""


def state_color(state: str) -> str:
    return STATE_COLORS.get(str(state).upper(), MUTED)


def transcript_line(speaker: str, text: str, timestamp: str) -> str:
    """One HTML row for the conversation view."""
    is_user = speaker.lower() == "you"
    color = TEXT if is_user else COPPER
    escaped = (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return (
        f'<div style="margin:0 0 9px 0;">'
        f'<span style="color:{MUTED};font-size:10px;">{timestamp}</span>&nbsp;'
        f'<span style="color:{color};font-weight:600;">{speaker}</span><br>'
        f'<span style="color:{TEXT};">{escaped}</span>'
        f"</div>"
    )
