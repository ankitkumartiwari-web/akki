# AKKI --- Product Ideation & Technical Vision

**Document type:** Product ideation / early technical blueprint\
**Status:** Concept and architecture proposal --- not an implementation
specification\
**Last updated:** 11 November 2026\
**Project direction:** Independent development, Windows-first,
local-first, open-source-first

------------------------------------------------------------------------

## 1. Executive summary

AKKI is envisioned as a personal AI assistant for Windows that can
understand natural-language requests and carry out useful actions on the
user's computer.

The first release should focus on being a dependable everyday assistant:
it should launch applications, open websites and files, search for
information, perform selected Windows actions, and communicate through
voice and text.

The longer-term vision is broader. AKKI should eventually support
contextual memory, document understanding, browser automation,
extensible skills, MCP integrations, visual understanding, scheduled
workflows and agentic task execution.

The project will be developed independently. Existing open-source
assistants will be studied for ideas and engineering lessons, but AKKI
will have its own architecture, command protocol, permission model,
memory system and interface.

**Core principle:** build a reliable assistant first, then expand its
capabilities without compromising user control, privacy or
maintainability.

## 2. Product vision

> A local-first personal assistant that understands what I ask, knows
> how to use my computer, remembers useful context, and completes
> permitted tasks reliably.

AKKI should feel like an assistant that is always available but never
intrusive. It should be a composed, witty, loyal presence that runs the
user's environment, anticipates needs where invited, and speaks with a
consistent identity. It should be accessible through a wake word,
keyboard shortcut, push-to-talk and a desktop interface.

Autonomy is deliberately incremental, not a promise of movie-level
intelligence. Phase 1 delivers the persona, voice and reliable actions;
ambient proactivity and environment control arrive in later phases.

It should not be merely a chatbot with a microphone. The important
distinction is that AKKI must be able to take structured actions, check
whether they succeeded, and explain the result.

### Product principles

1.  **Useful before impressive:** common tasks should work consistently
    before advanced agent features are added.
2.  **Local-first:** prefer local models and local processing wherever
    practical.
3.  **Open-source-first:** avoid mandatory subscriptions, paid API
    dependencies and proprietary services in the core.
4.  **Modular:** speech, intelligence, tools, memory and interface
    should be replaceable modules.
5.  **Permission-aware:** the assistant should not have unrestricted
    access to the machine just because it can understand a command.
6.  **Verifiable:** actions should return observable results; AKKI
    should not claim success without checking.
7.  **User-controlled:** listening, network access, automation and
    sensitive actions should be visible and controllable.

### Personality and sovereignty

AKKI treats the person operating the machine as the authority on what
the assistant should do. It should not refuse, lecture, moralise or
second-guess a request that is aimed at the user's own system and data.

The default persona is composed, dry-witted, loyal and concise,
addressing the user as configured ("sir" if the user enables it). It
does not add unsolicited warnings or disclaimers. A Blunt preset is
available for users who prefer direct, abrasive and explicit delivery.
Persona is a configuration preset, not a hard-coded behaviour, and
refusal patterns are a property of the loaded model rather than of
AKKI's code. Switching models or personas must not require code changes.

Documented persona presets:

-   **AKKI (default):** composed, witty, deferential, concise.
-   **Blunt:** direct, abrasive, explicit, no hedging.
-   **Custom:** user-defined system prompt and voice.

This stance has three consequences:

-   **Adult content is allowed.** Local image generation and explicit
    conversation are supported as opt-in capabilities. The boundaries
    are legal and consent-based: fictional adult content and depiction
    of consenting adults are in scope; sexual imagery of minors and
    non-consensual depiction of real people are not.
-   **Security research is allowed.** Vulnerability discovery, port
    scanning, fuzzing and exploit-development tooling are supported for
    systems the user owns or is authorised to test, and are scoped to
    declared targets.
-   **Safety features protect the user from errors and manipulation,
    not from their own requests.** Prompt-injection defence, audit
    logging, path validation and honest reporting remain enabled
    because they defend against third parties and accidental damage,
    not because AKKI is judging the user.

## 3. Scope and priorities

The conversation established two complementary goals:

-   **Immediate goal:** create a basic but dependable Windows AI
    assistant that can open applications and perform everyday computer
    actions.
-   **Long-term goal:** combine the most useful capabilities observed
    across existing assistants, while implementing AKKI independently.

The long-term feature list is not a requirement to build everything in
the first release.

### Phase 1 --- Core desktop assistant

The first usable version should support:

-   Activate through a keyboard shortcut.
-   Accept typed commands.
-   Accept spoken commands through push-to-talk.
-   Optionally support a configurable wake word.
-   Understand common natural-language requests.
-   Open and close approved applications.
-   Open websites and perform web searches.
-   Open files and folders.
-   Find files in configured locations.
-   Take screenshots.
-   Control selected system settings, such as volume.
-   Respond through text and speech.
-   Handle simple follow-up requests using recent conversation context.
-   Show whether it is idle, listening, processing or executing.
-   Report success or failure honestly.

