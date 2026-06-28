# Phase Receipts

## Phase 1 / MVP — Local Mock Pipeline

Status: complete

Outputs:
- `script.txt`
- `captions.srt`
- `thumbnail.jpg`
- `short.mp4`
- `receipt.json`

Result:
The repo can generate one local mock short end-to-end.

## Phase 2A — LIT API Connection

Status: complete

Commit:
`2ad9b80 Implement Phase 2A LIT API integration`

Implemented:
- Real LIT HTTP client
- Configurable URL and timeout
- Optional Bearer authentication
- Response normalization
- Strict verdict validation
- Safe API fallback
- `lit_api_response.json` on successful API calls
- Tests and README instructions

Known note:
The exact LIT-side companion commit is not recorded here. If needed, check the LIT-GhostTown repo separately.

## Phase 2B — Controlled Playwright Recording

Status: complete

Commit:
Not visible in the provided `git log -10`; verify and fill if needed.

Implemented:
- Controlled Playwright recorder
- `--record-app` CLI flag
- Raw WebM recording
- Normalized MP4 recording
- Final screenshot
- Receipt recording metadata
- Tests

Evidence reported:
- First-win command succeeded.
- WebM and H.264 MP4 verified at 1080×1920.
- Mock and API modes remain recording-disabled by default.
- No real-user recording added.

## Phase 2C — Real Voiceover/TTS

Status: complete

Commit:
`bd8d3e3 Add Phase 2C voiceover generation`

Evidence:
- 23 tests passed
- Real SAPI voiceover
- 25.216s PCM WAV
- Final MP4 includes AAC audio
- Final MP4 H.264 1080×1920

## Phase 2D — Background Music Mixing

Status: complete

Commit:
`b2a1759 Add Phase 2D background music mixing`

Evidence:
- 27 tests passed
- Final MP4 H.264 1080×1920 with AAC audio
- Voice retention correlation: 0.997021

## Phase 2E — Real Localization

Status: complete

Commit:
`53a2b4f Add Phase 2E localization support`

Implemented:
- Deterministic en-US / es-PR localization
- One localized verdict feeds every renderer
- Fallback warning for unsupported locales
- No translation service or LLM dependency

## Phase 2F — Local Queue and Scheduler

Status: complete

Commit:
`a3edbba Add Phase 2F local queue and scheduler`

Implemented:
- Local queue
- Local scheduler
- Single-process queue constraints documented

## Phase 2G — Dry-Run Publisher Packages

Status: complete

Commit:
`48fb757 Add Phase 2G dry-run publisher packages`

Evidence:
- 44 tests passed
- Final media: H.264/AAC, 1080×1920
- Live publishing disabled and explicitly refused
- Publisher packages require human approval

Reported receipt:
`output/phase2g-acceptance/jobs/2b600930dc05/receipt.json`
