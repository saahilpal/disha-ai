# User Flows

**Status:** As-built paths are marked **WORKING / PARTIAL / BROKEN** based on code review. Browser QA and runtime evidence are pending in `docs/design/DEFECTS.md`; current archived screenshots are not live-browser proof.

## First visit and account creation

```mermaid
flowchart TD
  A[Landing / sign in] --> B{New or returning?}
  B -->|New| C[Choose UI language]
  C --> D[AI health coach + data-use disclosure]
  D --> E[Create account]
  E --> F[Optional profile details]
  F --> G[Chat screen with one welcome message]
  G --> H[Start onboarding in chat or choose voice]
  B -->|Returning| I[Sign in]
  I --> J[Load profile, conversation, and onboarding cursor]
  J --> K{Setup incomplete?}
  K -->|Yes| L[Resume next saved slot]
  K -->|No| M[Chat / start voice]
```

**Current status:** Account registration and sign-in exist. Optionality, single welcome, profile/history hydration, and locale limits are being corrected. Disclosure and consent are incomplete; no real staged onboarding UI exists yet.

## Onboarding through chat or voice

```mermaid
flowchart TD
  A[Authenticated chat or voice turn] --> B[Load user-scoped stage cursor]
  B --> C{Emergency?}
  C -->|Yes| D[Emergency guidance; suspend onboarding; save no new slot]
  C -->|No| E{Supported English / Hindi / Hinglish?}
  E -->|No| F[Brief language deflection; no extraction or cursor change]
  E -->|Yes| G{Pending slot answer or command?}
  G -->|Answer| H[Normalize for current slot]
  H --> I{Valid and consented?}
  I -->|No| J[Explain issue; retain cursor]
  I -->|Yes| K[Commit slot, provenance, event, and cursor atomically]
  G -->|Side question| L[Answer via normal coaching path]
  K --> M{Critical value?}
  M -->|Yes| N[Confirm what was heard]
  M -->|No| O[Select one next applicable slot]
  N --> O
  L --> P[Resume saved slot only when appropriate]
  O --> Q[Render same question as chat bubble or voice prompt]
```

**Current status:** Chat and voice share the backend turn path; basic extraction and scheduling exist. The targeted slot state machine, consent gate, atomic slot writes, explicit commands, and user-facing resume flow are not implemented. The intended deterministic flow above is not yet live.

## Channel switch and interruption

```mermaid
flowchart LR
  A[Voice question / answer] --> B[Persist same cursor and channel=voice]
  B --> C{Switch to chat?}
  C -->|Yes| D[Stop microphone and voice capture]
  D --> E[Open chat with same pending slot]
  E --> F[Continue without repeating saved answers]
  C -->|No| G[Continue voice]
  H[Refresh / app restart] --> I[Authenticate]
  I --> J[Fetch same saved cursor]
  J --> F
```

**Current status:** Backend journey tables persist state, but browser history and an explicit onboarding resume cursor are not hydrated. “To Chat” currently hides the call overlay without ending mic capture; this is a blocker for the redesigned flow.

## Call, consent, and mic denial

```mermaid
flowchart TD
  A[User taps Start Voice] --> B{Voice recording consent saved?}
  B -->|No| C[Explain capture and data use]
  C --> D{User accepts?}
  D -->|No| E[Stay in chat]
  D -->|Yes| F[Request microphone permission]
  B -->|Yes| F
  F --> G{Permission granted?}
  G -->|No| H[Show recovery steps; offer chat; keep cursor]
  G -->|Yes| I[Connect voice; show live captions and mic state]
  I --> J{End or switch to chat?}
  J -->|End| K[Stop mic, recorder, audio, and voice turn]
  J -->|Switch| L[Stop mic; preserve onboarding cursor; return to chat]
```

**Current status:** Voice capture, WebSocket, and audio playback exist. The consent dialog markup is absent, so the current guard does not prevent voice startup. Live captions are not wired. Permission error copy exists but end-to-chat lifecycle must be fixed.

## Emergency, unsupported language, offline, and expired session

```mermaid
flowchart TD
  A[User turn] --> B{Emergency phrase?}
  B -->|Yes| C[Emergency guidance; suspend onboarding; do not ask another question]
  B -->|No| D{English, Hindi, or Hinglish?}
  D -->|No| E[One short deflection; no slot extraction]
  D -->|Yes| F{Network / API available?}
  F -->|No| G[Say answer was not saved; retain text for explicit retry]
  F -->|Yes| H{Session valid?}
  H -->|No| I[Return to sign in; server cursor remains saved]
  H -->|Yes| J[Continue normal coaching and onboarding]
```

**Current status:** Emergency checks precede normal chat processing. Existing language detection and session handling require browser/API verification. Offline answer retention and explicit retry are incomplete; no silent sensitive-data queue is intended.

## Completion and first follow-up

```mermaid
flowchart TD
  A[S0-S8 applicable slots complete or explicitly skipped] --> B[Summarize safety details only]
  B --> C{User confirms or edits?}
  C -->|Edit| D[Update targeted safety slot and record event]
  D --> B
  C -->|Confirm| E[Offer one next action]
  E --> F[Start first call now or record a preferred follow-up window]
```

**Current status:** There is no verified outbound-call/reminder scheduler. Until one exists, the UI must call a follow-up window a user preference and must not claim an appointment, notification, or proactive call was scheduled.
