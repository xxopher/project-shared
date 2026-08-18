# CritiqAI

> **"Using AI to teach students not to depend on AI"**

[![License: CC-BY 4.0](https://img.shields.io/badge/License-CC--BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/) [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/) [![Google ADK](https://img.shields.io/badge/framework-Google%20ADK-4285F4.svg)](https://google.github.io/adk-docs/)

AI tools give students answers — and students are losing the ability to think for themselves. The most visible symptom: students submit AI-written essays they cannot defend in a five-minute conversation. CritiqAI reverses the dynamic. It uses AI exclusively to *challenge* thinking, never to supply it.

[Demo Video](https://youtube.com/placeholder) | Track: **Agents for Good — Education**

---

## How It Works

```
Essay (Google Drive)
        │
        ▼
  ┌─────────────┐
  │ Summarizer  │  compress 75% → save tokens
  └──────┬──────┘
         │
         ▼
  ┌──────────────────┐
  │ Persona Selector │  detect weakness → pick 1 of 4 personas
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────────────────────────────────┐       ┌──────────────────────┐
  │              Debate Agent                    │◄──────┤  Validator Agent     │
  │                                              ├──────►│ (answer-leak check)  │
  │  Round 1: Persona challenges essay           │       └──────────────────────┘
  │  Round 2: Student responds (simulated)       │
  │  Round 3: Persona escalates                  │
  │                                              │
  │  Personas: Skeptic / Devil's Advocate /      │
  │            Nitpicker / Expander              │
  └──────┬───────────────────────────────────────┘
         │
         ▼
  ┌─────────────────────┐
  │ argument-scorer MCP │  rule-based, 0 LLM tokens
  └──────┬──────────────┘
         │
         ▼
  ┌───────────────────────┐
  │ Analytics+Report Agent│  create DRAFT → HITL gate
  └──────┬────────────────┘
         │  teacher approves
         ▼
    Gmail (send)
```

---

## Agents (6)

| Agent | Role |
|---|---|
| **Orchestrator** | Root ADK agent — routing, session state, entry point |
| **Summarizer** | Compresses essay ~75% before LLM calls to save token budget |
| **Persona Selector** | Detects the student's primary argumentative weakness, picks one persona |
| **Debate Agent** | Runs 3-round Socratic debate using one of four challenger personas |
| **Challenge Validator Agent** | Deterministic quality gate — answer-leak patterns, single-question rule, length check. Zero LLM tokens. Retries Debate Agent on hard fail. |
| **Analytics + Report Agent** | Aggregates scores, drafts teacher report — gated behind HITL approval |

---

## MCP Servers (4)

| Server | Type | Purpose |
|---|---|---|
| **Google Drive MCP** | Google-hosted | Read-only access to submissions folder |
| **Google Sheets MCP** | Google-hosted | Append + read — debate history and scores |
| **Gmail MCP** | Google-hosted | Compose only, no auto-send (HITL-gated) |
| **argument-scorer** | **Custom FastMCP — Cloud Run (serverless)** | Hybrid scoring: deterministic keyword matching for English (0 tokens) · 1 compact Gemini call for non-English vi/ja/zh (~300 tokens, LRU-cached) |

---

## Key Design Decisions

**The Challenge Validator is deterministic, not LLM-based.**
The Validator uses pure Python checks — 18 banned phrases, a `?`-count rule, and a word-count ceiling. No AI call is made to validate an AI output. This eliminates false positives (LLM-validators were flagging legitimate DevilsAdvocate challenges), removes 1–3 API calls per round, and makes the quality gate auditable.

**argument-scorer uses hybrid scoring: deterministic keyword matching for English, one compact LLM call for non-English.**
English text is scored with pure Python keyword rules — zero tokens, fully auditable. Non-English text (Vietnamese, Japanese, Chinese) triggers a single compact Gemini call scoring all four dimensions at once (~300 tokens, `temperature=0`, LRU-cached per response). It runs as a separate Cloud Run service (HTTP transport), keeping the scoring pipeline serverless and independently scalable. Teachers can audit English scores line-by-line; non-English scores are cached so the same response is never scored twice.

**Gmail is compose-only with a HITL gate.**
The Report Agent drafts the message. A teacher reads it and clicks send. The system is incapable of emailing anyone without human sign-off — an intentional constraint, not a limitation.

**The system only challenges, never answers.**
Every persona is designed to ask harder questions, not to provide corrections. This is the pedagogical core: students must locate their own errors. Giving a "better argument" would reproduce the exact dependency CritiqAI is designed to break.

**Free-tier compatible.**
Token budget is ~3,150 tokens/session on `gemini-2.5-flash-lite` (Google AI Studio free tier), supporting ~317 sessions/day (English) / ~290 sessions/day (non-English). The Summarizer and the zero-token scorer are the two mechanisms that make this budget viable at scale.

---

## Design Criteria Coverage

CritiqAI demonstrates four of the key agentic design concepts, all backed by code in this repo:

| Criterion | Feature |
|---|---|
| Multi-agent ADK system | 6 specialized agents (`agents/`), Orchestrator as root ADK `LlmAgent` |
| MCP server including custom | 3 Google MCP integrations + `argument-scorer` (custom FastMCP, `mcp_servers/argument_scorer/`) |
| Security features | Read-only Drive, compose-only Gmail, HITL gate on outbound email, deterministic answer-leak validator, input sanitization |
| Agent Skills | `skills/` — Paul-Elder rubric, persona-selector decision tree, answer-leak patterns (injected into agent instructions) |

---

## Quick Start

```bash
git clone https://github.com/francisnguyenanh/CritqAI.git
cd CritqAI
cp .env.example .env          # fill in GOOGLE_API_KEY
pip install -r requirements.txt

# Run the teacher/student web app
python web_app.py             # then open http://localhost:8000/teacher
```

**AI engine:**

- `GOOGLE_API_KEY` — uses `gemini-2.5-flash-lite` via AI Studio free tier (all judges need; no billing, no gcloud)
- Optional dev backends (Vertex AI / Kaggle) live in `ai_module/`; credentials are supplied at runtime via env vars and are never committed

---

## License

[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) — share and adapt with attribution.

---

*Built on Google ADK — Agents for Good: Education.*
