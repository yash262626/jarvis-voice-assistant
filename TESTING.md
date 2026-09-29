# TESTING.md — verification checklist

Two layers: automated tests that need nothing but Python, and a manual
walkthrough on real Windows.

---

## 1. Automated tests

```bat
.venv\Scripts\activate
pip install pytest
pytest tests -v
```

Expected: **114 passed**. No microphone is opened, no key is pressed, no window
is touched — every backend is replaced with a fake.

| File | Covers |
|---|---|
| `test_intent_engine.py` | Every command shape in the spec, including chains, addresses, codes |
| `test_text_normalizer.py` | Spoken punctuation, spelled codes, identifier casing |
| `test_typing_actions.py` | Focus restoration, clipboard vs keystrokes, error handling |
| `test_browser_actions.py` | URL encoding, scheme blocking |
| `test_command_router.py` | Allow-list, confirmation flow, exception containment, plugin loading |
| `test_safety_manager.py` | Blocked intents, path sandbox, dangerous-action rules |

Parsing can also be checked without speaking:

```bat
python main.py --text "type Anand Trading Company and press Enter"
python main.py --console
python main.py --diagnose
```

---

## 2. Manual checklist

Tick each row on the target machine. `logs\jarvis.log` explains any failure.

### Start-up

| # | Step | Expected | ✓ |
|---|---|---|---|
| 1 | `run_jarvis.bat` on a clean machine | venv created, deps installed, models downloaded | |
| 2 | `python main.py` | Dashboard opens, tray icon appears, state `SLEEPING` | |
| 3 | `python main.py --diagnose` | Lists mic devices, wake engine, STT engine, intents | |
| 4 | Launch a second copy | Refuses politely: already running | |

### Wake word

| # | Step | Expected | ✓ |
|---|---|---|---|
| 5 | Say "Hey Jarvis" | Chirp, *"Yes, sir?"*, state → `LISTENING` | |
| 6 | Say nothing for 5 s | Returns to `SLEEPING` on its own | |
| 7 | Press Ctrl+Alt+J | Same activation as the wake word | |
| 8 | Talk normally nearby for 2 min | No false triggers (else raise the threshold) | |
| 9 | While JARVIS is speaking | Its own voice does not re-trigger it | |

### Typing — the critical path

| # | Step | Expected | ✓ |
|---|---|---|---|
| 10 | Click a cell in Excel → "type Anand Trading Company" | Text lands **in that cell**; Excel keeps focus | |
| 11 | "enter RP0002442" | Exactly `RP0002442` | |
| 12 | "type 29AAFCJ4954L1ZY" | GST number exact, upper-case | |
| 13 | "type C A N triple zero four one zero" | `CAN000410` | |
| 14 | In Chrome's address bar → "type github.com" | Text in the bar, not in JARVIS | |
| 15 | In WhatsApp → "type Dear Sir comma please confirm full stop" | `Dear Sir, please confirm.` | |
| 16 | "type Bennikal Village, Hoovina Hadagali, Vijayanagara, Karnataka" | One line, commas kept, **one** action | |
| 17 | "type Anand and Sons Trading" | Not split at "and" | |
| 18 | Dictate a 400-character paragraph | Pasted instantly; clipboard restored afterwards | |
| 19 | Open the JARVIS window, then say "type Mumbai" | Still goes to the previous app | |

### Keyboard

| # | Step | Expected | ✓ |
|---|---|---|---|
| 20 | "press Enter" in Excel | Moves down one cell | |
| 21 | "press Tab twice" | Moves two cells right | |
| 22 | "copy" then "paste" | Ctrl+C / Ctrl+V behaviour | |
| 23 | "select all" then "undo" | Ctrl+A then Ctrl+Z | |
| 24 | "press Control S" | Save dialog appears | |

### Multi-action

| # | Step | Expected | ✓ |
|---|---|---|---|
| 25 | "type Anand Trading Company and press Enter" | Types, then Enter | |
| 26 | "Type Anand Trading Company, press Tab, type Mumbai, press Enter" | 4 actions, correct order | |

### Dictation mode

| # | Step | Expected | ✓ |
|---|---|---|---|
| 27 | "start typing mode" | *"Typing mode activated"*, state `DICTATING` | |
| 28 | Speak 3 sentences | Each typed, no wake word needed between them | |
| 29 | Say "press Enter" while dictating | Key pressed, not typed as words | |
| 30 | "stop typing" | Exits, back to `SLEEPING` | |

### Applications and web

| # | Step | Expected | ✓ |
|---|---|---|---|
| 31 | "open Chrome" | Chrome launches | |
| 32 | "open Excel" / "open Notepad" / "open Calculator" | Each launches | |
| 33 | "open something-that-does-not-exist" | Clear spoken error, no crash | |
| 34 | "close Notepad" | Asks to confirm → "yes" → closes | |
| 35 | "search Google for tesla stock" | Google results tab | |
| 36 | "search YouTube for Arijit Singh" | YouTube results tab | |
| 37 | "search Anand Trading Company" | A **web search**, never typing | |
| 38 | "go to github.com" | Opens the site | |

### Files and system

| # | Step | Expected | ✓ |
|---|---|---|---|
| 39 | "create a folder on my desktop called Sales Orders" | Folder appears | |
| 40 | "open Downloads" | Explorer opens the folder | |
| 41 | "what time is it" / "what's today's date" | Spoken correctly | |
| 42 | "shut down my computer" → "no" | Cancelled, nothing happens | |
| 43 | "lock my computer" | Workstation locks | |

### Interface

| # | Step | Expected | ✓ |
|---|---|---|---|
| 44 | Watch the state readout through one command | SLEEPING → LISTENING → PROCESSING → EXECUTING → SPEAKING → SLEEPING | |
| 45 | Close the window with X | Hides to the tray, still listening | |
| 46 | Tray → Disable listening | State `PAUSED`, wake word ignored | |
| 47 | Tray → Settings → change voice/rate → Save | Applies to the next spoken reply | |
| 48 | Settings → Start with Windows → reboot | JARVIS starts minimised | |
| 49 | Tray → Restart JARVIS | Subsystems reload, no leftover mic lock | |
| 50 | Type a command into the dashboard box | Executes like a spoken one | |

### Resilience

| # | Step | Expected | ✓ |
|---|---|---|---|
| 51 | Unplug the USB mic while running | Logged, reconnects within ~5 s | |
| 52 | Mumble something meaningless | *"Sorry, I didn't understand that"* — nothing runs | |
| 53 | Break `config/config.json` deliberately | Starts on defaults, warning in the log | |
| 54 | Try to type into an admin-elevated app | Clear message about running as administrator | |
| 55 | Leave it running for a few hours | No memory growth, still responds | |

---

## 3. Spec acceptance — three workflows

**A. Type into Excel**
Open Excel → click a cell → "Hey Jarvis" → "type Anand Trading Company"
→ the text is in that cell, Excel never lost focus.

**B. Open an application**
"Hey Jarvis" → "open Chrome" → Chrome launches, JARVIS says *"Opening Chrome."*

**C. Search YouTube**
"Hey Jarvis" → "search YouTube for Python tutorials" → YouTube opens with those
results.

If all three pass, the build is good.
