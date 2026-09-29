"""The intent engine is the safety-critical piece: every command shape is tested."""

from __future__ import annotations

import pytest


def first(engine, text):
    actions = engine.parse(text)
    assert actions, f"no action parsed for {text!r}"
    return actions[0]


# ---------------------------------------------------------------- applications
@pytest.mark.parametrize("phrase", [
    "open chrome", "launch chrome", "start chrome", "run chrome",
    "open Google Chrome", "Can you open Chrome?", "hey jarvis open chrome",
])
def test_open_chrome_variants(engine, phrase):
    action = first(engine, phrase)
    assert action.intent == "open_application"
    assert "chrome" in action.get("application").lower()


def test_open_notepad_and_calculator(engine):
    assert first(engine, "open notepad").get("application") == "notepad"
    assert first(engine, "open calculator").get("application") == "calculator"
    assert first(engine, "open task manager").get("application") == "task manager"


def test_close_application(engine):
    action = first(engine, "close notepad")
    assert action.intent == "close_application"
    assert action.get("application") == "notepad"


# --------------------------------------------------------------------- search
def test_google_search(engine):
    action = first(engine, "search google for tesla stock")
    assert action.intent == "web_search"
    assert action.get("query") == "tesla stock"
    assert action.get("engine") == "google"


@pytest.mark.parametrize("phrase,expected", [
    ("search youtube for python tutorials", "python tutorials"),
    ("Search YouTube for Arijit Singh", "Arijit Singh"),
    ("search for funny dog videos on youtube", "funny dog videos"),
    ("play lofi beats on youtube", "lofi beats"),
])
def test_youtube_search(engine, phrase, expected):
    action = first(engine, phrase)
    assert action.intent == "youtube_search"
    assert action.get("query").lower() == expected.lower()


def test_bare_search_is_web_search_not_typing(engine):
    """Spec section 15: 'search X' must never become type_text."""
    action = first(engine, "search Anand Trading Company")
    assert action.intent == "web_search"
    assert action.get("query") == "Anand Trading Company"


# --------------------------------------------------------------------- typing
@pytest.mark.parametrize("phrase", [
    "type Anand Trading Company",
    "enter Anand Trading Company",
    "write Anand Trading Company",
    "put Anand Trading Company here",
    "type this Anand Trading Company",
    "enter this Anand Trading Company",
    "write this Anand Trading Company",
])
def test_type_variants(engine, phrase):
    action = first(engine, phrase)
    assert action.intent == "type_text"
    assert action.get("text") == "Anand Trading Company"


@pytest.mark.parametrize("phrase,expected", [
    ("type RP0002442", "RP0002442"),
    ("enter CAN000410", "CAN000410"),
    ("type 29AAFCJ4954L1ZY", "29AAFCJ4954L1ZY"),
    ("type rp0002442", "RP0002442"),
    ("type 1C 800 33 KV E AL Armoured Cable", "1C 800 33 KV E AL Armoured Cable"),
])
def test_business_identifiers(engine, phrase, expected):
    assert first(engine, phrase).get("text") == expected


def test_address_keeps_its_commas(engine):
    text = "Bennikal Village, Hoovina Hadagali, Vijayanagara, Karnataka"
    actions = engine.parse(f"type {text}")
    assert len(actions) == 1, "an address must not be split into several actions"
    assert actions[0].get("text") == text


def test_company_name_with_and_is_not_split(engine):
    actions = engine.parse("type Anand and Sons Trading")
    assert len(actions) == 1
    assert actions[0].get("text") == "Anand and Sons Trading"


def test_spoken_punctuation(engine):
    action = first(engine, "type Dear Sir comma Please find attached the revised PO full stop")
    assert action.get("text") == "Dear Sir, Please find attached the revised PO."


def test_spelled_out_code(engine):
    assert first(engine, "type C A N triple zero four one zero").get("text") == "CAN000410"


# ------------------------------------------------------------------- keyboard
@pytest.mark.parametrize("key", ["enter", "tab", "escape", "backspace", "delete",
                                 "space", "up", "down", "left", "right"])
def test_press_keys(engine, key):
    action = first(engine, f"press {key}")
    assert action.intent == "press_key"
    assert action.get("key") == key


def test_press_repeat(engine):
    assert first(engine, "press tab twice").get("times") == 2
    assert first(engine, "press enter 3 times").get("times") == 3


@pytest.mark.parametrize("phrase,keys", [
    ("copy", ["ctrl", "c"]),
    ("paste", ["ctrl", "v"]),
    ("cut", ["ctrl", "x"]),
    ("undo", ["ctrl", "z"]),
    ("redo", ["ctrl", "y"]),
    ("select all", ["ctrl", "a"]),
    ("save", ["ctrl", "s"]),
    ("press control c", ["ctrl", "c"]),
])
def test_hotkeys(engine, phrase, keys):
    action = first(engine, phrase)
    assert action.intent == "hotkey"
    assert action.get("keys") == keys


# --------------------------------------------------------------- multi-action
def test_type_then_enter(engine):
    actions = engine.parse("type Anand Trading Company and press Enter")
    assert [a.intent for a in actions] == ["type_text", "press_key"]
    assert actions[0].get("text") == "Anand Trading Company"
    assert actions[1].get("key") == "enter"


def test_four_step_chain(engine):
    actions = engine.parse(
        "Type Anand Trading Company, press Tab, type Mumbai, press Enter"
    )
    assert [a.intent for a in actions] == [
        "type_text", "press_key", "type_text", "press_key"
    ]
    assert actions[2].get("text") == "Mumbai"


# -------------------------------------------------------------------- browser
def test_open_websites(engine):
    assert first(engine, "open youtube").intent == "open_website"
    assert first(engine, "open gmail").get("url").startswith("https://")
    assert first(engine, "go to github.com").get("url") == "https://github.com"


# --------------------------------------------------------------------- system
def test_system_intents(engine):
    assert first(engine, "what time is it?").intent == "get_time"
    assert first(engine, "what's today's date").intent == "get_date"
    assert first(engine, "lock my computer").intent == "lock_pc"
    assert first(engine, "shut down my computer").intent == "shutdown_pc"
    assert first(engine, "restart my computer").intent == "restart_pc"
    assert first(engine, "put my computer to sleep").intent == "sleep_pc"


def test_folders(engine):
    action = first(engine, "create a folder on my desktop called Sales Orders")
    assert action.intent == "create_folder"
    assert action.get("name") == "Sales Orders"
    assert action.get("location") == "desktop"
    assert first(engine, "open downloads").intent == "open_folder"


# ------------------------------------------------------------------ dictation
def test_dictation_mode(engine):
    assert first(engine, "start typing mode").intent == "start_dictation"
    assert first(engine, "stop typing").intent == "stop_dictation"


def test_unknown_command(engine):
    assert engine.parse("flibbertigibbet the quantum")[0].intent == "unknown"


def test_empty_input(engine):
    assert engine.parse("") == []
    assert engine.parse("   ") == []