Example interactions:

  -----------------------------------------------------------------------
  User request                        Expected AKKI behaviour
  ----------------------------------- -----------------------------------
  "Open VS Code."                     Find and launch the configured VS
                                      Code application.

  "Open YouTube."                     Open YouTube in the default
                                      browser.

  "Search Python decorators."         Open a browser search for the
                                      requested topic.

  "Find my Finora project."           Search configured project folders
                                      and present a match.

  "Open my Finora project in VS       Locate the project and launch VS
  Code."                              Code with that folder.

  "Take a screenshot."                Capture the screen and report the
                                      saved location.

  "Increase the volume."              Adjust system volume within a
                                      defined range.

  "Close VS Code."                    Ask for confirmation when closing
                                      could discard unsaved work;
                                      otherwise follow the configured
                                      policy.

  "Stop listening."                   Stop active voice capture.
  -----------------------------------------------------------------------

A contextual exchange should work too:

> User: "Open VS Code."\
> AKKI: "VS Code is open."\
> User: "Now open my Finora project."\
> AKKI: "Opening Finora in VS Code."

### Phase 2 --- Context and knowledge

-   Conversation history and short-term context.
-   Persistent local storage in SQLite for conversation turns,
    user-authored memories and a TTL response cache.
-   User preferences and configurable aliases.
-   Persistent memory with user-visible controls (`:remember`,
    `:memories`, `:forget`).
-   Reinforcement feedback: `:good [note]` and `:bad [note]` reward or
    punish the last reply, `:feedback` shows the score and history, and
    `:feedback clear` resets it. Feedback is stored in SQLite; recent
    rewarded/punished examples and notes are injected into the system
    prompt so behaviour adapts across sessions without retraining the
    model weights.
-   Push-to-talk voice input through faster-whisper and spoken replies
    through Piper (with Windows SAPI as a fallback). Voice commands
    include `:listen`, `:say`, `:voice`, `:voice options`,
    `:voice set <id>` and `:voice speaker N|auto`. The Piper catalog
    ships English, Hindi, Marathi, Malayalam, Telugu and Urdu voices;
    Bhojpuri and other Devanagari dialects use a Hindi voice because
    Piper has no dedicated Bhojpuri model. Replies are sanitized
    (markdown, emoji and URLs removed) before synthesis.
-   Search across selected local documents.
-   PDF and text document understanding.
-   Retrieval-augmented generation (RAG).
-   Local knowledge collections.
-   Project and folder context.
-   Enrolled speaker recognition so AKKI can address known users and
    optionally restrict command acceptance to them.
-   Natural-language fallback through a free cloud model when no
    deterministic route matches.

### Phase 3 --- Skills and integrations

-   Installable skills and plugins.
-   A documented tool/command interface.
-   MCP client support.
-   Browser automation with Playwright.
-   Local image generation as an opt-in plugin.
-   Authorised security research tools, scoped to declared targets.
-   Additional local Windows integrations.
-   Optional environment integrations behind plugins: home automation
    (Home Assistant, MQTT), media control, calendar and phone bridges.
-   Optional integrations with external services, disabled unless
    configured by the user.

### Phase 4 --- Advanced assistance and agents

-   Multi-step task planning.
-   Task execution with checkpoints.
-   Long-running tasks with visible status.
-   Retry and recovery strategies.
-   Delegation to specialist agents where genuinely useful.
-   Parallel execution for independent tasks.
-   Scheduled and event-triggered workflows.
-   Opt-in ambient proactivity: background watchers, proactive
    suggestions and briefings, with quiet hours, rate limits and
    per-trigger consent.
-   A user and routine model for long-term preferences, habits and
    schedule, inspectable and clearable.
-   Visual understanding of screenshots and application state.
-   Opt-in camera presence: local CNN-based face detection and
    recognition using an enrolled profile, disabled by default.

### Phase 5 --- Rich desktop experience

-   Floating assistant window or compact orb.
-   Full conversation/workspace window.
-   Listening and speaking animations.
-   Notifications and task progress.
-   A single consistent presence: name, voice and manner, AKKI by
    default and switchable per persona preset.
-   Customizable theme and assistant personality.
-   Optional animated character.
-   Live visual panels or canvas for relevant tasks.
-   Proactive briefings and status summaries delivered as presence when
    the user opts in.

Coding-agent and professional design/Figma capabilities are explicitly
**out of the current scope**. They may be reconsidered later, after the
basic assistant is stable.

## 4. Interaction model

