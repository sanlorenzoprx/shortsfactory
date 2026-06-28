# SHORTS FACTORY REPO BUILD COMMAND CENTER

## Objective

Turn the current markdown scaffold into a boring, working repo that generates one local mock Short end-to-end.

The uploaded scaffold currently defines a 9-agent concept, but several pieces are placeholders: voiceover returns a fake `voice.mp3`, captions return a fake `captions.srt`, the ffmpeg helper only prints, and the setup references `orchestrator.py` even though it is not included. The first job is to make the pipeline produce real local files, not to add more agents.

## First win

This command must pass:

```bash
python orchestrator.py --batch 1 --locale en-US --mode mock
```

It must create:

```txt
output/jobs/<job_id>/short.mp4
output/jobs/<job_id>/thumbnail.jpg
output/jobs/<job_id>/captions.srt
output/jobs/<job_id>/script.txt
output/jobs/<job_id>/receipt.json
```

## Hard rule

No creative expansion until the first win works and tests pass.

Do not add:

- TikTok API
- YouTube API
- Auto-publishing
- Playwright screen recording
- ElevenLabs
- Google Trends
- Reddit scraping
- More agents
- LangGraph/CrewAI
- Real G20 localization
- Scheduler
- Queue workers

## Required repo structure

```txt
shorts_factory_mvp_repo/
  orchestrator.py
  requirements.txt
  .env.example
  README.md
  content_factory/
    __init__.py
    config.py
    schemas.py
    agents/
      idea_researcher.py
      app_tester.py
      script_writer.py
      localization_agent.py
      caption_agent.py
      thumbnail_agent.py
      video_builder.py
    utils/
      files.py
  tests/
    test_mvp_pipeline.py
```

## Required behavior

### 1. Mock mode must work offline

The MVP must not require:

- Ollama
- OpenAI
- Anthropic
- Groq
- ElevenLabs
- Playwright
- A live LIT API

### 2. AppTester must never return incomplete data

Every verdict must include:

- idea
- verdict_headline
- lit_score
- risk_level
- top_reason
- next_step
- source

### 3. ScriptWriter must be deterministic

No LLM calls in MVP. The script should use a fixed structure:

- hook
- score/risk
- reason
- verdict reveal
- CTA

### 4. CaptionAgent must write a real `.srt` file

Do not return fake paths.

### 5. ThumbnailAgent must write a real `.jpg` file

Use Pillow. Keep it simple.

### 6. VideoBuilder must write a real `.mp4` file

Use Pillow to render text scenes as PNG images, then use ffmpeg to stitch them into a 9:16 vertical MP4.

Avoid raw ffmpeg `drawtext` for MVP because escaping apostrophes, colons, emojis, percent signs, and line breaks is fragile.

### 7. Receipt is mandatory

Every run must write `receipt.json` with:

- job_id
- created_at
- locale
- mode
- idea
- verdict
- outputs
- warnings

## Acceptance tests

Run:

```bash
pytest -q
python orchestrator.py --batch 1 --locale en-US --mode mock
```

The test must assert all required output files exist and are non-empty.

## Phase 2 only after MVP passes

After the local mock pipeline works:

1. Add real LIT API mode.
2. Add Playwright app capture.
3. Add TTS.
4. Add music mixing.
5. Add real localization.
6. Add queue/scheduler.
7. Add publisher workflow.
