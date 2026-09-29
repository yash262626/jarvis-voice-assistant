# JARVIS — Voice Assistant for Windows

A hands-free desktop assistant that opens apps, searches the web, and — most
importantly — **types what you dictate straight into whatever field your cursor
is already in**: an Excel cell, an ERP form, a browser input, a WhatsApp box.

Say `Hey Jarvis` → it answers *"Yes, sir?"* → give the command.

Everything runs **offline on your machine**. No API key, no cloud account, no
subscription. Audio never leaves the computer unless you deliberately switch to
the online fallback recogniser.

---

## Why the typing feature matters

Most voice assistants can open Chrome. Very few can put text into the exact cell
you clicked a second ago. JARVIS does, because:

- The window never takes focus (`WA_ShowWithoutActivating`, every widget
  `NoFocus`), so your application stays active while JARVIS listens.
- A background tracker remembers the last non-JARVIS foreground window and
  restores it only if focus was lost.
- Characters are injected with the Win32 `SendInput` API using
  `KEYEVENTF_UNICODE`, which Windows delivers exactly like real typing. That's
  layout-independent, so `29AAFCJ4954L1ZY`, `RP0002442` and `₹` all land
  correctly without any per-application integration.

---

## Features

| Area | What it does |
|---|---|
| Wake word | "Hey Jarvis" via openWakeWord (offline, pre-trained). Ctrl+Alt+J as backup |
| Typing | Types at the cursor in any app; clipboard paste for long text |
| Dictation mode | "Start typing mode" → everything you say is typed until "stop typing" |
| Spoken punctuation | "comma", "full stop", "new line", "at the rate" → `,` `.` ⏎ `@` |
| Business codes | "R P zero zero zero two four four two" → `RP0002442`; `can000410` → `CAN000410` |
| Keyboard | Enter, Tab, Escape, arrows, F-keys, Ctrl+C/V/X/Z/Y/A/S, "press Tab twice" |
| Multi-action | "type Anand Trading Company, press Tab, type Mumbai, press Enter" |
| Applications | Open/close by name; finds them via registry App Paths and Start Menu |
| Web | Open sites, Google/Bing/DuckDuckGo search, YouTube search |
| Files | Create and open folders (sandboxed to your user profile) |
| System | Time, date, lock, sleep, restart, shutdown, volume — with confirmation |
| Interface | Dark dashboard, system tray, settings dialog, manual command box |
| Safety | Fixed intent allow-list; there is no shell-execution path anywhere |

---

## Requirements