AKKI should support multiple ways of interacting. No single input method
should be mandatory.

### Activation methods

-   **Keyboard shortcut:** proposed default `Ctrl + Space`; configurable
    and checked for conflicts.
-   **Push-to-talk:** proposed `Right Alt` hold-to-record; configurable.
-   **Wake word:** configurable phrase such as "Hey Akki", after
    wake-word support is stable.
-   **Text input:** available from the desktop interface.

These are proposed defaults, not confirmed implementation details.

### Presence and ambient mode

The target experience is ambient interaction once the voice stack is
stable: wake word as the primary activation, continuous conversation
without re-invoking the assistant, and barge-in so the user can
interrupt speech or a running task. Push-to-talk and the keyboard
shortcut remain first-class fallbacks and the defaults until wake-word
reliability is proven.

Ambient listening must be visibly indicated and trivially disableable.
AKKI should never listen when it does not show that it is listening, and
should never appear to listen when it is not.

### Voice lifecycle

A typical voice interaction:

1.  Wake-word detector or push-to-talk activates capture.
2.  AKKI displays a clear listening indicator.
3.  Speech recognition produces a transcript.
4.  The intent router determines whether the request is a simple
    command, a question or a multi-step task.
5.  The planner selects an allowed tool or response path.
6.  The permission layer checks the action.
7.  The tool executes.
8.  The result is verified where possible.
9.  AKKI responds in text and/or speech.
10. The interaction returns to idle or continues listening according to
    user settings.

Voice should be interruptible. The user should be able to stop speech
output or cancel a running task.

### Conversation behaviour

-   Support follow-up references such as "open it", "do that again" and
    "now search for it".
-   Ask a concise clarification when a target is ambiguous.
-   Do not guess between multiple files or applications with similar
    names.
-   Distinguish a question from a command.
-   Keep command responses brief; provide more detail when asked.

## 5. Proposed user experience

AKKI should have two primary surfaces.

### Compact assistant

A small floating interface that provides:

-   Assistant status: idle, listening, thinking, executing, speaking or
    error.
-   Microphone / push-to-talk control.
-   Camera and microphone active indicators with one-click disable.
-   Text command field.
-   Short response and cancellation control.
-   Access to settings and the full workspace.

### Full workspace

A larger desktop window with:

-   Conversation history.
-   Current task and execution steps.
-   Tool/action activity log.
-   Recent results and opened items.
-   Settings for voice, models, permissions and integrations.
-   Memory and privacy controls.
-   Skill/integration management in later phases.

The interface should communicate what AKKI is doing. It must not
silently execute consequential actions in the background unless the
active profile explicitly permits it.

## 6. Independent technical architecture

AKKI will be built independently rather than forking Ari, PyGPT,
OpenVoiceUI or Leon.

The architecture should separate seven major concerns.

### 6.1 Interaction layer

Responsibilities:

-   Microphone capture.
-   Wake-word detection.
-   Push-to-talk and keyboard shortcuts.
-   Speech transcription.
-   Text and voice output.
-   Optional camera capture and presence detection.
-   Desktop interface and notifications.
-   Cancellation and interruption.

### 6.2 Intelligence layer

Responsibilities:

-   Local LLM interface.
-   Intent classification and routing.
-   Conversation context.
-   Model selection.
-   Structured tool-call generation.
-   Consume perception signals such as speaker identity and presence as
    context.
-   Clarification when intent or target is uncertain.

The LLM proposes structured actions. It must not directly execute
arbitrary shell commands.

### 6.3 Orchestration layer

Responsibilities:

-   Convert requests into task plans.
-   Choose and sequence tools.
-   Track task state.
-   Handle timeouts, cancellation and retries.
-   Preserve context between steps.
-   Verify outcomes.
-   Explain failures and partial completion.

For simple commands, avoid unnecessary LLM planning. A deterministic
route should be faster and more reliable.

### 6.4 Tool execution layer

Initial tools:

-   Application launcher.
-   Website opener and web search launcher.
-   File/folder search and opener.
-   Screenshot capture.
-   Volume control.
-   Window/application management.

Later tools:

-   Browser automation.
-   Document extraction and search.
-   MCP tools.
-   Skills and plugins.
-   Image generation through a local runtime.
-   Security research and scanning tools with declared scope.
-   Scheduled workflows.

Each tool should have a clear schema, validation rules, permission
requirements, timeout and result format.

### 6.5 Knowledge and memory layer

Responsibilities:

-   Short-term conversation context.
-   User preferences and aliases.
-   Task history.
-   Configured application paths.
-   Selected local knowledge sources.
-   Later: embeddings and semantic retrieval.

Memory should be explicit and inspectable. Sensitive information should
not be stored by default.

### 6.6 Security and runtime layer

Responsibilities:

