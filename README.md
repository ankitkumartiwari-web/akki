# AKKI

AKKI is a local-first Windows desktop assistant. It runs deterministic tools
without a model, uses a local Ollama model when available, and falls back to an
OpenRouter model for harder requests. Voice input and output support English,
Hindi, Marathi, Bhojpuri (through the Hindi voice), Malayalam, Telugu, and Urdu.
AKKI also includes universal Windows app discovery, local document RAG, web page
reading, scheduled commands, multi-step deterministic chaining, wake-word
listening, speaker and face enrollment, a local web UI, a desktop tray icon,
access widget, and settings panel, mobile alerts for important mail, and a stdio
MCP client.

## Requirements

- Windows 10 or 11
- Python 3.11
- A microphone for voice input
- Optional: Ollama with a 3B model for local generation
- Optional: an OpenRouter API key for cloud fallback

## Install

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[voice,dev,docs,vision,desktop]"
```

Start AKKI:

```powershell
akki
```

If the `akki` command is not on `PATH`, use:

```powershell
.\.venv\Scripts\python -m akki.cli
```

## Model setup

Local-first generation uses Ollama:

```powershell
ollama pull richardyoung/fable-qwen2.5-3b-abliterated
```

Cloud fallback reads the key from the environment, never from the config:

```powershell
$env:OPENROUTER_API_KEY = "..."
```

`OPENROUTER_API_KEY` is only needed when cloud fallback is enabled.

## Voice

Install the default Piper voice and backend:

```text
:voice setup
```

Useful voice commands:

```text
:voice                       show voice, STT, and hotkey settings
:voice options               list Piper voices and aliases
:voice set hindi             switch to a Hindi voice
:voice set marathi           switch to the Marathi voice
:voice speaker 3             pick a speaker for multi-speaker voices
:voice use piper|sapi|edge   choose the synthesis engine
:voice indian                Indian English male (Edge en-IN-PrabhatNeural)
:voice indian-female         Indian English female (Edge en-IN-NeerjaNeural)
:voice edge <voice-id>       pick a specific Edge neural voice
:voice batman                deep Piper neural voice (slow and low pitch)
:voice pitch -12             lower or raise voice pitch (-50..50)
:voice on|off                toggle spoken replies
```

Hindi, Marathi, and other Indian-language models download on first use.
Bhojpuri uses the Hindi voice because no dedicated Piper Bhojpuri model exists.
The Edge engine needs internet access and `ffplay`; if it fails, AKKI falls back
to Piper. The `nsfw` content mode automatically uses
`en-IN-NeerjaExpressiveNeural`.

### Push to talk

```text
:hotkey on
```

Press `Ctrl+Space` to start listening and press it again to stop. Recording also
stops automatically after silence or 20 seconds. The hotkey autostarts on future
sessions once enabled. If `Ctrl+Space` is taken by another application, change
`voice.hotkey` in the config.

### Speech recognition

The default Whisper model is `small`, which supports multilingual recognition.
Adjust it at runtime:

```text
:stt                         show model and language
:stt model small             switch model (downloads on first use)
:stt language auto           auto-detect, or force en/hi/mr
```

For English-only low-memory use, `:stt model base.en` is faster.

## Content mode

```text
:mode                       show the current mode
:mode nsfw                  allow adult language and fictional adult content
:mode sovereign             same adult policy under the default name
:mode guarded               safer general-audience replies
```

The same setting is available in `:panel` under General. All modes keep the hard
limits: no sexual content involving minors, no non-consensual or coercive acts,
and no illegal material.

## Feedback learning

AKKI stores reward and punishment signals locally and injects them into future
prompts. This adapts tone and length without retraining model weights.

```text
:good short and direct       reward the last reply
:bad too long                punish the last reply
:feedback                    show score and recent notes
:feedback clear              delete all feedback
```

## Files, folders, and lock screen

AKKI searches the Desktop, Documents, Downloads, Projects, Code, and Dev folders
by default, including both local and OneDrive variants. Use `:ls` for a quick
Desktop listing, or inspect any path directly:

```text
:ls                        list Desktop
:ls downloads              list Downloads
:file README.md            read text, size, line count, and modified date
:inspect C:\path\to\file  read a file or list a folder
:index desktop             index Desktop for local RAG
:index all                 index every configured search root
lock screen                lock Windows
lock kar do                the same request in Hinglish
screen lock karo           the same request in Hinglish
open folder <path>         open a folder in Explorer
extract info from folder   list a folder's files, sizes, and dates
remember that <fact>       store a long-term memory
store important info in memory for remainder: <fact>
```

Natural-language steps can be chained with `then`:

```text
open folder C:\Projects then extract info from folder C:\Projects then remember that the main project is Finora
```

`:file` and `:inspect` extract text from Markdown, code, JSON, HTML, PDF, DOCX,
PPTX, and XLSX files. Image, audio, and archive files return metadata only.

## Knowledge and web

Index local documents for retrieval-augmented answers. Text, Markdown, code,
JSON, HTML, PDF, DOCX, PPTX, and XLSX files are supported; PDF extraction needs
`pypdf`.

```text
:index                       index the configured search roots
:index C:\path\to\docs       index a specific file or folder
:docs                        list indexed documents
:docs forget <id|path>       remove one document
:docs clear                  clear the whole index
:searchdocs <query>          search indexed chunks
:read <url>                  fetch a page and ask AKKI about it
```

## Scheduling

```text
:schedule every 3600 open notepad
:schedule daily 09:00 open notepad
:schedules
:schedule cancel <id>
```

Schedules are stored in SQLite and run while AKKI is open.

## Multi-step tasks

Use an explicit `then` to chain deterministic actions:

```text
open notepad then take a screenshot
```

Each step must match a local tool. If a step fails, later steps are skipped and
AKKI reports partial completion.

## Installed apps

AKKI discovers Start Menu, desktop, and Store/UWP apps automatically:

```text
:apps
:apps store
open Microsoft Store
open brave
```

The discovery list is cached for the session. Configured aliases in the `apps`
section still take priority, so custom paths and command-line flags keep working.

## Wake word, speakers, and vision

```text
:wake
:wake on|off
:wake phrase hey akki
:active [on|off]
:speaker
:speaker enroll <name> <audio-path>
:speaker forget <name>
:speaker identify <audio-path>
:camera
:face detect <image-b64>
:face enroll <name> <image-b64>
```

Wake-word listening is enabled by default and uses the Whisper stack, so it is CPU-heavy compared with a
dedicated wake detector. Enabling wake also starts the hotkey capture listener
when needed. After the wake phrase, AKKI stays in a continuous voice
conversation: it listens for each follow-up, replies, and listens again until
you say "bye akki" (or "goodbye"). If `voice.conversation_mode` is on, AKKI
starts listening immediately and stays active until the farewell; toggle it
with `:active on|off`. While capture is active, AKKI plays a short pop and
shows a Siri-style glowing orb in the top-right corner. Camera
capture and face detection need `opencv-python`. Face enrollment currently
stores a reference image; it is not CNN identity recognition.

## Web UI

Start a local browser interface:

```text
:ui on
:ui
:ui off
:ui port 8765
```

Or start it with the REPL:

```powershell
akki --ui
```

The UI binds to `127.0.0.1` by default. It has no authentication, so keep it
local. Sensitive actions are denied in the web UI and must be confirmed in the
terminal.

## Desktop panel, access widget, tray, and listening bubble

The desktop UI uses Tkinter for the access widget and settings window, plus
optional `pystray` and Pillow for the tray icon:

```powershell
pip install -e ".[desktop]"
akki --tray --widget
```

```text
:panel                     open the full settings window
:widget                    open the compact desktop access widget
:widget on|off             start/stop it and set autostart
:shortcut                  create the desktop widget shortcut
:tray                      show the tray state
:tray on|off               start or stop the tray icon
```

Create a desktop shortcut for the widget:

```powershell
akki --widget
akki --shortcut
```

The shortcut creates `AKKI Widget.lnk` on the current user Desktop and launches
the hidden-console widget with Python `-m akki.cli --widget-only`.

The compact widget is a small always-on-top window with:

- a mode selector (`sovereign`, `nsfw`, `guarded`)
- IMAP password, ntfy token, and cloud API key fields
- Talk, Test alert, Full settings, and Clear saved buttons
- an option to start the widget with AKKI

Passwords entered in the widget are encrypted with Windows DPAPI and stored in
`%APPDATA%\AKKI\secrets.json`; they are loaded into the process environment at
startup. Existing environment variables still work. The settings panel edits the
content mode, voice, web UI, desktop, alerts, and MCP summary. Changes are saved
to the config and applied to the running session where possible; restart AKKI if
a newly enabled hotkey, wake listener, web server, tray icon, or widget does not
start immediately. The tray menu opens either window.

While the microphone is listening, a small Siri-style orb appears in the
top-right corner. It keeps a soft circular glow with no hard border and uses
gentle sphere shading with a highlight for a three-dimensional feel. Disable it
with `:panel` or by setting `desktop.bubble_enabled` to `false`.

## Mobile alerts

AKKI can push important unseen mail to your phone with `ntfy` and IMAP. Mail is
classified locally first, with cloud fallback only if needed.

Create a private topic with the ntfy mobile app, then configure the panel or
config. Enter the IMAP password and ntfy token in the desktop widget, or use
environment variables:

```powershell
$env:AKKI_NTFY_TOKEN = "..."       # optional for a protected ntfy topic
$env:AKKI_IMAP_PASSWORD = "..."    # IMAP app password, never written to config
```

```text
:alerts                    show alert settings and recent decisions
:alerts on|off             enable or disable mail checking
:alerts topic <topic>      set the ntfy topic
:alerts test               send a test phone notification
:alerts check              check important unseen mail now
:alert <text>              send a manual phone notification
```

IMAP defaults to `INBOX` on port 993 with SSL. The poll interval and importance
threshold are editable in `:panel`. Already-processed messages are remembered in
SQLite so they are not sent twice.

## MCP

AKKI includes a stdio MCP client. Add servers to the config:

```json
"mcp_servers": {
  "filesystem": {
    "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\you\\Documents"],
    "env": {},
    "enabled": true,
    "timeout_seconds": 15
  }
}
```

Load and inspect them at runtime:

```text
:mcp
:mcp reload
:mcp stop
```

Read-only MCP tools are exposed as read-only actions. Tools without a read-only
hint require confirmation. Only stdio transport is supported.

## Commands

```text
:tools                       list registered tools
:apps [search]               list installed Start Menu and Store apps
:ls [folder]                 list a folder with sizes and dates
:file <file>                 read a local file
:inspect <file|folder>       read a file or list a folder
:alerts                      show mobile alert status
:alerts check                check important mail now
:alert <text>                send a manual phone alert
:panel                       open the desktop settings window
:widget                      open the desktop access widget
:widget on|off               start/stop it and set autostart
:tray on|off                 start or stop the tray icon
:shortcut                    create the desktop widget shortcut
:mode nsfw|sovereign|guarded change the content mode
:llm                         show local and cloud model settings
:remember <fact>             store a persistent memory
:memories                    list memories
:forget <id>                 delete a memory
:cache                       show response cache stats
:cache clear                 drop cached responses
:listen                      record a command, Enter to stop
:say <text>                  speak text aloud
:index [path|desktop|all]    index documents for local RAG
:docs                        list indexed documents
:searchdocs <query>          search indexed documents
:read <url>                  read and summarize a web page
:schedule every <seconds> <command>
:schedule daily <HH:MM> <command>
:schedules                   list scheduled jobs
:schedule cancel <id>        remove a scheduled job
:wake on|off                 enable or disable wake-word listening
:speaker                     list enrolled speakers
:ui                          show the local web UI state
:mcp                         show configured MCP servers
:mcp reload                  start MCP servers and register tools
:logs                        show the audit log path
:config                      show the config path
:db                          show the database path
:help                        show command help
:quit                        exit
```

Natural-language requests are routed to tools when they match. Unmatched text is
sent to the local model first, then to cloud fallback.

## Files and privacy

- Config: `%APPDATA%\AKKI\config.json`
- Encrypted secrets: `%APPDATA%\AKKI\secrets.json` (Windows DPAPI)
- Database: `%APPDATA%\AKKI\akki.db`
- Logs: `%APPDATA%\AKKI\akki.log` (rotated, tool outcomes only; chat text is not logged)
- Piper models and binaries: `%APPDATA%\AKKI\models\piper`, `%APPDATA%\AKKI\bin\piper`
- Whisper models: `%APPDATA%\AKKI\models\whisper`

Override paths with `AKKI_DB` and `AKKI_PIPER`. Microphone sensitivity can be
tuned with `AKKI_MIC_THRESHOLD` (default `300`).

Cloud fallback sends the request, recent conversation, memories, and learned
feedback to the configured provider. Mobile alerts send the sender, subject, and
preview to the ntfy server; importance classification runs locally first and can
fall back to the configured cloud provider. Local tools run on-device. Do not put
API keys in the config file or commit them to the repository. Secrets entered in
the desktop widget are encrypted with Windows DPAPI in `secrets.json`; the config
only stores the environment-variable names.

AKKI allows profanity, roasting, and dark humour in every supported language.
Illegal material, sexual content involving minors, and non-consensual or coerced
acts remain hard limits.

## Tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

GitHub Actions runs the same suite on Windows with Python 3.11.

## Current limits

- The local 3B model is weak at long-form Hindi, Bhojpuri, and Marathi prose.
- Wake-word detection uses Whisper transcription rather than a dedicated wake
  model, so it costs more CPU.
- Camera and face detection need `opencv-python`; stored faces are reference
  images, not CNN identity embeddings.
- The web UI is local-only and unauthenticated. Sensitive actions require the
  terminal.
- MCP supports stdio servers only; remote HTTP transports are not implemented.
- Windows toast/notification capture is not implemented. AKKI forwards important
  IMAP mail and explicit `:alert` / `mobile_alert` notifications; arbitrary
  Windows notifications are not mirrored yet.
- The tray icon needs `pystray` and Pillow (`.[desktop]`); the settings panel only
  needs Tkinter.
- Browser automation and image generation are not implemented.
- Volume changes and shell-opened documents cannot be independently verified.
