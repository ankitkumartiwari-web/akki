# ODIN

ODIN is a local-first Windows desktop assistant. It runs deterministic tools
without a model, uses a local Ollama model when available, and falls back to an
OpenRouter model for harder requests. Voice input and output support English,
Hindi, Marathi, Bhojpuri (through the Hindi voice), Malayalam, Telugu, and Urdu.

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
pip install -e ".[voice,dev]"
```

Start ODIN:

```powershell
odin
```

If the `odin` command is not on `PATH`, use:

```powershell
.\.venv\Scripts\python -m odin.cli
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
:voice use piper|sapi        choose the synthesis engine
:voice on|off                toggle spoken replies
```

Hindi, Marathi, and other Indian-language models download on first use.
Bhojpuri uses the Hindi voice because no dedicated Piper Bhojpuri model exists.

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

## Feedback learning

ODIN stores reward and punishment signals locally and injects them into future
prompts. This adapts tone and length without retraining model weights.

```text
:good short and direct       reward the last reply
:bad too long                punish the last reply
:feedback                    show score and recent notes
:feedback clear              delete all feedback
```

## Commands

```text
:tools                       list registered tools
:llm                         show local and cloud model settings
:remember <fact>             store a persistent memory
:memories                    list memories
:forget <id>                 delete a memory
:cache                       show response cache stats
:cache clear                 drop cached responses
:listen                      record a command, Enter to stop
:say <text>                  speak text aloud
:logs                        show the audit log path
:config                      show the config path
:db                          show the database path
:help                        show command help
:quit                        exit
```

Natural-language requests are routed to tools when they match. Unmatched text is
sent to the local model first, then to cloud fallback.

## Files and privacy

- Config: `%APPDATA%\ODIN\config.json`
- Database: `%APPDATA%\ODIN\odin.db`
- Logs: `%APPDATA%\ODIN\odin.log` (rotated, tool outcomes only; chat text is not logged)
- Piper models and binaries: `%APPDATA%\ODIN\models\piper`, `%APPDATA%\ODIN\bin\piper`
- Whisper models: `%APPDATA%\ODIN\models\whisper`

Override paths with `ODIN_DB` and `ODIN_PIPER`. Microphone sensitivity can be
tuned with `ODIN_MIC_THRESHOLD` (default `300`).

Cloud fallback sends the request, recent conversation, memories, and learned
feedback to the configured provider. Local tools run on-device. Do not put API
keys in the config file or commit them to the repository.

ODIN allows profanity, roasting, and dark humour in every supported language.
Illegal material, sexual content involving minors, and non-consensual or coerced
acts remain hard limits.

## Tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

## Current limits

- The local 3B model is weak at long-form Hindi, Bhojpuri, and Marathi prose.
- Wake-word detection, speaker recognition, camera/vision, a tray UI, browser
  automation, and MCP integrations are not implemented yet.
- Volume changes and shell-opened documents cannot be independently verified.