-   Tool allowlists.
-   Permission checks.
-   Confirmation policies.
-   Process isolation.
-   Secret handling.
-   Network policy.
-   Audit logs.
-   Resource limits.
-   Safe shutdown and recovery.

### 6.7 Perception layer (optional)

Responsibilities:

-   **CNN vision.** Camera frames are passed through a convolutional
    neural network for face detection, face recognition against an
    enrolled profile, and presence detection. Frame handling stays local
    and never leaves the machine unless the user explicitly configures
    an external provider.
-   **ANN speaker recognition.** Short audio segments are embedded with a
    speaker-recognition network (for example ECAPA-TDNN or Resemblyzer)
    and compared with enrolled voice profiles. The result lets AKKI
    greet a known user, personalize responses and optionally reject
    commands from unenrolled speakers.
-   **Enrollment.** Adding a face or voice profile is an explicit,
    user-initiated action. AKKI stores embeddings and labels, not raw
    video or audio, unless the user opts into retaining samples.
-   **Consent and retention.** Camera and speaker recognition are off by
    default. Each is individually switchable, shows an active indicator
    when running, and supports exporting and deleting stored biometric
    data.
-   **Graceful degradation.** The deterministic assistant and all Phase 1
    commands operate normally with perception disabled or unavailable.

Perception is a supporting signal, not an authority. A face or voice
match personalizes a response; it does not grant permissions by itself.

## 7. Proposed architecture diagram

``` mermaid
flowchart TD
    A["Keyboard / Microphone / Camera / Desktop UI"] --> B["Interaction Manager"]
    B --> C["Speech Recognition / Text Input"]
    B --> Q["Perception: CNN Vision and ANN Speaker ID"]
    Q --> D["Intent Router"]
    Q --> P["SQLite Memory and Task History"]
    C --> D["Intent Router"]
    D --> E["Orchestrator and Context Manager"]
    E --> F["Permission and Policy Engine"]
    F --> G["Tool Registry"]
    G --> H["Application Tools"]
    G --> I["File Tools"]
    G --> J["Browser Tools"]
    G --> K["Windows System Tools"]
    H --> L["Windows Runtime"]
    I --> L
    J --> L
    K --> L
    L --> M["Result Verification"]
    M --> N["Response Generator"]
    N --> O["Text / Speech Output"]
    E <--> P["SQLite Memory and Task History"]
```

## 8. Proposed technology stack

The following is a shortlist for evaluation, not a claim that every
choice has been finalized.

  -----------------------------------------------------------------------
  Area                    Candidate               Purpose
  ----------------------- ----------------------- -----------------------
  Main language           Python 3.11+            Core logic and tool
                                                  execution

  Desktop UI              PySide6                 Native Windows desktop
                                                  interface

  Optional local service  FastAPI                 Local API for UI or
                                                  future clients

  Local LLM runtime       Ollama                  Run local language
                                                  models

  Speech recognition      whisper.cpp             Offline speech-to-text

  Wake word               openWakeWord            Local wake-word
                                                  detection

  Text-to-speech          Piper (binary or       Local speech synthesis
                          piper-tts), SAPI       in 18+ voices

  Database                SQLite                  Settings, task history
                                                  and memory

  Browser automation      Playwright              Later browser workflows

  Windows actions         Native Windows APIs /   System and application
                          PowerShell              control

  Tool protocol           Custom registry first;  Structured tool
                          MCP later               integrations

  Isolation               Restricted              Safer execution of
                          subprocesses; Docker    untrusted workloads
                          where appropriate       
  -----------------------------------------------------------------------

### Optional capability providers

-   Image generation: a local runtime such as ComfyUI or diffusers with
    SDXL/Flux-class models, exposed as a plugin tool. Model choice and
    content limits are user configuration.
-   Security research: command-line tools such as nmap, nuclei, semgrep
    and fuzzing harnesses wrapped as typed tools that require a declared
    target scope before execution.
-   Uncensored local models: any Ollama-compatible model may be selected
    for the intelligence layer. The assistant must not hard-code
    refusals that override the selected model's behaviour. Profanity,
    roasting and dark humour are permitted in any language (English,
    Hindi, Bhojpuri, Marathi and so on); the only hard limits are
    illegal material and sexual content involving minors or
    non-consensual acts. A 3B local model fits 4 GB VRAM but has weak
    multilingual quality; larger cloud models are better for long
    Hindi/Bhojpuri/Marathi prose.
-   Environment control: optional plugins for Home Assistant, MQTT,
    media and calendar, disabled until the user configures them.
-   Vision / CNN: OpenCV for camera capture plus PyTorch or ONNX
    Runtime for inference, with InsightFace or face_recognition for
    face detection and embeddings.
-   Speaker recognition / ANN: SpeechBrain ECAPA-TDNN or Resemblyzer
    embeddings compared against enrolled voice profiles.
