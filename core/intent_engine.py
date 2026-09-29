"""Deterministic intent engine.

Turns a recognised sentence into a list of structured :class:`Action` objects.
No shell strings are ever produced - the router only accepts intents from a
fixed allow-list, so a mis-heard sentence can never become a command.

Everything here is pure text processing with no OS calls, which makes it fully
unit-testable (see ``tests/test_intent_engine.py``).
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Pattern, Tuple

from core.models import Action
from core.text_normalizer import normalize_typed_text, strip_trailing_politeness
from utils.config import Config, load_json_asset
from utils.helpers import normalise_url
from utils.logger import get_logger

log = get_logger("core.intent")

# Verbs that may legitimately start a new action inside one sentence.
_CHAIN_VERBS = (
    "press|hit|tap|type|enter|write|put|input|insert|open|launch|start|run|close|quit|"
    "search|google|copy|paste|cut|undo|redo|select all|save|go to|play|create|make|"
    "lock|shutdown|shut down|restart|reboot|maximise|maximize|minimise|minimize"
)
_SPLIT_RE = re.compile(
    rf"\s*(?:,|;|\band then\b|\bthen\b|\band\b)\s+(?=(?:{_CHAIN_VERBS})\b)", re.IGNORECASE
)

_FILLERS = re.compile(
    r"^\s*(?:ok(?:ay)?|hey|hi|hello|yo|please|kindly|umm?|uh|so)\b[\s,]*", re.IGNORECASE
)
_POLITE_PREFIX = re.compile(
    r"^\s*(?:can you|could you|would you|will you|i want you to|i need you to|"
    r"please|jarvis|hey jarvis|ok jarvis|let's|lets)\b[\s,]*",
    re.IGNORECASE,
)
_TRAILING_QUESTION = re.compile(r"[?.!]+$")
_TYPE_START = re.compile(
    r"^(?:type|enter|write|input|insert|put|fill|add)\b", re.IGNORECASE
)

_TIMES = {
    "once": 1, "twice": 2, "thrice": 3, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_KEY_ALIASES = {
    "return": "enter", "escape key": "escape", "esc": "escape",
    "back space": "backspace", "space bar": "space", "spacebar": "space",
    "arrow up": "up", "arrow down": "down", "arrow left": "left",
    "arrow right": "right", "up arrow": "up", "down arrow": "down",
    "left arrow": "left", "right arrow": "right", "page up": "pageup",
    "page down": "pagedown", "print screen": "printscreen", "windows key": "win",
    "control": "ctrl",
}

_BARE_KEYS = {
    "enter", "return", "tab", "escape", "esc", "backspace", "delete", "space",
    "spacebar", "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    "page up", "page down", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9",
    "f10", "f11", "f12",
}

_HOTKEYS = {
    "copy": ("ctrl", "c"),
    "paste": ("ctrl", "v"),
    "cut": ("ctrl", "x"),
    "undo": ("ctrl", "z"),
    "redo": ("ctrl", "y"),
    "select all": ("ctrl", "a"),
    "select everything": ("ctrl", "a"),
    "save": ("ctrl", "s"),
    "save file": ("ctrl", "s"),
    "save as": ("ctrl", "shift", "s"),
    "print": ("ctrl", "p"),
    "find": ("ctrl", "f"),
    "bold": ("ctrl", "b"),
    "italic": ("ctrl", "i"),
    "underline": ("ctrl", "u"),
    "new tab": ("ctrl", "t"),
    "close tab": ("ctrl", "w"),
    "reopen tab": ("ctrl", "shift", "t"),
    "refresh": ("f5",),
    "reload": ("f5",),
    "switch window": ("alt", "tab"),
    "next cell": ("tab",),
    "new line": ("enter",),
    "screenshot": ("win", "shift", "s"),
    "snip": ("win", "shift", "s"),
    "minimise all": ("win", "d"),
    "minimize all": ("win", "d"),
    "show desktop": ("win", "d"),
}

_MODIFIER_WORDS = {"ctrl", "control", "alt", "shift", "win", "windows", "command"}


class IntentEngine:
    """Rule-based parser. ``parse()`` returns zero or more actions."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self.websites = {
            str(k).lower(): v for k, v in (load_json_asset("websites.json", {}) or {}).items()
        }
        self.applications = load_json_asset("applications.json", {}) or {}
        self._rules: List[Tuple[str, Pattern[str], Callable]] = []
        self._build_rules()

    # ------------------------------------------------------------ public API
    def parse(self, text: str) -> List[Action]:
        """Parse a full utterance into an ordered list of actions."""
        if not text or not text.strip():
            return []

        cleaned = self.preprocess(text)
        if not cleaned:
            return []

        actions: List[Action] = []
        for segment in self.split_segments(cleaned):
            action = self.parse_segment(segment)
            if action:
                actions.append(action)

        if not actions:
            actions = [Action(intent="unknown", params={"text": cleaned}, raw_text=text,
                              confidence=0.0)]
        return actions

    def preprocess(self, text: str) -> str:
        """Strip the wake word, fillers and polite wrappers."""
        cleaned = " ".join(str(text).split())
        wake = str(self.config.get("wake_word", "hey jarvis")).strip().lower()
        pattern = re.compile(
            rf"^\s*(?:{re.escape(wake)}|jarvis|hey jarvis|ok jarvis)\b[\s,.!]*", re.IGNORECASE
        )
        previous = None
        while previous != cleaned:
            previous = cleaned
            cleaned = pattern.sub("", cleaned)
            cleaned = _FILLERS.sub("", cleaned)
            cleaned = _POLITE_PREFIX.sub("", cleaned)
        cleaned = cleaned.strip()

        # "Open Chrome?" -> "Open Chrome". Typing commands keep their
        # punctuation, because the user may want it typed.
        if cleaned and not _TYPE_START.match(cleaned):
            cleaned = cleaned.rstrip(" ?!.,")
        return cleaned.strip()

    def split_segments(self, text: str) -> List[str]:
        """Split "type X and press Enter" into ["type X", "press Enter"].

        A separator only splits when the *next* word is a command verb, so
        addresses and company names keep their commas and "and"s.
        """
        parts = [part.strip(" ,.;") for part in _SPLIT_RE.split(text)]
        return [part for part in parts if part]

    def parse_segment(self, segment: str) -> Optional[Action]:
        segment = segment.strip()
        if not segment:
            return None
        for name, pattern, builder in self._rules:
            match = pattern.match(segment)
            if match:
                try:
                    action = builder(match, segment)
                except Exception as exc:                        # noqa: BLE001
                    log.error("Rule %s failed on %r: %s", name, segment, exc)
                    action = None
                if action:
                    action.raw_text = segment
                    return action
        return None

    # --------------------------------------------------------------- helpers
    def _clean_text_payload(self, text: str) -> str:
        return normalize_typed_text(
            text.strip().strip('"'),
            auto_punctuation=bool(self.config.get("auto_punctuation", True)),
            normalize_codes=bool(self.config.get("normalize_spelled_codes", True)),
            uppercase_alphanumeric=bool(self.config.get("uppercase_alphanumeric_codes", True)),
        )

    @staticmethod
    def _clean_query(text: str) -> str:
        text = _TRAILING_QUESTION.sub("", text.strip())
        text = re.sub(r"^(for|about|regarding)\s+", "", text, flags=re.IGNORECASE)
        return strip_trailing_politeness(text).strip(" .,")

    @staticmethod
    def _resolve_key(name: str) -> str:
        key = re.sub(r"\s+", " ", name.strip().lower()).strip(" .")
        key = re.sub(r"\s*key$", "", key)
        return _KEY_ALIASES.get(key, key).replace(" ", "")

    @staticmethod
    def _repeat_count(text: str) -> int:
        match = re.search(r"\b(\d+|once|twice|thrice|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:times?)?\s*$",
                          text.strip(), re.IGNORECASE)
        if not match:
            return 1
        token = match.group(1).lower()
        if token.isdigit():
            return max(1, min(50, int(token)))
        return _TIMES.get(token, 1)

    def _lookup_website(self, name: str) -> Optional[str]:
        key = re.sub(r"\s+", " ", name.strip().lower()).strip(" .")
        key = re.sub(r"^(the|my)\s+", "", key)
        key = re.sub(r"\s+(website|site|page|dot com)$", "", key)
        if key in self.websites:
            return self.websites[key]
        for site, url in self.websites.items():
            if key == site.replace(" ", "") or key.replace(" ", "") == site.replace(" ", ""):
                return url
        return None

    # ----------------------------------------------------------------- rules
    def _build_rules(self) -> None:
        R = re.IGNORECASE
        add = lambda name, pattern, builder: self._rules.append(  # noqa: E731
            (name, re.compile(pattern, R), builder)
        )

        # -- session control ------------------------------------------------
        add("cancel",
            r"^(?:cancel|never ?mind|forget it|stop it|abort|nothing)\s*$",
            lambda m, s: Action("cancel"))
        add("sleep_assistant",
            r"^(?:go to sleep|stop listening|sleep now|standby|dismiss)\s*$",
            lambda m, s: Action("sleep_assistant"))
        add("exit_app",
            r"^(?:exit|quit|close)\s+(?:jarvis|yourself|the assistant)\s*$",
            lambda m, s: Action("exit_app"))

        # -- dictation mode --------------------------------------------------
        add("start_dictation",
            r"^(?:start|enable|activate|begin)\s+(?:the\s+)?(?:typing|dictation)\s*(?:mode)?\s*$",
            lambda m, s: Action("start_dictation"))
        add("start_dictation2",
            r"^(?:typing|dictation)\s+mode\s*(?:on)?\s*$",
            lambda m, s: Action("start_dictation"))
        add("stop_dictation",
            r"^(?:stop|end|exit|disable|cancel)\s+(?:the\s+)?(?:typing|dictation)"
            r"(?:\s+mode)?\s*$",
            lambda m, s: Action("stop_dictation"))
        add("stop_dictation2",
            r"^(?:typing|dictation)\s+mode\s+off\s*$",
            lambda m, s: Action("stop_dictation"))

        # -- confirmation ----------------------------------------------------
        add("affirm",
            r"^(?:yes|yeah|yep|yup|sure|confirm|confirmed|do it|go ahead|proceed|haan|ha)\b.*$",
            lambda m, s: Action("affirm"))
        add("deny",
            r"^(?:no|nope|nah|don'?t|do not|stop|negative|nahi)\b.*$",
            lambda m, s: Action("deny"))

        # -- keyboard --------------------------------------------------------
        add("press_combo",
            r"^(?:press|hit|tap|do)\s+(?P<combo>(?:ctrl|control|alt|shift|win|windows|command)"
            r"(?:\s*\+\s*|\s+)[\w\s+]+?)\s*$",
            self._build_combo)
        add("press_key",
            r"^(?:press|hit|tap|push)\s+(?:the\s+)?(?P<key>[\w\s]+?)"
            r"(?:\s+key)?(?:\s+(?P<times>\d+|once|twice|thrice|one|two|three|four|five|six|seven|eight|nine|ten)"
            r"(?:\s*times?)?)?\s*$",
            self._build_press)
        add("bare_key",
            r"^(?P<key>" + "|".join(re.escape(k) for k in sorted(_BARE_KEYS, key=len, reverse=True))
            + r")\s*(?:key)?\s*$",
            lambda m, s: Action("press_key", {"key": self._resolve_key(m.group("key")), "times": 1}))
        add("hotkey_word",
            r"^(?:please\s+)?(?P<name>" + "|".join(
                re.escape(k) for k in sorted(_HOTKEYS, key=len, reverse=True)
            ) + r")(?:\s+(?:it|this|that|everything|all))?\s*$",
            lambda m, s: Action("hotkey", {"keys": list(_HOTKEYS[m.group("name").lower()])}))

        # -- typing (the core feature) ---------------------------------------
        add("type_literal",
            r"^(?:type|write|enter|input|insert)\s+(?:this\s+)?(?:literally|exactly|verbatim|as is)\s+"
            r"(?P<text>.+?)\s*$",
            lambda m, s: Action("type_text", {"text": m.group("text").strip(),
                                              "literal": True}))
        add("type_text",
            r"^(?:type|enter|write|input|insert|put|fill(?:\s+in)?|add)"
            r"(?:\s+(?:this|that|the following|in|out))?\s*[:\-]?\s+"
            r"(?P<text>.+?)"
            r"(?:\s+(?:here|there|in(?:to)?\s+(?:this|the)\s+(?:cell|field|box)))?\s*$",
            self._build_type)
        add("clear_field",
            r"^(?:clear|erase)\s+(?:the\s+)?(?:field|cell|text|line|input)\s*$",
            lambda m, s: Action("hotkey", {"keys": ["ctrl", "a"], "then": ["delete"]}))

        # -- search ----------------------------------------------------------
        add("youtube_search",
            r"^(?:search|find|look\s+up|play|show me)\s+(?:for\s+)?(?:on\s+)?youtube\s+"
            r"(?:for\s+|videos?\s+(?:of|about|on)\s+)?(?P<q>.+)$",
            lambda m, s: Action("youtube_search", {"query": self._clean_query(m.group("q"))}))
        add("youtube_search2",
            r"^(?:youtube|yt)\s+(?:search\s+)?(?P<q>.+)$",
            lambda m, s: Action("youtube_search", {"query": self._clean_query(m.group("q"))}))
        add("youtube_search3",
            r"^(?:search|find|look\s+up|play)\s+(?:for\s+)?(?P<q>.+?)\s+on\s+youtube\s*$",
            lambda m, s: Action("youtube_search", {"query": self._clean_query(m.group("q"))}))
        add("web_search_engine",
            r"^(?:search|look\s+up)\s+(?:on\s+)?(?P<engine>google|bing|duckduckgo)\s+"
            r"(?:for\s+)?(?P<q>.+)$",
            lambda m, s: Action("web_search", {"query": self._clean_query(m.group("q")),
                                               "engine": m.group("engine").lower()}))
        add("web_search_engine2",
            r"^(?:search|look\s+up)\s+(?:for\s+)?(?P<q>.+?)\s+on\s+(?P<engine>google|bing|duckduckgo)\s*$",
            lambda m, s: Action("web_search", {"query": self._clean_query(m.group("q")),
                                               "engine": m.group("engine").lower()}))
        add("google_verb",
            r"^google\s+(?:for\s+)?(?P<q>.+)$",
            lambda m, s: Action("web_search", {"query": self._clean_query(m.group("q")),
                                               "engine": "google"}))
        add("web_search",
            r"^(?:search|look\s+up|find)\s+(?:the\s+web\s+for\s+|for\s+|about\s+)?(?P<q>.+)$",
            lambda m, s: Action("web_search", {"query": self._clean_query(m.group("q")),
                                               "engine": self.config.get(
                                                   "default_search_engine", "google")}))

        # -- websites ---------------------------------------------------------
        add("goto_url",
            r"^(?:go\s+to|navigate\s+to|visit|browse\s+to|open)\s+(?:the\s+)?(?:website\s+)?"
            r"(?P<url>(?:https?://)?[\w\-]+(?:\s*dot\s*|\.)[\w\-./]+)\s*$",
            self._build_goto)
        add("open_website",
            r"^(?:open|launch|start|show)\s+(?:the\s+)?(?P<name>[\w\s]+?)"
            r"(?:\s+(?:website|site|page|in\s+(?:the\s+)?browser))?\s*$",
            self._build_open)

        # -- folders / files ---------------------------------------------------
        add("create_folder",
            r"^(?:create|make|add)\s+(?:a\s+)?(?:new\s+)?folder\s*"
            r"(?:on\s+(?:my\s+)?(?P<loc1>desktop|documents|downloads))?\s*"
            r"(?:(?:called|named|with\s+name)\s+)?(?P<name>[\w\s\-&.]+?)\s*"
            r"(?:(?:on|in)\s+(?:my\s+|the\s+)?(?P<loc2>desktop|documents|downloads))?\s*$",
            self._build_create_folder)
        add("open_folder",
            r"^(?:open|show|go\s+to)\s+(?:my\s+|the\s+)?"
            r"(?P<name>downloads?|desktop|documents?|pictures|music|videos|home)"
            r"(?:\s+folder)?\s*$",
            lambda m, s: Action("open_folder", {"name": m.group("name").lower()}))
        add("open_named_folder",
            r"^(?:open|show)\s+(?:the\s+)?(?P<name>[\w\s\-&.]+?)\s+folder"
            r"(?:\s+(?:on|in)\s+(?:my\s+|the\s+)?(?P<loc>desktop|documents|downloads))?\s*$",
            lambda m, s: Action("open_folder", {"name": m.group("name").strip(),
                                                "location": (m.group("loc") or "").lower()}))

        # -- system -------------------------------------------------------------
        add("get_time",
            r"^(?:what(?:'?s| is)?\s+(?:the\s+)?time|what\s+time\s+is\s+it|tell\s+me\s+the\s+time|time)\s*[?.]?$",
            lambda m, s: Action("get_time"))
        add("get_date",
            r"^(?:what(?:'?s| is)?\s+(?:today'?s?\s+)?(?:the\s+)?date|what\s+is\s+the\s+day|"
            r"what\s+day\s+is\s+it|tell\s+me\s+the\s+date|date)\s*[?.]?$",
            lambda m, s: Action("get_date"))
        add("lock_pc",
            r"^lock\s+(?:my\s+|the\s+)?(?:computer|pc|screen|laptop|system|windows)?\s*$",
            lambda m, s: Action("lock_pc"))
        add("sleep_pc",
            r"^(?:put\s+(?:my\s+|the\s+)?(?:computer|pc|laptop|system)\s+to\s+sleep|"
            r"sleep\s+(?:my\s+)?(?:computer|pc|laptop))\s*$",
            lambda m, s: Action("sleep_pc"))
        add("restart_pc",
            r"^(?:restart|reboot)\s+(?:my\s+|the\s+)?(?:computer|pc|laptop|system|windows)\s*$",
            lambda m, s: Action("restart_pc"))
        add("shutdown_pc",
            r"^(?:shut\s*down|power\s+off|turn\s+off)\s+(?:my\s+|the\s+)?"
            r"(?:computer|pc|laptop|system|windows)\s*$",
            lambda m, s: Action("shutdown_pc"))
        add("volume",
            r"^(?:volume|sound)\s+(?P<dir>up|down|mute|unmute)\s*$",
            lambda m, s: Action("set_volume", {"direction": m.group("dir").lower()}))
        add("volume2",
            r"^(?:mute|unmute)\s*(?:the\s+)?(?:volume|sound|audio)?\s*$",
            lambda m, s: Action("set_volume", {"direction": s.strip().split()[0].lower()}))
        add("help",
            r"^(?:help|what\s+can\s+you\s+do|show\s+commands|list\s+commands)\s*[?.]?$",
            lambda m, s: Action("help"))
        add("repeat",
            r"^(?:repeat|say\s+(?:that\s+)?again|come\s+again)\s*[?.]?$",
            lambda m, s: Action("repeat"))
        add("repeat_last_typing",
            r"^(?:type|enter)\s+(?:that|it)\s+again\s*$",
            lambda m, s: Action("repeat_typing"))

        # -- applications --------------------------------------------------------
        add("close_application",
            r"^(?:close|quit|exit|kill)\s+(?:the\s+)?(?P<app>[\w\s.+-]+?)"
            r"(?:\s+(?:app|application|window|program))?\s*$",
            lambda m, s: Action("close_application", {"application": m.group("app").strip()}))
        add("window_control",
            r"^(?:maximi[sz]e|minimi[sz]e)\s+(?:the\s+)?(?:window|it|this)?\s*$",
            lambda m, s: Action("hotkey", {
                "keys": ["win", "up"] if s.lower().startswith("max") else ["win", "down"]}))
        add("open_application",
            r"^(?:open|launch|start|run|fire\s+up)\s+(?:the\s+)?(?P<app>[\w\s.+-]+?)"
            r"(?:\s+(?:app|application|program|for\s+me))?\s*$",
            lambda m, s: Action("open_application", {"application": m.group("app").strip()}))

    # ------------------------------------------------------- rule builders
    def _build_type(self, match: re.Match, segment: str) -> Optional[Action]:
        raw = match.group("text").strip()
        if not raw:
            return None
        # "put my computer to sleep" must not become typing.
        if re.match(r"^(?:my\s+)?(?:computer|pc|laptop)\b", raw, re.IGNORECASE):
            return None
        return Action("type_text", {"text": self._clean_text_payload(raw), "raw": raw})

    def _build_press(self, match: re.Match, segment: str) -> Optional[Action]:
        key = self._resolve_key(match.group("key"))
        if not key:
            return None
        times_token = match.group("times")
        times = self._repeat_count(times_token) if times_token else 1
        if key in _MODIFIER_WORDS:
            return None                       # handled by the combo rule
        return Action("press_key", {"key": key, "times": times})

    def _build_combo(self, match: re.Match, segment: str) -> Optional[Action]:
        raw = match.group("combo").replace("+", " ")
        parts = [self._resolve_key(p) for p in raw.split() if p.strip()]
        parts = [p for p in parts if p]
        if len(parts) < 2:
            return None
        return Action("hotkey", {"keys": parts})

    def _build_goto(self, match: re.Match, segment: str) -> Optional[Action]:
        url = normalise_url(match.group("url"))
        if not url:
            return None
        return Action("open_website", {"url": url})

    def _build_open(self, match: re.Match, segment: str) -> Optional[Action]:
        name = match.group("name").strip()
        if not name:
            return None
        url = self._lookup_website(name)
        if url:
            return Action("open_website", {"url": url, "name": name.lower()})
        maybe_url = normalise_url(name)
        if maybe_url:
            return Action("open_website", {"url": maybe_url})
        lowered = name.lower()
        folder = re.sub(r"\s+folder$", "", lowered)
        if folder in {"downloads", "download", "desktop", "documents", "document",
                      "pictures", "music", "videos", "home"}:
            return Action("open_folder", {"name": folder})
        if lowered.endswith(" folder") and folder:
            return Action("open_folder", {"name": name[: -len(" folder")].strip()})
        return Action("open_application", {"application": name})

    def _build_create_folder(self, match: re.Match, segment: str) -> Optional[Action]:
        name = (match.group("name") or "").strip()
        location = (match.group("loc2") or match.group("loc1") or "desktop").lower()
        name = re.sub(r"^(?:called|named)\s+", "", name, flags=re.IGNORECASE).strip()
        if not name:
            return None
        return Action("create_folder", {"name": name, "location": location})
