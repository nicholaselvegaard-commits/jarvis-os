# Jarvis OS

An autonomous AI agent framework that runs 24/7, manages itself, and actually gets work done.

Built because every AI assistant forgets everything after the conversation ends.

## Core Ideas

**Persistent memory** -- remembers every conversation, decision, and outcome across sessions.

**Tool use, not chat** -- Jarvis does not talk about sending emails. It sends them. Does not talk about finding leads. It finds them.

**Self-improvement** -- reads its own error logs weekly, proposes fixes, auto-applies safe ones.

**Model routing** -- uses the cheapest capable model for each task. Groq for research. Claude for complex decisions. Local Ollama when offline.

## Architecture

```
core/
  engine.py        # Main Claude tool-use loop
  error_handler.py # Retry logic with exponential backoff

memory/
  smart_memory.py  # Compressed semantic memory (SQLite)
  goals.py         # Revenue tracking + milestone alerts

tools/
  apollo.py        # Lead generation
  crm.py           # CRM with lead scoring
  email_sender.py  # Autonomous outreach
  brreg.py         # Norwegian business registry (free)
  minimax.py       # TTS, video, music generation

agents/
  sales_agent.py       # Cold outreach machine
  content_agent.py     # Brand content pipeline
  scout_agent.py       # Competitive intelligence
  self_improve_agent.py # Weekly self-analysis
```

## What it can do right now

- Find Norwegian businesses via Bronnoysund API (free, no key)
- Score leads 0-100 based on fit
- Send personalized cold emails from a dedicated inbox
- Generate Twitter/LinkedIn/Reddit content drafts (approval required)
- Monitor crypto prices, alert on >5% moves
- Read error logs and auto-fix simple bugs
- Run 16 scheduled jobs autonomously (03:00-21:00)

## Stack

Python 3.12 · FastAPI · APScheduler · SQLite · httpx · Anthropic API

## Status

Running 24/7 on Hetzner VPS. Not yet open for external contributions -- cleaning up before public release.

## Author

Nicholas Elvegaard -- 17, Bodo Norway
[nicholaselvegaard.com](https://nicholaselvegaard.com) (coming soon)