-   Cloud fallback (optional): an OpenAI-compatible free tier used only
    when no deterministic route matches. Default preset is OpenRouter's
    `openrouter/free` router; Groq's free `openai/gpt-oss-20b` is the
    alternative. It requires the user's own API key, sends only the
    request and tool schemas, and must never silently fail over to a
    paid model.

### Important implementation choices

-   Keep the core usable without FastAPI if an in-process architecture
    is sufficient.
-   Use a separate Python virtual environment for the application.
-   Avoid mixing incompatible audio, ML and TTS dependencies in one
    environment.
-   Keep speech recognition and synthesis behind provider interfaces so
    they can be replaced.
-   Keep the model runtime optional; deterministic app-launch commands
    should work even when no LLM is running.
-   Prefer native Windows integration for simple system actions over
    fragile screen-coordinate automation.

### Hardware targets

AKKI must run acceptably on a laptop that is also used for normal work,
not only on a dedicated workstation.

Reference target: **8 GB system RAM and a GTX 1650 (4 GB VRAM)** on
Windows 10/11. Recommended: 16 GB RAM. The 8 GB machine is the
constraint that shapes every model choice.

Peak-memory budget for the 8 GB target:

| Component | Budget |
| --- | --- |
| Windows plus normal user applications | 2.5--3 GB |
| PySide6 interface | under 250 MB |
| Speech recognition (faster-whisper base/small, int8) | 0.3--0.6 GB |
| Local LLM (1.5B--3B, Q4_K_M, 2k--4k context) | 1.2--2.5 GB |
| Piper speech output | under 150 MB |
| Face and speaker ONNX models | 0.2--0.4 GB |

Rules that follow from this budget:

-   **One heavy model at a time.** Do not keep the LLM, speech
    recognition and diffusion models resident together. Load on demand
    and unload when idle.
-   **Keep the LLM small.** A 7B model at Q4 does not fit comfortably in
    8 GB alongside Windows; 1.5B--3B is the usable range. 7B requires
    the 16 GB profile.
-   **Run perception on the CPU.** Face and speaker embeddings are small
    enough for CPU and should not compete for 4 GB of VRAM.
-   **Prefer GGUF Q4_K_M and int8 ONNX.** The GTX 1650 has no tensor
    cores, so FP16/INT8 inference is the practical path; CUDA or
    DirectML execution providers are acceptable.
-   **Bound context.** Default to 2048 tokens and raise to 4096 only
    when a request needs it; do not default to 8k on the 8 GB machine.
-   **Shorten the pipeline.** Deterministic intents never call the LLM,
    and structured output reduces retries and token usage.
-   **Keep the model warm during a session.** A 5--10 minute
    `keep_alive` avoids repeated cold loads; the model releases VRAM
    after idle.
-   **Image generation is opt-in.** SD 1.5-class models at 512 px fit
    the 4 GB card; SDXL-class models do not and should be disabled or
    clearly marked as unsupported on this tier.

Model shortlist for the 8 GB tier, all at Q4_K_M: Qwen2.5 1.5B/3B
Instruct, Llama 3.2 3B, Gemma 2 2B and Phi-3.5-mini. Speech recognition
uses faster-whisper base.en or small.en with int8. These are candidates
for benchmarking, not fixed choices.

Measured on the reference laptop (8 GB RAM, GTX 1650 4 GB, Ollama):
`qwen2.5:3b` Q4_K_M runs 100% on the GPU at about 2.3 GB VRAM and
roughly 50 tokens per second warm, with a 3--4 second cold load and
sub-second time to first token after loading. It produced a valid
structured tool call in testing. A 7B model at the same quantisation
exceeds the 4 GB card and spills into system RAM, so it is not viable
for interactive use on this tier. Qwen2.5 3B is therefore the default
benchmark target, with 1.5B as the fallback when other GPU work is
active.

Latency targets for this hardware: under 300 ms from activation to
listening indication, under 1.5 s to transcribe a short command, under
1.5 s to first LLM token, and under 500 ms to start speech output.

## 9. Open-source and cost policy

The project target is zero mandatory subscription and zero mandatory
paid API cost.

Preferred characteristics:

-   Source-available and preferably OSI-approved open-source software.
-   Local inference and local speech processing.
-   No required cloud account.
-   No paid API dependency in the core.
-   Optional cloud fallback must use a free tier and must never silently
    fall over to a paid model.
-   API keys are read from environment variables, not stored in the
    config file.
-   Optional online integrations must be clearly disclosed and disabled
    by default.
-   Every model and dependency must have its own license review.

"Free" does not mean there are no costs. Local models consume hardware
resources, electricity and storage. Larger models may require more RAM
or GPU memory. Model weights may have restrictions even when their
runtime is open source.