- Windows 10 or 11 (64-bit)
- Python 3.10 – 3.12 ([python.org](https://www.python.org/downloads/windows/) —
  tick **Add python.exe to PATH** during setup)
- A working microphone
- ~2 GB disk for the speech models
- Internet **once**, to download dependencies and models

---

## Install and run

### The easy way

Double-click **`run_jarvis.bat`**. On first run it creates the virtual
environment, installs everything and downloads the models. After that it just
starts JARVIS.

### Manually

```bat
cd path\to\JARVIS
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\download_models.py
python main.py
```

### Command-line options

```bat
python main.py                    :: dashboard + tray
python main.py --minimized        :: start hidden in the tray
python main.py --console          :: no GUI, type commands in the terminal
python main.py --text "open chrome"   :: run one command and exit
python main.py --diagnose         :: check mic, engines, intents, then exit
```

`--text` and `--console` are the fastest way to test command parsing without
speaking.

---

## Voice commands

### Typing — the core

| Say | Result |
|---|---|
| type Anand Trading Company | Types it at the cursor |
| enter RP0002442 | Types `RP0002442` |
| write CAN000410 | Types `CAN000410` |
| put Anand Trading Company here | Types it |
| type this Anand Trading Company | Types it |
| type Dear Sir comma Please find attached the revised PO full stop | `Dear Sir, Please find attached the revised PO.` |
| type mail me at yash at the rate example dot com | `mail me at yash@example.com` |
| type C A N triple zero four one zero | `CAN000410` |
| type rp0002442 | `RP0002442` (auto upper-cased) |
| type Bennikal Village, Hoovina Hadagali, Vijayanagara, Karnataka | Typed as one line, commas intact |
| start typing mode … stop typing | Continuous dictation |
| type literally comma | Types the word "comma" |

### Keyboard

| Say | Result |
|---|---|
| press Enter / Tab / Escape / Backspace / Delete / Space | That key |
| press Tab twice · press Enter 3 times | Repeats |
| press Control C · press Ctrl+S | Shortcut |
| copy · paste · cut · undo · redo · select all · save | Standard shortcuts |
| new tab · close tab · refresh · screenshot | Browser / Windows shortcuts |

### Multi-action chains

| Say | Result |
|---|---|
| type Anand Trading Company and press Enter | 2 actions |
| type RP0002442 and press Tab | 2 actions |
| Type Anand Trading Company, press Tab, type Mumbai, press Enter | 4 actions |

Chains split only when the next word is a command verb — so company names with
"and", and addresses with commas, stay in one piece.

### Applications, web, files, system

| Say | Result |
|---|---|
| open Chrome / Excel / Notepad / Calculator / Task Manager / SAP | Launches it |
| close Notepad | Confirms, then closes |
| open YouTube / Gmail / GST portal / eway bill | Opens the site |
| go to github.com | Opens the URL |
| search Google for tesla stock | Google search |
| search YouTube for Arijit Singh | YouTube search |
| search Anand Trading Company | Web search (never typing) |
| create a folder on my desktop called Sales Orders | Creates it |
| open Downloads | Opens the folder |
| what time is it · what's today's date | Speaks it |
| lock my computer | Locks |
| shut down / restart my computer · put my computer to sleep | Asks first |
| volume up / down / mute | Adjusts |
| help · repeat · cancel · go to sleep | Assistant control |

---

## A day at the sales desk

```
Hey Jarvis → "Yes, sir?"
  open Excel
  type Anand Trading Company and press Tab
  type RP0002442 and press Tab
  type 29AAFCJ4954L1ZY and press Enter
  type Bennikal Village, Hoovina Hadagali, Vijayanagara, Karnataka
  save
  create a folder on my desktop called September Orders
  search Google for KEI 33 KV armoured cable price
```

For a long email or remarks column: **"start typing mode"**, talk normally
(saying "comma" and "full stop" where you want them), then **"stop typing"**.

---

## Settings

Tray → **Settings**, or edit `config/config.json`. Key values:

| Setting | Default | Meaning |
|---|---|---|
| `wake_word` | `hey jarvis` | Phrase that activates JARVIS |
| `wake_word_threshold` | `0.5` | Lower = more sensitive, more false triggers |
| `wake_hotkey` | `ctrl+alt+j` | Always-available manual trigger |
| `stt_engine` | `auto` | `whisper` (offline) · `vosk` · `google` (online) |
| `whisper_model` | `base.en` | `tiny.en` faster · `small.en` more accurate |
| `typing_method` | `auto` | `sendinput` · `clipboard` · `pyautogui` |
| `clipboard_threshold` | `200` | Above this many characters, paste instead of type |
| `typing_interval` | `0.01` | Delay per character; raise to `0.03` for slow ERP forms |
| `auto_punctuation` | `true` | Convert spoken punctuation words |
| `uppercase_alphanumeric_codes` | `true` | `rp0002442` → `RP0002442` |
| `require_confirmation_for_dangerous_actions` | `true` | Ask before shutdown/restart/close |
| `sandbox_file_operations` | `true` | Folder actions stay inside your user profile |
| `follow_up_enabled` | `true` | Keep listening briefly after each command |
| `log_typed_text` | `false` | Keep dictated business text out of the log |
| `start_with_windows` | `false` | Login entry under HKCU\...\Run |
| `llm_enabled` | `false` | Optional natural-language fallback (see below) |

**Start with Windows**: tick it in Settings. It writes a single `HKEY_CURRENT_USER`
Run entry — no admin rights, and unticking removes it.

---

## Building a standalone .exe

```bat
build_exe.bat
```

Output: `dist\JARVIS\JARVIS.exe`. Copy the whole `dist\JARVIS` folder to move it
to another PC. Expect **1.5–2.5 GB** — Whisper, onnxruntime and Qt are bundled.
Windows SmartScreen will warn on first launch because the build is unsigned:
*More info → Run anyway*.

---

## Optional: LLM fallback

Off by default and **not required**. When enabled, sentences the rule engine
can't parse are sent to Claude or GPT, which may only reply with JSON naming an
allow-listed intent. It cannot invent new capabilities and it never produces a
command string.

1. `copy .env.example .env` and add your key
2. Set `"llm_enabled": true` in `config/config.json`

---

## Safety model

- **Allow-list**: `core/safety_manager.py` holds every intent JARVIS can perform.
  Anything else — from a misheard sentence or from the LLM — is dropped before a
  handler is reached.
- **No shell**: there is no `run_command` intent, no `os.system`, no `shell=True`
  anywhere in the codebase. Power commands are a fixed list of argument arrays.
- **Confirmation** for shutdown, restart, sleep and closing applications.
- **Sandbox**: folder operations are restricted to your user profile; Windows,
  System32 and Program Files are hard-blocked.
- **Privacy**: audio is processed locally by default, and dictated text is not
  written to the log unless you switch `log_typed_text` on.

---

## Project structure

```
JARVIS/
├── main.py                     entry point (GUI / console / one-shot / diagnose)
├── run_jarvis.bat              first-run setup + launch
├── build_exe.bat               builds dist\JARVIS\JARVIS.exe
├── jarvis.spec                 PyInstaller spec
├── config/
│   ├── config.json             all settings
│   ├── applications.json       app name → executable paths
│   └── websites.json           site name → URL
├── core/
│   ├── assistant.py            the wake→listen→parse→execute→speak loop
│   ├── intent_engine.py        rule-based parser (~45 ordered rules)
│   ├── text_normalizer.py      punctuation, spelled codes, identifier casing
│   ├── command_router.py       handler registry + plugin auto-discovery
│   ├── safety_manager.py       allow-list, confirmations, path sandbox
│   ├── state_manager.py        state machine
│   ├── llm_intent.py           optional JSON-only LLM fallback
│   └── models.py               Action / ActionResult / Utterance
├── voice/
│   ├── microphone.py           one shared stream, fan-out, energy VAD
│   ├── wake_word.py            openWakeWord → STT polling → hotkey
│   ├── stt.py                  faster-whisper → Vosk → Google
│   ├── text_to_speech.py       SAPI5 in a dedicated worker thread
│   └── sounds.py               short activation cues
├── actions/                    typing · keyboard · browser · apps · files · system
├── gui/                        main_window · system_tray · settings_dialog · styles
├── utils/                      config · logger · helpers · win_input · win_window
│                               · hotkey · startup
├── tests/                      114 unit tests, no OS calls
├── scripts/download_models.py  one-time model download
└── logs/                       rotating logs, auto-pruned
```

Adding a capability: drop a module in `actions/` with a
`register(router, context)` function and add its intent to `ALLOWED_INTENTS`.
Nothing else needs to change.

---

## Troubleshooting

**"Hey Jarvis" isn't detected**
Use Ctrl+Alt+J or the *Wake now* button to confirm the rest works. Then run
`python scripts\download_models.py`, and lower `wake_word_threshold` to `0.35`.
Check the right microphone is selected in Settings.

**Text goes into the wrong window**
Click the target field once before speaking. If the target app runs **as
administrator**, JARVIS must run as administrator too — Windows blocks input
injection into higher-privilege windows (UIPI).

**Characters are dropped in Excel or an ERP form**
Raise `typing_interval` to `0.03`, or set `typing_method` to `clipboard`.

**Numbers or codes come out wrong**
Set `whisper_model` to `small.en`. For difficult codes, spell them:
"type C A N triple zero four one zero".

**Microphone not found / busy**
Close other apps using the mic, then Settings → pick the device explicitly, then
tray → *Restart JARVIS*. `python main.py --diagnose` lists every input device.

**No voice output**
Check `tts_enabled`, and that a SAPI5 voice exists under Windows Settings →
Time & language → Speech.

**Nothing happens at all**
Read `logs\jarvis.log` — every failure is recorded there with a reason.

---

## Known limitations

- **Windows only.** The input, window and startup layers are Win32-specific.
- **Elevated apps** need JARVIS elevated too (Windows security, not a bug).
- **First run is slow** — models download (~150 MB) and Whisper loads for ~5–15 s.
- **Whisper on CPU** adds roughly 0.5–2 s per command; `tiny.en` is faster,
  `small.en` more accurate.
- **Noisy rooms** raise false wake triggers; raise `wake_word_threshold`.
- **The .exe is large** (1.5–2.5 GB) and unsigned.
- **Accents**: `base.en` handles Indian English well but unusual proper nouns
  may need spelling out.
- **No shell access by design** — JARVIS cannot run arbitrary programs or
  scripts, only launch applications it can resolve.

---

## Tests

```bat
.venv\Scripts\activate
pip install pytest
pytest tests -v
```

114 tests, no microphone, no keystrokes, no OS calls — every backend is faked.
Manual verification steps are in `TESTING.md`.

---

MIT licensed. Built for Yash Ail.