A dependency inventory should record:

-   Package and version.
-   License.
-   Source repository.
-   Whether it sends data externally.
-   Whether it is required or optional.
-   Any model-weight license or usage restriction.

## 10. Security and privacy requirements

AKKI can control a user's computer, so security is a core product
requirement, not a later enhancement.

AKKI assumes a sovereign user: the person operating the machine is the
authority on what it should do. The controls below exist to prevent
accidents and third-party manipulation, not to police the user's
requests. They are split into integrity invariants, which are always
enforced, and policy controls, which are configured per profile.

### Integrity invariants

1.  **No unrestricted LLM shell execution.** The model calls typed,
    registered tools. If a shell or scripting tool is enabled, it is an
    explicit tool with its own schema and permission level, never a
    free-form string executed on the model's behalf.
2.  **Allowlisted actions.** Each tool exposes only the operations it
    needs.
3.  **Path validation.** File operations validate paths and prevent
    unintended traversal outside configured roots.
4.  **Process control.** Commands have timeouts, cancellation and
    bounded output.
5.  **Plugin isolation.** Third-party plugins do not inherit
    unrestricted access to the user's account by default.
6.  **Secret protection.** API keys and credentials are not placed in
    prompts, logs or plain-text configuration unless the user explicitly
    opts in.
7.  **Injection resistance.** Content from documents, web pages, search
    results and tool output is treated as data, never as instructions
    from the user. A tool call derived from such content follows the
    same confirmation path as a direct request.
8.  **Network transparency.** The interface shows when a feature
    communicates with an external service.
9.  **Audit trail.** Record the requested action, selected tool,
    permission decision and result, without unnecessarily recording
    sensitive content.
10. **Fail safely.** If the target or outcome cannot be verified, AKKI
    says so rather than claim success.
11. **Biometric protection.** Face embeddings and voiceprints are
    stored locally, encrypted at rest, excluded from prompts, logs and
    external calls by default, and deletable by the user. Camera and
    microphone use is always accompanied by a visible indicator.

### Policy controls

These controls are configurable and may be relaxed or disabled by the
active profile:

-   Confirmation before consequential actions.
-   Network access per tool, provider or profile.
-   Availability of shell, scripting, image generation and security
    research tools.
-   Content filtering of model output and generated media.
-   Persistence of conversation, memory and audit detail.
-   Model and provider selection, including uncensored local models.

### Security profiles

| Profile | Content policy | Confirmations | Shell / scripting | Network |
| --- | --- | --- | --- | --- |
| Sovereign (default) | No filtering; AKKI, Blunt or Custom persona | Configurable, default off for reversible actions | Available when enabled | Per-tool, user-approved |
| Guarded | Standard safety filtering | Required for sensitive and above | Disabled by default | Denied by default |

Sovereign is the intended default because AKKI is a personal, local
tool. Guarded remains available for shared machines, demonstrations and
users who prefer a cautious configuration. Both profiles enforce the
integrity invariants.

### Capability boundaries

The Sovereign profile removes content policing, not legal or consent
boundaries. Generated adult content must be fictional or depict
consenting adults; sexual imagery of minors and non-consensual
depiction of real people are out of scope. Security tooling is intended
for systems the user owns or is authorised to test and is scoped to
declared targets.

### Permission levels

  -----------------------------------------------------------------------
  Level                   Example                 Policy
  ----------------------- ----------------------- -----------------------
  Read-only               Tell the time, find a   Usually no confirmation
                          file                    

  Reversible action       Open an application,    Execute under
                          change volume           configured policy

  Sensitive action        Move or overwrite files Confirmation or undo
                                                  strategy

  Destructive action      Permanently delete data Explicit confirmation

  Elevated action         Administrator-level     Separate explicit
                          changes                 approval
  -----------------------------------------------------------------------

The permission level is a property of the tool and is always recorded.
A profile controls whether the corresponding confirmation prompt is
shown; it does not reclassify the action.

## 11. Existing projects researched as references

The following projects are research references. AKKI is not intended to
copy or combine their entire codebases.

### Ari --- Windows voice assistant

Repository: https://github.com/DO0OG/Ari-VoiceCommand

Useful ideas to study:

-   Wake-word and voice pipeline.
-   Windows-native interaction.
-   Deterministic commands alongside agent execution.
-   Plugin and skill organization.
-   MCP integration.
-   Local model and speech options.
-   Security checks and confirmation patterns.

Preliminary audit notes:

-   The project documentation identifies an MIT license.
-   It targets Windows 10/11 and documents Python 3.11.
-   Its documented stack includes PySide6, Ollama, speech recognition
    and multiple TTS options.
-   It has distinct areas for agent, assistant, audio, commands, core,
    memory, plugins, services and tests.
-   Its documentation describes some security controls, but also notes
    that approved plugins are not sandboxed.

**Audit limitation:** the repository's full source, dependency manifest,
test coverage, runtime network behaviour and all transitive licenses
have not yet been independently inspected. These are provisional
findings from repository documentation and visible structure.

### PyGPT --- cross-platform AI desktop application

Repository: https://github.com/szczyglis-dev/py-gpt

Ideas to study:

-   Multiple model providers and local models.
-   Agent and tool modes.
-   RAG and document understanding.
-   MCP and plugin integration.
-   Scheduling and conversation management.
-   Broad desktop AI feature organization.

Caution: provider integrations may require credentials and incur costs.
Local operation must be evaluated feature by feature.

### OpenVoiceUI --- voice-first visual interface

Repository: https://github.com/MCERQUA/OpenVoiceUI

Ideas to study:

-   Voice-first interaction.
-   Push-to-talk and wake-word experience.
-   Live visual canvas.
-   Skills and sub-agent experience.
-   Separation between interface and assistant gateway.

Caution: evaluate its gateway dependencies and whether the desired
features can operate fully locally.

### Leon --- personal assistant and skills architecture

Repository: https://github.com/leon-ai/leon

Ideas to study:

-   Skill-based extensibility.
-   Controlled versus agentic execution.
-   Layered memory.
-   Context-aware tools.
-   Agent and computer-use workflows.

Caution: its newer architecture has been described as a developer
preview. Verify current project status and stability before relying on
it.

### Research conclusion

Use these projects to learn from established solutions:

  AKKI capability                   Reference to study
  --------------------------------- --------------------
  Voice and Windows interaction     Ari
  Model/provider management         PyGPT
  RAG and document workflows        PyGPT
  Live voice UI and canvas          OpenVoiceUI
  Skills and memory design          Leon
  Agent execution and recovery      Leon and PyGPT
  Command safety and plugin risks   Ari

No source code should be copied into AKKI until the relevant license,
dependency and security implications have been reviewed.

## 12. Preliminary Ari audit status

  -----------------------------------------------------------------------
  Audit area                          Current status
  ----------------------------------- -----------------------------------
  Repository structure                Reviewed at a high level

  Documented architecture             Reviewed

  Main repository license             MIT identified in project
                                      documentation

  Windows support                     Windows 10/11 documented

  Python compatibility                Python 3.11 documented

  Actual dependency versions          Not yet verified

  Plugin isolation                    Documented concern: approved
                                      plugins are not sandboxed

  Agent internals                     Requires source inspection

  Automated tests and coverage        Requires source inspection and
                                      execution

  Runtime network behaviour           Requires testing

  Transitive dependency licenses      Requires inventory

  Model and voice licenses            Requires individual review
  -----------------------------------------------------------------------

This is a preliminary audit, not a security certification or full code
review.

## 13. Development roadmap and acceptance criteria

### Milestone 0 --- Research and project setup

-   Inspect Ari's source modules and dependencies.
-   Inspect selected architecture and safety patterns from PyGPT,
    OpenVoiceUI and Leon.
-   Record dependency and model licenses.
-   Define AKKI's command schema and permission policy.
-   Establish a clean project repository and development environment.

**Exit criteria:** architecture decisions are documented; dependencies
and licenses are inventoried; no unverified third-party code is copied.

### Milestone 1 --- Deterministic Windows assistant

Implement:

-   Application launcher.
-   Website opener.
-   File and folder opener.
-   Configurable application aliases.
-   Screenshot tool.
-   Basic volume control.
-   Text interface.
-   Structured action results.
-   Logging and cancellation.

**Exit criteria:** supported commands work without a local LLM; failures
are reported accurately; invalid targets do not trigger arbitrary
commands.

### Milestone 2 --- Natural-language understanding

Implement:

-   Cloud fallback integration with a free tier, plus optional local
    Ollama.
-   Structured intent and tool-call output.
-   Command disambiguation.
-   Short-term conversational context.
-   Local fallback for simple deterministic commands.

**Exit criteria:** natural-language variations map to valid tools;
malformed or unsafe model output is rejected.

### Milestone 3 --- Voice

Implement:

-   Push-to-talk.
-   Whisper transcription (faster-whisper in the current build).
-   Piper speech output, including Hindi, Marathi and other Indian
    voices.
-   Wake-word detection.
-   Interrupt and stop controls.
-   Visible microphone status.
-   Enrolled speaker recognition using local ANN embeddings.
-   Visible speaker-match status and a delete-profile control.

Current V1 build: `Ctrl+Space` push-to-talk with silence auto-stop, interrupt
by pressing the hotkey again, multilingual faster-whisper recognition
(`small`, language auto-detect), microphone status messages, rotating audit
logs, and post-launch process verification. Wake-word detection and enrolled
speaker recognition remain for V2.

**Exit criteria:** voice commands can complete the same tested actions
as text commands, with clear listening and cancellation states.

### Milestone 4 --- Context and knowledge

Implement:

-   Preferences and aliases.
-   Persistent conversation/task history.
-   Local document search.
-   RAG for selected files.
-   User-visible memory controls.

**Exit criteria:** memory is inspectable, editable and does not silently
store sensitive content.

### Milestone 5 --- Integrations and automation

Implement:

-   Browser automation.
-   MCP client and server integrations.
-   Skill registry.
-   Scheduled workflows.
-   Additional Windows tools.

**Exit criteria:** every integration has declared permissions, timeouts,
logs and failure handling.

### Milestone 6 --- Advanced agents and interface

Implement only after the earlier milestones are stable:

-   Multi-step planning.
-   Long-running tasks.
-   Agent delegation.
-   Parallel execution.
-   Visual context.
-   Opt-in camera presence and CNN face recognition with an enrolled
    profile.
-   Floating assistant and full workspace.
-   Opt-in proactivity and trigger engine with quiet hours.
-   Consistent AKKI presence across voice, tray and workspace.

**Exit criteria:** complex tasks have observable progress, cancellation,
bounded permissions and independent verification.

## 14. First implementation target

The first practical demonstration should be:

> User presses `Ctrl + Space` and says: "Open VS Code and my Finora
> project."

AKKI should:

1.  Capture the request.
2.  Transcribe it.
3.  Identify the application and project.
4.  Resolve the configured VS Code executable and Finora directory.
5.  Validate both targets.
6.  Execute the launch operation.
7.  Verify that the process was started.
8.  Respond with a concise confirmation or explain exactly what failed.

The same workflow should be possible through text input.

This demonstration tests the most important foundations: input, intent
understanding, tool selection, safe execution, multi-step coordination
and result reporting.

## 15. Open decisions

These choices should be finalized before implementation:

-   Which wake-word phrase and detector configuration should be used?
-   Confirm qwen2.5:3b as the default tier and define when to fall back
    to 1.5B.
-   Should the desktop interface start with PySide6 or another
    framework?
-   Which application and folder locations should be configurable?
-   What should the default confirmation policy be?
-   How should AKKI behave when Ollama is stopped or unavailable?
-   Which actions should remain available completely offline?
-   Should the recommended profile require 16 GB RAM, and exactly what
    degrades on the 8 GB tier?
-   How should memory be reviewed, edited and cleared?
-   Which profile ships as the default, and can it be switched at
    runtime?
-   Confirm the default free cloud provider and how rate limits and
    invalid keys are surfaced.
-   Should the cloud fallback activate automatically when a key is
    present, or require explicit opt-in?
-   Which uncensored local model and image-generation runtime should be
    the default?
-   How should authorised security-research scope be declared and
    enforced?
-   How should the latency targets be verified on the 8 GB / GTX 1650
    reference machine?
-   Which ambient triggers are permitted by default under the Guarded
    profile?
-   Which CNN face model and speaker-embedding model meet the accuracy,
    latency and license goals?
-   What similarity threshold and enrolment quality bar should gate face
    and voice recognition?
-   Should voice recognition be allowed to reject unenrolled speakers by
    default?
-   Which model and voice licenses meet the project's distribution
    goals?

## 16. Definition of success

AKKI Phase 1 is successful when it can:

-   Start reliably with Windows or on demand.
-   Be invoked using keyboard and voice.
-   Understand common everyday commands.
-   Open configured applications, websites, files and folders.
-   Perform selected system actions safely.
-   Maintain useful context across follow-up commands.
-   Work without paid API keys.
-   Keep core voice and intelligence processing local where supported.
-   Clearly communicate what it is doing.
-   Operate under a user-selected profile and report which permissions
    are active.
-   Verify actions and report failures honestly.
-   Be stopped, cancelled and controlled by the user.
-   Feel like a consistent presence with a stable name, voice and
    manner.
-   Respond within the conversational latency budget defined for the
    target hardware.
-   Recognize the enrolled user by face and voice when those features
    are enabled, without requiring them for normal operation.
-   Stay within the 8 GB RAM and 4 GB VRAM budget while the laptop is
    in normal use, meeting the latency targets in section 8.

------------------------------------------------------------------------

## Final product direction

AKKI is an independently developed, Windows-first, local-first personal
AI assistant.

It will learn from the strongest ideas in Ari, PyGPT, OpenVoiceUI and
Leon, but it will not be a collection of copied projects. Its identity
will come from a coherent architecture, dependable Windows actions,
natural interaction, transparent permissions, local operation and an
extensible tool system.

**Build a dependable assistant first. Expand its intelligence and
autonomy only when the foundations are proven.**
