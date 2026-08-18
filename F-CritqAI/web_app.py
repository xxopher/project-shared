"""CritiqAI Web Dashboard — configure, launch, and run sessions without CLI."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from dotenv import set_key, dotenv_values

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
MCP_SCRIPT = ROOT / "mcp_servers" / "argument_scorer" / "server.py"
SCORER_CONFIG_FILE = ROOT / "scorer_config.json"
SCORER_URL = os.getenv("SCORER_URL", "")  # Cloud Run URL — khi set thì skip subprocess

DEFAULT_SCORER_CONFIG = {
    "llm_scoring": True,
    "llm_model": "gemini-2.0-flash-lite",
    "logical_coherence": {
        "positive_keywords": ["therefore","because","thus","hence","consequently","it follows","since","so"],
        "negative_keywords": ["obviously","clearly it is","everyone agrees","needless to say","it goes without saying"],
        "thresh_5_min_pos": 3, "thresh_5_max_neg": 0,
        "thresh_4_min_pos": 2, "thresh_4_max_neg": 1,
        "thresh_3_min_pos": 1,
    },
    "evidence_quality": {
        "positive_keywords": ["according to","percent","reported","published","in 20","in 19","study by","research by","data from","survey","cited","found that","demonstrated","showed that","statistics"],
        "negative_keywords": ["everyone knows","it's clear that","studies show","obviously","it is well known","people say"],
        "thresh_5_min_pos": 3, "thresh_5_max_neg": 0,
        "thresh_4_min_pos": 2, "thresh_4_max_neg": 1,
        "thresh_3_min_pos": 1,
    },
    "counterargument_handling": {
        "positive_keywords": ["while","although","however","on the other hand","critics argue","one might argue","opponents claim","this doesn't mean","despite","even though","admittedly","some may argue","it could be argued","a counterpoint"],
        "negative_keywords": ["wrong","false","simply wrong","clearly wrong","no one believes"],
        "thresh_5_min_pos": 3, "thresh_5_max_neg": 0,
        "thresh_4_min_pos": 2, "thresh_4_max_neg": 1,
        "thresh_3_min_pos": 1,
    },
    "scope_awareness": {
        "positive_keywords": ["may","might","could","in some cases","it depends","under certain","assuming","given that","limited to","in this context","for example","this does not apply","within the scope","one limitation","however this"],
        "negative_keywords": ["always","never","everyone","all people","in all cases","universally","without exception","absolutely","completely"],
        "thresh_5_min_pos": 3, "thresh_5_max_neg": 0,
        "thresh_4_min_pos": 2, "thresh_4_max_neg": 1,
        "thresh_3_min_pos": 1,
    },
}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contextlib import asynccontextmanager

@asynccontextmanager
async def _lifespan(_: FastAPI):
    from agents.model_config import fetch_available_models
    from dotenv import load_dotenv
    import logging
    load_dotenv(str(ENV_FILE), override=True)
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if api_key:
        await asyncio.get_event_loop().run_in_executor(None, fetch_available_models, api_key)
    else:
        logging.getLogger(__name__).warning(
            "startup: GOOGLE_API_KEY not set — model list will use static defaults"
        )
    yield  # app runs here


app = FastAPI(title="CritiqAI Dashboard", lifespan=_lifespan)

_mcp_process: Optional[subprocess.Popen] = None
_api_lock = asyncio.Lock()

from session_manager import DebateSessionManager
_debate_manager = DebateSessionManager()

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CritiqAI — Dashboard</title>
<style>
:root {
  --ground:      #F9F6EF;
  --surface:     #FFFFFF;
  --text:        #1A1815;
  --muted:       #7A7268;
  --accent:      #A83225;
  --accent-2:    #2D3F6E;
  --border:      #DDD8CE;
  --border-mid:  #C4BDB0;
  --green:       #2A6041;
  --gap:         1.5rem;
  --radius:      4px;
  --font-serif:  "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  --font-ui:     -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --font-mono:   "Courier New", Courier, monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html { font-size: 16px; }

body {
  background: var(--ground);
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 0.9375rem;
  line-height: 1.6;
  min-height: 100vh;
}

/* ── HEADER ── */
.site-header {
  background: var(--surface);
  border-bottom: 2px solid var(--text);
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.logo {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.logo-name {
  font-family: var(--font-serif);
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1;
}

.logo-name span {
  color: var(--accent);
}

.logo-sub {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.mcp-badge {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--muted);
  letter-spacing: 0.04em;
  background: var(--ground);
  border: 1px solid var(--border);
  padding: 0.25rem 0.625rem;
  border-radius: 2px;
}

.mcp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--border-mid);
  transition: background 0.3s;
  flex-shrink: 0;
}
.mcp-dot.running { background: var(--green); box-shadow: 0 0 0 2px rgba(42,96,65,0.2); }

/* ── TABS ── */
.tabs-nav {
  display: flex;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 2rem;
  gap: 0;
}

.tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 0.75rem 1.25rem;
  font-family: var(--font-ui);
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--muted);
  cursor: pointer;
  margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
  letter-spacing: 0.01em;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active {
  color: var(--accent-2);
  border-bottom-color: var(--accent-2);
}

/* ── LAYOUT ── */
.main {
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.tab-pane { display: none; }
.tab-pane.active { display: block; }

/* ── SECTION LABELS ── */
.section-eyebrow {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.section-eyebrow::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

/* ── FILL-IN FIELD (annotated manuscript style) ── */
.field-group {
  margin-bottom: 1.5rem;
}

.field-label {
  display: block;
  font-size: 0.725rem;
  font-family: var(--font-mono);
  color: var(--muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 0.35rem;
}

.field-input {
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1.5px solid var(--border-mid);
  border-radius: 0;
  padding: 0.375rem 0.125rem;
  font-family: var(--font-mono);
  font-size: 0.875rem;
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}
.field-input:focus { border-bottom-color: var(--accent-2); }
.field-input::placeholder { color: var(--border-mid); }

.field-input.secret {
  letter-spacing: 0.05em;
}

.field-row {
  position: relative;
}

.reveal-btn {
  position: absolute;
  right: 0;
  bottom: 0.375rem;
  background: none;
  border: none;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--muted);
  cursor: pointer;
  padding: 0 0.125rem;
}
.reveal-btn:hover { color: var(--accent-2); }

/* ── GRID ── */
.fields-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 2.5rem;
}
@media (max-width: 600px) {
  .fields-grid { grid-template-columns: 1fr; }
}

/* ── BUTTONS ── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--font-ui);
  font-size: 0.875rem;
  font-weight: 600;
  border: none;
  border-radius: var(--radius);
  padding: 0.625rem 1.25rem;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
  letter-spacing: 0.01em;
}
.btn:active { transform: translateY(1px); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }

.btn-primary {
  background: var(--accent-2);
  color: #fff;
}
.btn-primary:hover:not(:disabled) { opacity: 0.88; }

.btn-danger {
  background: var(--accent);
  color: #fff;
}
.btn-danger:hover:not(:disabled) { opacity: 0.88; }

.btn-ghost {
  background: transparent;
  color: var(--text);
  border: 1.5px solid var(--border-mid);
}
.btn-ghost:hover:not(:disabled) { border-color: var(--text); }

.btn-run {
  background: var(--accent);
  color: #fff;
  font-family: var(--font-serif);
  font-size: 1rem;
  font-style: italic;
  padding: 0.75rem 2rem;
  letter-spacing: 0.01em;
}
.btn-run:hover:not(:disabled) { opacity: 0.88; }
.btn-run.running {
  animation: pulse-run 1.4s ease-in-out infinite;
}

@keyframes pulse-run {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.65; }
}

/* ── MCP CONTROL ── */
.mcp-control {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 1rem 1.25rem;
  border-radius: var(--radius);
}

.mcp-info {
  flex: 1;
}

.mcp-label {
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--text);
  margin-bottom: 0.125rem;
}

.mcp-desc {
  font-size: 0.75rem;
  color: var(--muted);
  font-family: var(--font-mono);
}

/* ── TEXTAREA ── */
.field-textarea {
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.75rem 0.875rem;
  font-family: var(--font-ui);
  font-size: 0.875rem;
  color: var(--text);
  resize: vertical;
  min-height: 140px;
  outline: none;
  transition: border-color 0.15s;
  line-height: 1.6;
}
.field-textarea:focus { border-color: var(--accent-2); }

/* ── ESSAY INPUT TOGGLE ── */
.input-mode-toggle {
  display: flex;
  gap: 0;
  margin-bottom: 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: fit-content;
  overflow: hidden;
}
.mode-btn {
  background: none;
  border: none;
  padding: 0.375rem 0.875rem;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.mode-btn.active {
  background: var(--text);
  color: #fff;
}

/* ── STATUS LINE ── */
.status-line {
  font-size: 0.775rem;
  font-family: var(--font-mono);
  color: var(--muted);
  margin-top: 0.5rem;
  min-height: 1.2em;
  transition: color 0.2s;
}
.status-line.error { color: var(--accent); }

/* ── OUTPUT ── */
.output-area {
  margin-top: 2rem;
  display: none;
}
.output-area.visible { display: block; }

/* Raw stream (while streaming) */
.stream-raw {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  line-height: 1.7;
  color: var(--text);
  max-height: 480px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Rendered report */
.report-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.report-header {
  background: var(--text);
  color: var(--ground);
  padding: 1.25rem 1.5rem;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.report-student-name {
  font-family: var(--font-serif);
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 0.25rem;
}

.report-meta {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: rgba(249,246,239,0.55);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.report-total-stamp {
  text-align: right;
  flex-shrink: 0;
}

.stamp-score {
  font-family: var(--font-mono);
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--ground);
  line-height: 1;
  letter-spacing: -0.03em;
}

.stamp-label {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: rgba(249,246,239,0.5);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.report-body {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.report-section-title {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.625rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.report-section-title::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

.report-claim {
  font-family: var(--font-serif);
  font-size: 1.0625rem;
  line-height: 1.55;
  color: var(--text);
  font-style: italic;
  border-left: 3px solid var(--accent-2);
  padding-left: 0.875rem;
}

.report-evidence {
  font-size: 0.8375rem;
  color: var(--muted);
  margin-top: 0.5rem;
}

/* Personas */
.persona-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.persona-tag {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: var(--ground);
  border: 1px solid var(--border-mid);
  border-radius: 2px;
  color: var(--accent-2);
  letter-spacing: 0.04em;
}

.persona-reason {
  font-size: 0.8375rem;
  color: var(--muted);
  font-style: italic;
}

/* Debate rounds */
.debate-rounds {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.debate-round {
  display: flex;
  gap: 0.875rem;
}

.round-marker {
  flex-shrink: 0;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 0.1rem;
}

.round-content {
  flex: 1;
}

.round-persona-label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--accent);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 0.2rem;
}

.round-question {
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--text);
}

/* Scores rubric */
.scores-table {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 0.875rem;
}

.score-dim-label {
  width: 11rem;
  flex-shrink: 0;
  font-size: 0.8rem;
  color: var(--text);
}

.score-dots {
  display: flex;
  gap: 0.3rem;
  flex-shrink: 0;
}

.score-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1.5px solid var(--border-mid);
  background: transparent;
  transition: background 0.2s, border-color 0.2s;
}
.score-dot.filled {
  background: var(--accent-2);
  border-color: var(--accent-2);
}
.score-dot.high {
  background: var(--green);
  border-color: var(--green);
}
.score-dot.low {
  background: var(--accent);
  border-color: var(--accent);
}

.score-num {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  color: var(--muted);
  width: 2rem;
}

/* Strengths / improve */
.report-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.report-chip {
  font-size: 0.8125rem;
  padding: 0.25rem 0.75rem;
  border-radius: 2px;
}
.chip-strength {
  background: rgba(42,96,65,0.08);
  color: var(--green);
  border: 1px solid rgba(42,96,65,0.2);
}
.chip-improve {
  background: rgba(168,50,37,0.07);
  color: var(--accent);
  border: 1px solid rgba(168,50,37,0.2);
}

/* Next focus */
.next-focus {
  background: var(--ground);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent-2);
  padding: 0.875rem 1rem;
  border-radius: 0 var(--radius) var(--radius) 0;
  font-size: 0.875rem;
  line-height: 1.55;
  color: var(--text);
}

/* Save feedback */
.save-feedback {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--green);
  margin-left: 0.875rem;
  opacity: 0;
  transition: opacity 0.3s;
}
.save-feedback.visible { opacity: 1; }

/* Divider */
.divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1.75rem 0;
}

/* Focus outline for accessibility */
:focus-visible {
  outline: 2px solid var(--accent-2);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .btn-run.running { animation: none; }
  * { transition: none !important; }
}

/* ── LANGUAGE SWITCHER ── */
.lang-switcher {
  display: flex;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.lang-btn {
  background: none;
  border: none;
  padding: 0.25rem 0.6rem;
  font-size: 0.7rem;
  font-family: var(--font-mono);
  letter-spacing: 0.05em;
  color: var(--muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.lang-btn + .lang-btn { border-left: 1px solid var(--border); }
.lang-btn.active { background: var(--text); color: #fff; }
.lang-btn:hover:not(.active) { background: var(--ground); color: var(--text); }

/* ── THINKING INDICATOR ── */
.thinking-wrap {
  display: flex;
  gap: .5rem;
  align-items: flex-end;
}
.thinking-dots {
  display: flex;
  gap: 4px;
  padding: .55rem .85rem;
  background: #fff;
  border: 1px solid #E0DBD2;
  border-radius: 12px;
  border-top-left-radius: 2px;
}
.thinking-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--muted);
  animation: tdot 1.2s ease-in-out infinite;
}
.thinking-dot:nth-child(2) { animation-delay: .2s; }
.thinking-dot:nth-child(3) { animation-delay: .4s; }
@keyframes tdot {
  0%,80%,100% { transform: translateY(0); opacity: 0.35; }
  40% { transform: translateY(-6px); opacity: 1; }
}

/* ── INLINE SPINNER ── */
.spinner {
  display: inline-block;
  width: 11px; height: 11px;
  border: 2px solid var(--border);
  border-top-color: var(--accent-2);
  border-radius: 50%;
  animation: spin .7s linear infinite;
  vertical-align: middle;
  margin-right: 5px;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── SCORER TAB ── */
.scorer-dim {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 1rem;
  overflow: hidden;
}
.scorer-dim-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: .75rem 1rem;
  cursor: pointer;
  user-select: none;
  background: var(--ground);
  border-bottom: 1px solid var(--border);
}
.scorer-dim-title {
  font-weight: 600;
  font-size: .875rem;
}
.scorer-dim-body {
  padding: 1rem;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
@media (max-width: 640px) { .scorer-dim-body { grid-template-columns: 1fr; } }
.scorer-kw-area {
  width: 100%;
  min-height: 70px;
  font-family: var(--font-mono);
  font-size: .78rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: .5rem .625rem;
  resize: vertical;
  line-height: 1.5;
  background: var(--ground);
  color: var(--text);
  outline: none;
}
.scorer-kw-area:focus { border-color: var(--accent-2); }
.scorer-thresh-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .5rem .75rem;
}
.thresh-field label {
  display: block;
  font-size: .68rem;
  font-family: var(--font-mono);
  color: var(--muted);
  letter-spacing: .06em;
  text-transform: uppercase;
  margin-bottom: .2rem;
}
.thresh-field input {
  width: 100%;
  padding: .3rem .4rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-family: var(--font-mono);
  font-size: .85rem;
  background: var(--ground);
  color: var(--text);
  outline: none;
}
.thresh-field input:focus { border-color: var(--accent-2); }

/* ── GMAIL PREVIEW MODAL ── */
.gmail-preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.55);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn .22s ease;
}
@keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
.gmail-preview-modal {
  background: #fff;
  border-radius: 12px;
  width: min(620px, 95vw);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(0,0,0,.28);
  animation: slideUp .24s cubic-bezier(.22,.68,0,1.2);
}
@keyframes slideUp { from { transform: translateY(24px); opacity:0; } to { transform: translateY(0); opacity:1; } }
.gmail-preview-topbar {
  display: flex;
  align-items: center;
  gap: .75rem;
  padding: .85rem 1.1rem;
  background: #f6f8fc;
  border-bottom: 1px solid #e0e0e0;
}
.gmail-icon {
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg,#EA4335,#FBBC05,#34A853,#4285F4);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: .85rem;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.gmail-preview-topbar-title {
  flex: 1;
  font-weight: 600;
  font-size: .875rem;
  color: #202124;
}
.gmail-mock-badge {
  background: #fce8e6;
  color: #c5221f;
  font-size: .68rem;
  font-weight: 700;
  padding: .2rem .55rem;
  border-radius: 20px;
  letter-spacing: .04em;
}
.gmail-preview-close {
  background: none;
  border: none;
  font-size: 1.25rem;
  cursor: pointer;
  color: #5f6368;
  line-height: 1;
  padding: .2rem .4rem;
  border-radius: 4px;
}
.gmail-preview-close:hover { background: #f1f3f4; }
.gmail-preview-header {
  padding: .85rem 1.25rem .65rem;
  border-bottom: 1px solid #f1f3f4;
}
.gmail-preview-meta {
  display: flex;
  gap: .5rem;
  align-items: flex-start;
  margin-bottom: .4rem;
  font-size: .82rem;
}
.gmail-meta-label {
  color: #5f6368;
  min-width: 42px;
  flex-shrink: 0;
  padding-top: 1px;
}
.gmail-meta-value {
  color: #202124;
  word-break: break-all;
}
.gmail-subject-line {
  font-size: 1rem;
  font-weight: 600;
  color: #202124;
  margin-top: .5rem;
}
.gmail-preview-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.1rem 1.25rem;
  font-size: .875rem;
  line-height: 1.7;
  color: #202124;
  white-space: pre-wrap;
  font-family: 'Google Sans', Arial, sans-serif;
}
.gmail-preview-footer {
  padding: .75rem 1.25rem;
  background: #f6f8fc;
  border-top: 1px solid #e0e0e0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: .78rem;
  color: #5f6368;
}
.gmail-hitl-note {
  display: flex;
  align-items: center;
  gap: .4rem;
}
.gmail-hitl-note svg { flex-shrink: 0; }
</style>
</head>
<body>

<!-- Gmail Preview Overlay (injected by JS) -->
<div id="gmailPreviewOverlay" class="gmail-preview-overlay" style="display:none;" aria-modal="true" role="dialog" aria-label="Gmail Draft Preview">
  <div class="gmail-preview-modal">
    <div class="gmail-preview-topbar">
      <div class="gmail-icon">M</div>
      <span class="gmail-preview-topbar-title">Gmail — Draft Preview</span>
      <span class="gmail-mock-badge">SIMULATED · NOT SENT</span>
      <button class="gmail-preview-close" onclick="document.getElementById('gmailPreviewOverlay').style.display='none'" aria-label="Close">&times;</button>
    </div>
    <div class="gmail-preview-header">
      <div class="gmail-preview-meta">
        <span class="gmail-meta-label">To:</span>
        <span class="gmail-meta-value" id="gmail-preview-to"></span>
      </div>
      <div class="gmail-preview-meta">
        <span class="gmail-meta-label">From:</span>
        <span class="gmail-meta-value">critiqai@system (HITL — draft only)</span>
      </div>
      <div class="gmail-subject-line" id="gmail-preview-subject"></div>
    </div>
    <div class="gmail-preview-body" id="gmail-preview-body"></div>
    <div class="gmail-preview-footer">
      <div class="gmail-hitl-note">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        Human-in-the-Loop: Teacher reviews &amp; sends manually. CritiqAI cannot auto-send.
      </div>
      <button class="btn btn-run" style="font-size:.75rem;padding:.35rem .85rem;" onclick="document.getElementById('gmailPreviewOverlay').style.display='none'">Close Preview</button>
    </div>
  </div>
</div>

<header class="site-header">
  <div class="logo">
    <div class="logo-name">Critiq<span>AI</span></div>
    <div class="logo-sub">Paul–Elder Framework · Socratic Debate Coach</div>
  </div>
  <div class="header-right">
    <div class="lang-switcher" role="group" aria-label="Language">
      <button class="lang-btn active" data-lang="en" type="button">EN</button>
      <button class="lang-btn" data-lang="vi" type="button">VI</button>
      <button class="lang-btn" data-lang="ja" type="button">日本語</button>
    </div>
    <div class="mcp-badge" id="mcpBadge">
      <span class="mcp-dot" id="mcpDot"></span>
      <span id="mcpBadgeText">argument-scorer</span>
    </div>
  </div>
</header>

<nav class="tabs-nav" role="tablist">
  <button class="tab-btn active" role="tab" aria-selected="true" data-tab="configure">Configure</button>
  <button class="tab-btn" role="tab" aria-selected="false" data-tab="scorer">Scorer Settings</button>
  <button class="tab-btn" role="tab" aria-selected="false" data-tab="session">One-shot Demo</button>
  <button class="tab-btn" role="tab" aria-selected="false" data-tab="interactive">Interactive Debate</button>
</nav>

<main class="main">

  <!-- ── TAB: CONFIGURE ── -->
  <div class="tab-pane active" id="tab-configure">

    <div id="mockModeBanner" style="display:none; background:rgba(255,193,7,0.15); border-left:3px solid #ffc107; padding:0.75rem 1rem; margin-bottom:1.5rem; border-radius:var(--radius); font-size:0.85rem; color:#856404;">
      <strong>Test Mode Active:</strong> No Google OAuth credentials found in .env. Gmail drafts and Sheets logging will be simulated safely on the UI.
    </div>

    <p class="section-eyebrow" id="eyebrow-env">Environment</p>

    <div class="fields-grid">
      <div class="field-group">
        <label class="field-label" for="cfg-google-api-key">Google API Key (Gemini)</label>
        <div class="field-row">
          <input class="field-input secret" id="cfg-google-api-key" name="GOOGLE_API_KEY" type="password"
            placeholder="AIza..." autocomplete="off">
          <button class="reveal-btn" type="button" data-target="cfg-google-api-key">show</button>
        </div>
      </div>

      <div class="field-group">
        <label class="field-label" for="cfg-teacher-email">Teacher Email</label>
        <input class="field-input" id="cfg-teacher-email" name="TEACHER_EMAIL" type="email"
          placeholder="teacher@school.vn">
      </div>

      <div class="field-group">
        <label class="field-label" for="cfg-oauth-client-id">OAuth Client ID</label>
        <div class="field-row">
          <input class="field-input secret" id="cfg-oauth-client-id" name="GOOGLE_OAUTH_CLIENT_ID" type="password"
            placeholder="641148...apps.googleusercontent.com" autocomplete="off">
          <button class="reveal-btn" type="button" data-target="cfg-oauth-client-id">show</button>
        </div>
      </div>

      <div class="field-group">
        <label class="field-label" for="cfg-oauth-secret">OAuth Client Secret</label>
        <div class="field-row">
          <input class="field-input secret" id="cfg-oauth-secret" name="GOOGLE_OAUTH_CLIENT_SECRET" type="password"
            placeholder="GOCSPX-..." autocomplete="off">
          <button class="reveal-btn" type="button" data-target="cfg-oauth-secret">show</button>
        </div>
      </div>

      <div class="field-group">
        <label class="field-label" for="cfg-sheet-id">Debate Log Sheet ID</label>
        <input class="field-input" id="cfg-sheet-id" name="DEBATE_LOG_SHEET_ID" type="text"
          placeholder="1yn8N7h6ms9s...">
      </div>

      <div class="field-group">
        <label class="field-label" for="cfg-sandbox">Gemini Sandbox</label>
        <input class="field-input" id="cfg-sandbox" name="GEMINI_SANDBOX" type="text"
          placeholder="docker">
      </div>
    </div>

    <div style="display:flex;align-items:center;margin-top:0.5rem;">
      <button class="btn btn-primary" id="saveConfigBtn" type="button">Save settings</button>
      <span class="save-feedback" id="saveFeedback" data-i18n-saved>Saved ✓</span>
    </div>

    <hr class="divider">

    <p class="section-eyebrow" id="eyebrow-mcp">Argument Scorer MCP</p>

    <div class="mcp-control">
      <div class="mcp-info">
        <div class="mcp-label">argument-scorer</div>
        <div class="mcp-desc" id="mcpStatusDesc">Stopped — deterministic Paul-Elder scoring, zero LLM tokens</div>
      </div>
      <button class="btn btn-ghost" id="mcpToggleBtn" type="button" data-i18n-mcp-btn>Start server</button>
    </div>

    <hr class="divider">

    <p class="section-eyebrow">Student Interface</p>

    <div class="mcp-control" style="gap:1rem;margin-bottom:.875rem;">
      <div class="mcp-info">
        <div class="mcp-label">Show results to student</div>
        <div class="mcp-desc" id="show-results-desc">After debate ends, student will see their score breakdown</div>
      </div>
      <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer;flex-shrink:0;">
        <div id="show-results-toggle" onclick="toggleShowResults()" style="
          width:40px;height:22px;border-radius:11px;background:var(--border-mid);
          position:relative;cursor:pointer;transition:background .2s;flex-shrink:0;
        ">
          <div id="show-results-knob" style="
            position:absolute;top:3px;left:3px;
            width:16px;height:16px;border-radius:50%;background:#fff;
            transition:transform .2s;box-shadow:0 1px 3px rgba(0,0,0,.2);
          "></div>
        </div>
        <span id="show-results-label" style="font-size:.8rem;color:var(--muted);font-family:var(--font-mono);">OFF</span>
      </label>
    </div>

    <div class="mcp-control" style="gap:1rem;">
      <div class="mcp-info">
        <div class="mcp-label">Student Debate Link</div>
        <div class="mcp-desc">Share this link with students — no config, no scores visible, debate only.</div>
      </div>
      <div style="display:flex;align-items:center;gap:.625rem;flex-shrink:0;">
        <code id="student-link-text" style="font-family:var(--font-mono);font-size:.78rem;background:var(--ground);border:1px solid var(--border);padding:.3rem .65rem;border-radius:var(--radius);color:var(--accent-2);"></code>
        <button class="btn btn-ghost" onclick="copyStudentLink(this)" type="button" style="padding:.5rem .875rem;font-size:.8rem;">Copy</button>
        <a id="student-link-open" href="/student" target="_blank" class="btn btn-primary" style="padding:.5rem .875rem;font-size:.8rem;text-decoration:none;">Open ↗</a>
      </div>
    </div>

  </div>

  <!-- ── TAB: RUN SESSION ── -->
  <div class="tab-pane" id="tab-session">

    <p class="section-eyebrow" id="eyebrow-student">Session Details</p>

    <div class="fields-grid" style="grid-template-columns:1fr 1fr;margin-bottom:1.75rem;">
      <div class="field-group" style="margin-bottom:0;">
        <label class="field-label" for="studentName">Full name</label>
        <input class="field-input" id="studentName" type="text" placeholder="Nguyen Van An">
      </div>
      <div class="field-group" style="margin-bottom:0;">
        <label class="field-label" for="demoApiKey">Gemini API Key (Optional if configured)</label>
        <input class="field-input secret" id="demoApiKey" type="password" placeholder="Enter key for this session...">
        <div style="font-size:0.65rem; color:var(--muted); margin-top:0.25rem;">Key is strictly stored in memory for this session and NEVER saved.</div>
      </div>
    </div>

    <p class="section-eyebrow" id="eyebrow-essay">Essay</p>

    <div class="input-mode-toggle" role="group" aria-label="Essay input mode">
      <button class="mode-btn active" data-mode="text" type="button">Paste text</button>
      <button class="mode-btn" data-mode="url" type="button">Google Doc URL</button>
    </div>

    <div id="essayTextArea">
      <textarea class="field-textarea" id="essayText" rows="7"
        placeholder="Paste the student's essay here..."></textarea>
    </div>

    <div id="essayUrlArea" style="display:none;">
      <div class="field-row">
        <input class="field-input" id="essayUrl" type="url"
          placeholder="https://docs.google.com/document/d/...">
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:1rem;margin-top:1.25rem;">
      <button class="btn btn-run" id="runBtn" type="button">Run session →</button>
      <span class="status-line" id="runStatus" style="display:flex;align-items:center;gap:4px;"></span>
    </div>

    <!-- Output -->
    <div class="output-area" id="outputArea">
      <div id="streamRaw" class="stream-raw" style="display:none;"></div>
      <div id="reportCard" class="report-card" style="display:none;"></div>
    </div>

  </div>

  <!-- ── TAB: SCORER SETTINGS ── -->
  <div class="tab-pane" id="tab-scorer">
    <p class="section-eyebrow" id="eyebrow-scorer">Scorer Settings</p>
    <p id="scorer-desc" style="color:var(--muted);margin-bottom:1.5rem;font-size:.875rem;">
      Adjust keyword lists and scoring thresholds for each Paul-Elder dimension.
    </p>

    <!-- Logical Coherence -->
    <div class="scorer-dim">
      <div class="scorer-dim-header" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'grid':'none'">
        <span class="scorer-dim-title" id="scorer-title-logical">Logical Coherence</span>
        <span style="font-size:.75rem;color:var(--muted);">▾</span>
      </div>
      <div class="scorer-dim-body" id="scorer-body-logical">
        <div>
          <label class="field-label" id="scorer-lbl-pos-logical">Positive keywords (comma-separated)</label>
          <textarea class="scorer-kw-area" id="scorer-pos-logical"></textarea>
        </div>
        <div>
          <label class="field-label" id="scorer-lbl-neg-logical">Negative keywords (comma-separated)</label>
          <textarea class="scorer-kw-area" id="scorer-neg-logical"></textarea>
        </div>
        <div>
          <label class="field-label" id="scorer-lbl-thresh-logical">Score thresholds (min positive hits)</label>
          <div class="scorer-thresh-grid">
            <div class="thresh-field"><label id="scorer-t5-logical">Score 5 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh5-logical" value="3"></div>
            <div class="thresh-field"><label id="scorer-t4-logical">Score 4 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh4-logical" value="2"></div>
            <div class="thresh-field"><label id="scorer-t3-logical">Score 3 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh3-logical" value="1"></div>
          </div>
        </div>
        <div>
          <label class="field-label" id="scorer-lbl-maxneg-logical">Max negative hits allowed</label>
          <div class="scorer-thresh-grid">
            <div class="thresh-field"><label id="scorer-mn5-logical">Score 5 — max neg.</label><input type="number" min="0" max="10" id="scorer-maxneg5-logical" value="0"></div>
            <div class="thresh-field"><label id="scorer-mn4-logical">Score 4 — max neg.</label><input type="number" min="0" max="10" id="scorer-maxneg4-logical" value="1"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Evidence Quality -->
    <div class="scorer-dim">
      <div class="scorer-dim-header" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'grid':'none'">
        <span class="scorer-dim-title" id="scorer-title-evidence">Evidence Quality</span>
        <span style="font-size:.75rem;color:var(--muted);">▾</span>
      </div>
      <div class="scorer-dim-body" id="scorer-body-evidence" style="display:none;">
        <div>
          <label class="field-label">Positive keywords</label>
          <textarea class="scorer-kw-area" id="scorer-pos-evidence"></textarea>
        </div>
        <div>
          <label class="field-label">Negative keywords</label>
          <textarea class="scorer-kw-area" id="scorer-neg-evidence"></textarea>
        </div>
        <div>
          <div class="scorer-thresh-grid">
            <div class="thresh-field"><label>Score 5 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh5-evidence" value="3"></div>
            <div class="thresh-field"><label>Score 4 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh4-evidence" value="2"></div>
            <div class="thresh-field"><label>Score 3 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh3-evidence" value="1"></div>
          </div>
        </div>
        <div>
          <div class="scorer-thresh-grid">
            <div class="thresh-field"><label>Score 5 — max neg.</label><input type="number" min="0" max="10" id="scorer-maxneg5-evidence" value="0"></div>
            <div class="thresh-field"><label>Score 4 — max neg.</label><input type="number" min="0" max="10" id="scorer-maxneg4-evidence" value="1"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Counterargument Handling -->
    <div class="scorer-dim">
      <div class="scorer-dim-header" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'grid':'none'">
        <span class="scorer-dim-title" id="scorer-title-counter">Counterargument Handling</span>
        <span style="font-size:.75rem;color:var(--muted);">▾</span>
      </div>
      <div class="scorer-dim-body" id="scorer-body-counter" style="display:none;">
        <div>
          <label class="field-label">Positive keywords</label>
          <textarea class="scorer-kw-area" id="scorer-pos-counter"></textarea>
        </div>
        <div>
          <label class="field-label">Negative keywords</label>
          <textarea class="scorer-kw-area" id="scorer-neg-counter"></textarea>
        </div>
        <div>
          <div class="scorer-thresh-grid">
            <div class="thresh-field"><label>Score 5 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh5-counter" value="3"></div>
            <div class="thresh-field"><label>Score 4 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh4-counter" value="2"></div>
            <div class="thresh-field"><label>Score 3 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh3-counter" value="1"></div>
          </div>
        </div>
        <div>
          <div class="scorer-thresh-grid">
            <div class="thresh-field"><label>Score 5 — max neg.</label><input type="number" min="0" max="10" id="scorer-maxneg5-counter" value="0"></div>
            <div class="thresh-field"><label>Score 4 — max neg.</label><input type="number" min="0" max="10" id="scorer-maxneg4-counter" value="1"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Scope Awareness -->
    <div class="scorer-dim">
      <div class="scorer-dim-header" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'grid':'none'">
        <span class="scorer-dim-title" id="scorer-title-scope">Scope Awareness</span>
        <span style="font-size:.75rem;color:var(--muted);">▾</span>
      </div>
      <div class="scorer-dim-body" id="scorer-body-scope" style="display:none;">
        <div>
          <label class="field-label">Positive keywords</label>
          <textarea class="scorer-kw-area" id="scorer-pos-scope"></textarea>
        </div>
        <div>
          <label class="field-label">Negative keywords</label>
          <textarea class="scorer-kw-area" id="scorer-neg-scope"></textarea>
        </div>
        <div>
          <div class="scorer-thresh-grid">
            <div class="thresh-field"><label>Score 5 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh5-scope" value="3"></div>
            <div class="thresh-field"><label>Score 4 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh4-scope" value="2"></div>
            <div class="thresh-field"><label>Score 3 — min pos.</label><input type="number" min="0" max="10" id="scorer-thresh3-scope" value="1"></div>
          </div>
        </div>
        <div>
          <div class="scorer-thresh-grid">
            <div class="thresh-field"><label>Score 5 — max neg.</label><input type="number" min="0" max="10" id="scorer-maxneg5-scope" value="0"></div>
            <div class="thresh-field"><label>Score 4 — max neg.</label><input type="number" min="0" max="10" id="scorer-maxneg4-scope" value="1"></div>
          </div>
        </div>
      </div>
    </div>

    <div style="display:flex;align-items:center;margin-top:1rem;">
      <button class="btn btn-primary" id="saveScorerBtn" type="button">Save Scorer Config</button>
      <span class="save-feedback" id="scorerFeedback">Saved ✓</span>
    </div>
  </div>

  <!-- ── TAB: INTERACTIVE DEBATE ── -->
  <div class="tab-pane" id="tab-interactive">
    <p class="section-eyebrow" id="eyebrow-interactive">Interactive Mode</p>
    <p id="interactive-desc" style="color:var(--muted);margin-bottom:1.5rem;font-size:.9rem;">Real student interaction — AI asks questions, you answer, 3 escalating rounds, then receive a report.</p>

    <!-- Setup form -->
    <div id="debate-setup">
      <div class="fields-grid" style="margin-bottom:1rem;">
        <div class="field-group">
          <label class="field-label" id="d-label-name" for="d-name">Student name</label>
          <input class="field-input" id="d-name" type="text" placeholder="Nguyen Van A" />
        </div>
        <div class="field-group">
          <label class="field-label" for="d-apiKey">Gemini API Key (Optional if configured)</label>
          <input class="field-input secret" id="d-apiKey" type="password" placeholder="Enter key for this session..." />
          <div style="font-size:0.65rem; color:var(--muted); margin-top:0.25rem;">Key is strictly stored in memory for this session and NEVER saved.</div>
        </div>
      </div>

      <div class="field-group" style="margin-bottom:.75rem;">
        <label class="field-label" id="d-label-essay">Essay</label>
        <div style="display:flex;gap:.75rem;margin-bottom:.5rem;">
          <label style="display:flex;align-items:center;gap:.35rem;font-size:.85rem;cursor:pointer;">
            <input type="radio" name="d-mode" value="text" checked id="d-mode-text" /> <span id="d-label-mode-text">Paste text</span>
          </label>
          <label style="display:flex;align-items:center;gap:.35rem;font-size:.85rem;cursor:pointer;">
            <input type="radio" name="d-mode" value="url" id="d-mode-url" /> <span id="d-label-mode-url">Google Doc URL</span>
          </label>
        </div>
        <textarea class="field-input" id="d-essay-text" rows="6"
          placeholder="Paste the student's essay here..."></textarea>
        <input class="field-input" id="d-essay-url" type="url"
          placeholder="https://docs.google.com/document/d/..." style="display:none;" />
      </div>

      <button class="btn btn-run" id="d-start-btn" onclick="debateStart()">
        <span id="d-start-label">Start Session</span>
      </button>
      <div id="d-setup-error" style="color:var(--accent);margin-top:.5rem;font-size:.85rem;"></div>
    </div>

    <!-- Chat area (hidden until session starts) -->
    <div id="debate-chat" style="display:none;">
      <div id="debate-header" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">
        <div>
          <span id="d-student-label" style="font-weight:600;"></span>
          <span id="d-persona-label" style="margin-left:.75rem;font-size:.8rem;background:var(--accent);color:#fff;padding:.15rem .5rem;border-radius:999px;"></span>
        </div>
        <span id="d-round-label" style="font-size:.85rem;color:var(--muted);"></span>
      </div>

      <div id="d-messages" style="
        background:var(--ground);border:1px solid #E0DBD2;border-radius:8px;
        padding:1rem;min-height:200px;max-height:480px;overflow-y:auto;
        display:flex;flex-direction:column;gap:.75rem;margin-bottom:1rem;
      "></div>

      <div id="d-input-area" style="display:flex;gap:.5rem;">
        <textarea id="d-response-input" class="field-input" rows="3"
          placeholder="Enter your response..."
          style="flex:1;resize:vertical;"
          onkeydown="if(event.ctrlKey&&event.key==='Enter'){debateRespond();}"></textarea>
        <button class="btn btn-run" id="d-send-btn" onclick="debateRespond()"
          style="align-self:flex-end;white-space:nowrap;">
          <span id="d-send-label">Send (Ctrl+↵)</span>
        </button>
      </div>
      <p id="d-hint-ctrl" style="font-size:.75rem;color:var(--muted);margin-top:.35rem;">Ctrl+Enter to send quickly</p>
    </div>

    <!-- Report area (hidden until complete) -->
    <div id="debate-report" style="display:none;"></div>

  </div>

</main>

<script>
// ── TABS ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

// ── REVEAL BUTTONS ────────────────────────────────────────────────────────────
document.querySelectorAll('.reveal-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const input = document.getElementById(btn.dataset.target);
    if (input.type === 'password') {
      input.type = 'text';
      btn.textContent = 'hide';
    } else {
      input.type = 'password';
      btn.textContent = 'show';
    }
  });
});

// ── ESSAY MODE TOGGLE ─────────────────────────────────────────────────────────
document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const mode = btn.dataset.mode;
    document.getElementById('essayTextArea').style.display = mode === 'text' ? 'block' : 'none';
    document.getElementById('essayUrlArea').style.display = mode === 'url' ? 'block' : 'none';
  });
});

// ── LOAD CONFIG ───────────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    const data = await res.json();
    const map = {
      'GOOGLE_API_KEY': 'cfg-google-api-key',
      'TEACHER_EMAIL': 'cfg-teacher-email',
      'GOOGLE_OAUTH_CLIENT_ID': 'cfg-oauth-client-id',
      'GOOGLE_OAUTH_CLIENT_SECRET': 'cfg-oauth-secret',
      'DEBATE_LOG_SHEET_ID': 'cfg-sheet-id',
      'GEMINI_SANDBOX': 'cfg-sandbox',
    };
    Object.entries(map).forEach(([key, id]) => {
      const el = document.getElementById(id);
      if (el && data[key] !== undefined) el.value = data[key];
    });

    if (!data['GOOGLE_OAUTH_CLIENT_ID']) {
      document.getElementById('mockModeBanner').style.display = 'block';
    } else {
      document.getElementById('mockModeBanner').style.display = 'none';
    }
  } catch (e) { /* silent */ }
}
loadConfig();

// ── SAVE CONFIG ───────────────────────────────────────────────────────────────
document.getElementById('saveConfigBtn').addEventListener('click', async () => {
  const map = {
    'GOOGLE_API_KEY': 'cfg-google-api-key',
    'TEACHER_EMAIL': 'cfg-teacher-email',
    'GOOGLE_OAUTH_CLIENT_ID': 'cfg-oauth-client-id',
    'GOOGLE_OAUTH_CLIENT_SECRET': 'cfg-oauth-secret',
    'DEBATE_LOG_SHEET_ID': 'cfg-sheet-id',
    'GEMINI_SANDBOX': 'cfg-sandbox',
  };
  const payload = {};
  Object.entries(map).forEach(([key, id]) => {
    const el = document.getElementById(id);
    if (el && el.value.trim()) payload[key] = el.value.trim();
  });
  try {
    await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const fb = document.getElementById('saveFeedback');
    fb.classList.add('visible');
    setTimeout(() => fb.classList.remove('visible'), 2200);
  } catch (e) { alert('Failed to save: ' + e.message); }
});

// ── MCP STATUS ────────────────────────────────────────────────────────────────
let mcpRunning = false;
let mcpMode = 'local';  // 'local' | 'remote'

async function refreshMcpStatus() {
  try {
    const res = await fetch('/api/mcp/status');
    const data = await res.json();
    mcpRunning = data.running;
    mcpMode = data.mode || 'local';
    updateMcpUI();
  } catch (e) { /* silent */ }
}

function updateMcpUI() {
  const dot = document.getElementById('mcpDot');
  const badgeText = document.getElementById('mcpBadgeText');
  const desc = document.getElementById('mcpStatusDesc');
  const btn = document.getElementById('mcpToggleBtn');

  if (mcpMode === 'remote') {
    dot.classList.add('running');
    badgeText.textContent = 'argument-scorer · Cloud Run';
    desc.textContent = 'Serverless — always on, scales to zero automatically. No manual start needed.';
    btn.textContent = 'Cloud Run (managed)';
    btn.disabled = true;
    btn.classList.remove('btn-danger');
    btn.classList.add('btn-ghost');
    return;
  }

  btn.disabled = false;
  if (mcpRunning) {
    dot.classList.add('running');
    badgeText.textContent = (typeof t === 'function') ? t('mcp.badge.running') : 'argument-scorer · running';
    desc.textContent = (typeof t === 'function') ? t('mcp.running') : 'Running — accepting MCP stdio connections';
    btn.textContent = (typeof t === 'function') ? t('btn.stop-server') : 'Stop server';
    btn.classList.remove('btn-ghost');
    btn.classList.add('btn-danger');
  } else {
    dot.classList.remove('running');
    badgeText.textContent = (typeof t === 'function') ? t('mcp.badge.stopped') : 'argument-scorer';
    desc.textContent = (typeof t === 'function') ? t('mcp.stopped') : 'Stopped — hybrid Paul-Elder scoring (keyword EN / LLM non-EN)';
    btn.textContent = (typeof t === 'function') ? t('btn.start-server') : 'Start server';
    btn.classList.remove('btn-danger');
    btn.classList.add('btn-ghost');
  }
}

document.getElementById('mcpToggleBtn').addEventListener('click', async () => {
  if (mcpMode === 'remote') return;
  const endpoint = mcpRunning ? '/api/mcp/stop' : '/api/mcp/start';
  try {
    await fetch(endpoint, {method: 'POST'});
    await refreshMcpStatus();
  } catch (e) { alert('Failed: ' + e.message); }
});

refreshMcpStatus();
setInterval(refreshMcpStatus, 5000);

// ── RUN SESSION ───────────────────────────────────────────────────────────────
const runBtn = document.getElementById('runBtn');
const runStatus = document.getElementById('runStatus');
const outputArea = document.getElementById('outputArea');
const streamRaw = document.getElementById('streamRaw');
const reportCard = document.getElementById('reportCard');

runBtn.addEventListener('click', async () => {
  const studentName = document.getElementById('studentName').value.trim();
  if (!studentName) { setStatus('Enter student name.', true); return; }

  const mode = document.querySelector('.mode-btn.active').dataset.mode;
  const essayText = mode === 'text' ? document.getElementById('essayText').value.trim() : '';
  const essayUrl = mode === 'url' ? document.getElementById('essayUrl').value.trim() : '';
  const apiKey = document.getElementById('demoApiKey').value.trim() || document.getElementById('cfg-google-api-key').value.trim();

  if (!essayText && !essayUrl) { setStatus('Provide essay text or URL.', true); return; }

  // Reset output
  streamRaw.textContent = '';
  reportCard.innerHTML = '';
  streamRaw.style.display = 'block';
  reportCard.style.display = 'none';
  outputArea.classList.add('visible');
  runBtn.disabled = true;
  runBtn.classList.add('running');
  setStatus(t('status.connecting'), false, true);

  let fullText = '';

  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({student_name: studentName, essay_text: essayText, essay_url: essayUrl, api_key: apiKey}),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Request failed');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'status') {
            setStatus(event.text, false, true);
          } else if (event.type === 'line') {
            fullText += event.text + '\n';
            streamRaw.textContent = fullText;
            streamRaw.scrollTop = streamRaw.scrollHeight;
          } else if (event.type === 'done') {
            streamRaw.style.display = 'none';
            reportCard.style.display = 'block';
            renderReport(fullText, studentName);
            setStatus(t('status.complete'), false, false);
          } else if (event.type === 'error') {
            throw new Error(event.text);
          }
        } catch (parseErr) { /* skip malformed */ }
      }
    }
  } catch (e) {
    setStatus(e.message, true);
    if (!fullText) { streamRaw.textContent = e.message; }
  } finally {
    runBtn.disabled = false;
    runBtn.classList.remove('running');
  }
});

function setStatus(text, isError = false, loading = false) {
  // Build via DOM nodes, never innerHTML — `text` may originate from server
  // events and must not be interpreted as HTML (stored-XSS guard).
  runStatus.textContent = '';
  if (loading) {
    const sp = document.createElement('span');
    sp.className = 'spinner';
    runStatus.appendChild(sp);
  }
  runStatus.appendChild(document.createTextNode(text));
  runStatus.className = 'status-line' + (isError ? ' error' : '');
  runStatus.style.display = 'flex';
  runStatus.style.alignItems = 'center';
  runStatus.style.gap = '4px';
}

// ── REPORT RENDERER ───────────────────────────────────────────────────────────
function renderReport(raw, studentName) {
  // Parse sections
  const parsed = parseReport(raw);

  const name = parsed.student || studentName.split(' ')[0];
  const total = parsed.total || '—';
  const pct = parsed.percentage ? parsed.percentage + '%' : '';

  let html = `
    <div class="report-header">
      <div>
        <div class="report-student-name">${esc(name)}</div>
        <div class="report-meta">CritiqAI Session Report · Paul–Elder Framework</div>
      </div>
      <div class="report-total-stamp">
        <div class="stamp-score">${esc(total)}<span style="font-size:1.25rem;opacity:0.6">/20</span></div>
        <div class="stamp-label">${esc(pct)} · total score</div>
      </div>
    </div>
    <div class="report-body">`;

  // Essay summary
  if (parsed.mainClaim || parsed.evidence) {
    html += `
      <div>
        <div class="report-section-title">Essay Summary</div>
        ${parsed.mainClaim ? `<div class="report-claim">${esc(parsed.mainClaim)}</div>` : ''}
        ${parsed.evidence ? `<div class="report-evidence"><strong>Evidence cited:</strong> ${esc(parsed.evidence)}</div>` : ''}
      </div>`;
  }

  // Personas
  if (parsed.personas.length) {
    html += `
      <div>
        <div class="report-section-title">Personas Activated</div>
        <div class="persona-tags">
          ${parsed.personas.map(p => `<span class="persona-tag">${esc(p)}</span>`).join('')}
        </div>
        ${parsed.personaReason ? `<div class="persona-reason">${esc(parsed.personaReason)}</div>` : ''}
      </div>`;
  }

  // Debate rounds
  if (parsed.rounds.length) {
    html += `
      <div>
        <div class="report-section-title">Debate Challenges</div>
        <div class="debate-rounds">
          ${parsed.rounds.map((r, i) => `
            <div class="debate-round">
              <div class="round-marker">${i + 1}</div>
              <div class="round-content">
                ${r.persona ? `<div class="round-persona-label">${esc(r.persona)}</div>` : ''}
                <div class="round-question">${esc(r.question)}</div>
              </div>
            </div>`).join('')}
        </div>
      </div>`;
  }

  // Scores
  if (parsed.scores.length) {
    html += `
      <div>
        <div class="report-section-title">Scoring Rubric</div>
        <div class="scores-table">
          ${parsed.scores.map(s => {
            const n = parseInt(s.score) || 0;
            const max = parseInt(s.max) || 5;
            const isHigh = n >= 4;
            const isLow = n <= 2;
            const dots = Array.from({length: max}, (_, i) => {
              const filled = i < n;
              const cls = filled ? (isHigh ? 'filled high' : isLow ? 'filled low' : 'filled') : '';
              return `<span class="score-dot ${cls}"></span>`;
            }).join('');
            return `
              <div class="score-row">
                <span class="score-dim-label">${esc(s.label)}</span>
                <div class="score-dots">${dots}</div>
                <span class="score-num">${esc(s.score)}/${esc(s.max)}</span>
              </div>`;
          }).join('')}
        </div>
      </div>`;
  }

  // Strengths / improve
  if (parsed.strengths || parsed.improve) {
    html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;">`;
    if (parsed.strengths) {
      html += `
        <div>
          <div class="report-section-title">Key Strengths</div>
          <div class="report-chips">
            ${parsed.strengths.split(/[,;·•]+/).map(s => s.trim()).filter(Boolean)
              .map(s => `<span class="report-chip chip-strength">${esc(s)}</span>`).join('')}
          </div>
        </div>`;
    }
    if (parsed.improve) {
      html += `
        <div>
          <div class="report-section-title">Areas to Improve</div>
          <div class="report-chips">
            ${parsed.improve.split(/[,;·•]+/).map(s => s.trim()).filter(Boolean)
              .map(s => `<span class="report-chip chip-improve">${esc(s)}</span>`).join('')}
          </div>
        </div>`;
    }
    html += `</div>`;
  }

  // Next focus
  if (parsed.nextFocus) {
    html += `
      <div>
        <div class="report-section-title">Next Session Focus</div>
        <div class="next-focus">${esc(parsed.nextFocus)}</div>
      </div>`;
  }

  html += `</div>`;
  reportCard.innerHTML = html;
}

function parseReport(raw) {
  const result = {
    student: '', mainClaim: '', evidence: '', personas: [], personaReason: '',
    rounds: [], scores: [], total: '', percentage: '',
    strengths: '', improve: '', nextFocus: '',
  };

  const lines = raw.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    if (/^Student:\s*/i.test(line))
      result.student = line.replace(/^Student:\s*/i, '').trim();

    if (/^Main claim:\s*/i.test(line))
      result.mainClaim = line.replace(/^Main claim:\s*/i, '').trim();

    if (/^Evidence cited:\s*/i.test(line))
      result.evidence = line.replace(/^Evidence cited:\s*/i, '').trim();

    if (/^PERSONAS ACTIVATED:\s*/i.test(line)) {
      const val = line.replace(/^PERSONAS ACTIVATED:\s*/i, '').trim();
      result.personas = val.split(/[,\s]+/).filter(p => /[A-Z_]{3,}/.test(p)).map(p => p.replace(/[^\w]/g, ''));
    }

    if (/^REASON:\s*/i.test(line))
      result.personaReason = line.replace(/^REASON:\s*/i, '').trim();

    // Debate rounds: "Round N [PERSONA]: text"
    const roundMatch = line.match(/^Round\s+(\d+)\s*\[?([A-Z_'S]+)\]?:\s*(.*)/i);
    if (roundMatch) {
      result.rounds.push({persona: roundMatch[2], question: roundMatch[3]});
    }

    // Scores: "- Logical Coherence: 3/5"
    const scoreMatch = line.match(/^[-–]\s*(.+?):\s*(\d+)\s*\/\s*(\d+)/);
    if (scoreMatch && !line.toUpperCase().includes('TOTAL')) {
      result.scores.push({label: scoreMatch[1].trim(), score: scoreMatch[2], max: scoreMatch[3]});
    }

    const totalMatch = line.match(/TOTAL:\s*(\d+)\s*\/\s*20\s*\((\d+)%?\)/i);
    if (totalMatch) { result.total = totalMatch[1]; result.percentage = totalMatch[2]; }

    if (/^KEY STRENGTHS:\s*/i.test(line))
      result.strengths = line.replace(/^KEY STRENGTHS:\s*/i, '').trim();

    if (/^AREAS TO IMPROVE:\s*/i.test(line))
      result.improve = line.replace(/^AREAS TO IMPROVE:\s*/i, '').trim();

    if (/^NEXT SESSION FOCUS:\s*/i.test(line))
      result.nextFocus = line.replace(/^NEXT SESSION FOCUS:\s*/i, '').trim();
  }

  return result;
}

function esc(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── INTERACTIVE DEBATE ────────────────────────────────────────────────────────
let _debateSessionId = null;
let _debateRound = 0;

document.querySelectorAll('input[name="d-mode"]').forEach(r => {
  r.addEventListener('change', () => {
    const isUrl = document.getElementById('d-mode-url').checked;
    document.getElementById('d-essay-text').style.display = isUrl ? 'none' : '';
    document.getElementById('d-essay-url').style.display  = isUrl ? '' : 'none';
  });
});

function debateAddBubble(text, role) {
  // role: 'ai' | 'student'
  const msgs = document.getElementById('d-messages');
  const wrap = document.createElement('div');
  wrap.style.cssText = role === 'ai'
    ? 'display:flex;gap:.5rem;'
    : 'display:flex;gap:.5rem;flex-direction:row-reverse;';

  const avatar = document.createElement('div');
  avatar.style.cssText = 'width:32px;height:32px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;';
  avatar.style.background = role === 'ai' ? 'var(--accent)' : '#4A6741';
  avatar.style.color = '#fff';
  avatar.textContent = role === 'ai' ? 'AI' : 'Me';

  const bubble = document.createElement('div');
  bubble.style.cssText = `max-width:78%;padding:.65rem .9rem;border-radius:12px;font-size:.88rem;line-height:1.55;white-space:pre-wrap;` +
    (role === 'ai'
      ? 'background:#fff;border:1px solid #E0DBD2;color:var(--text);border-top-left-radius:2px;'
      : 'background:#4A6741;color:#fff;border-top-right-radius:2px;');
  bubble.textContent = text;

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
}

function debateAddStatus(text) {
  const msgs = document.getElementById('d-messages');
  const div = document.createElement('div');
  div.style.cssText = 'text-align:center;font-size:.78rem;color:var(--muted);padding:.25rem 0;';
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

async function debateStart() {
  const name = document.getElementById('d-name').value.trim();
  const isUrl = document.getElementById('d-mode-url').checked;
  const essayText = isUrl ? '' : document.getElementById('d-essay-text').value.trim();
  const essayUrl  = isUrl ? document.getElementById('d-essay-url').value.trim() : '';
  const errDiv = document.getElementById('d-setup-error');
  const apiKey = document.getElementById('d-apiKey').value.trim() || document.getElementById('cfg-google-api-key').value.trim();

  errDiv.textContent = '';
  if (!name) { errDiv.textContent = 'Vui lòng nhập tên học sinh.'; return; }
  if (!essayText && !essayUrl) { errDiv.textContent = 'Vui lòng nhập bài luận hoặc URL.'; return; }

  const btn = document.getElementById('d-start-btn');
  btn.disabled = true;
  document.getElementById('d-start-label').textContent = t('btn.starting-debate');

  try {
    const res = await fetch('/api/session/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({student_name: name, essay_text: essayText, essay_url: essayUrl, api_key: apiKey}),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      errDiv.textContent = data.error || 'Unknown error.';
      btn.disabled = false; document.getElementById('d-start-label').textContent = t('btn.start-debate');
      return;
    }

    _debateSessionId = data.session_id;
    _debateRound = data.round;

    document.getElementById('debate-setup').style.display = 'none';
    document.getElementById('debate-chat').style.display = '';
    document.getElementById('d-student-label').textContent = name.split(' ')[0];
    document.getElementById('d-persona-label').textContent = data.personas.join(' + ');
    document.getElementById('d-round-label').textContent = `Round ${data.round}/3`;

    debateAddStatus(`${t('session.started')} · Personas: ${data.personas.join(', ')}`);
    if (data.reasoning) debateAddStatus(data.reasoning);
    debateRemoveThinking();
    debateAddBubble(data.challenge, 'ai');

    document.getElementById('d-response-input').focus();

  } catch (e) {
    debateRemoveThinking();
    errDiv.textContent = 'Connection error: ' + e.message;
    btn.disabled = false; document.getElementById('d-start-label').textContent = t('btn.start-debate');
  }
}

async function debateRespond() {
  const input = document.getElementById('d-response-input');
  const response = input.value.trim();
  if (!response || !_debateSessionId) return;

  const btn = document.getElementById('d-send-btn');
  btn.disabled = true;
  document.getElementById('d-send-label').textContent = t('btn.sending');
  input.disabled = true;

  debateAddBubble(response, 'student');
  input.value = '';
  debateAddThinking();
  const apiKey = document.getElementById('d-apiKey').value.trim() || document.getElementById('cfg-google-api-key').value.trim();

  try {
    const res = await fetch('/api/session/respond', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: _debateSessionId, student_response: response, api_key: apiKey}),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      debateRemoveThinking();
      debateAddStatus('⚠ ' + (data.error || 'Connection error'));
      btn.disabled = false; document.getElementById('d-send-label').textContent = t('btn.send'); input.disabled = false;
      return;
    }

    if (data.complete) {
      debateShowReport(data);
    } else {
      _debateRound = data.round;
      document.getElementById('d-round-label').textContent = `Round ${data.round}/3`;
      debateRemoveThinking();
      debateAddBubble(data.challenge, 'ai');
      btn.disabled = false; document.getElementById('d-send-label').textContent = t('btn.send');
      input.disabled = false; input.focus();
    }

  } catch (e) {
    debateRemoveThinking();
    debateAddStatus('⚠ ' + e.message);
    btn.disabled = false; document.getElementById('d-send-label').textContent = t('btn.send'); input.disabled = false;
  }
}

// ── THINKING INDICATOR ───────────────────────────────────────────────────────
let _thinkingEl = null;

function debateAddThinking() {
  debateRemoveThinking();
  const msgs = document.getElementById('d-messages');
  const wrap = document.createElement('div');
  wrap.className = 'thinking-wrap';
  wrap.id = 'thinking-indicator';

  const avatar = document.createElement('div');
  avatar.style.cssText = 'width:32px;height:32px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;background:var(--accent);color:#fff;';
  avatar.textContent = 'AI';

  const dots = document.createElement('div');
  dots.className = 'thinking-dots';
  dots.innerHTML = '<span class="thinking-dot"></span><span class="thinking-dot"></span><span class="thinking-dot"></span>';

  wrap.appendChild(avatar);
  wrap.appendChild(dots);
  msgs.appendChild(wrap);
  _thinkingEl = wrap;
  msgs.scrollTop = msgs.scrollHeight;
}

function debateRemoveThinking() {
  const el = document.getElementById('thinking-indicator');
  if (el) el.remove();
  _thinkingEl = null;
}

// ── I18N ─────────────────────────────────────────────────────────────────────
let _lang = localStorage.getItem('critiq-lang') || 'en';

const I18N = {
  en: {
    'tab.configure':'Configure','tab.session':'One-shot Demo','tab.interactive':'Interactive Debate','tab.scorer':'Scorer Settings',
    'logo.sub':'Paul–Elder Framework \xb7 Socratic Debate Coach',
    'eyebrow.env':'Environment','eyebrow.mcp':'Argument Scorer MCP','eyebrow.student':'Student','eyebrow.essay':'Essay',
    'eyebrow.interactive':'Interactive Mode','eyebrow.scorer':'Scorer Settings',
    'scorer.desc':'Adjust keyword lists and scoring thresholds for each Paul-Elder dimension.',
    'scorer.title.logical':'Logical Coherence','scorer.title.evidence':'Evidence Quality',
    'scorer.title.counter':'Counterargument Handling','scorer.title.scope':'Scope Awareness',
    'btn.save-settings':'Save settings','saved':'✓ Saved',
    'btn.save-scorer':'Save Scorer Config','scorer.saved':'✓ Scorer config saved',
    'mcp.running':'Running — accepting MCP stdio connections',
    'mcp.stopped':'Stopped — deterministic Paul-Elder scoring, zero LLM tokens',
    'mcp.badge.running':'argument-scorer \xb7 running','mcp.badge.stopped':'argument-scorer',
    'btn.start-server':'Start server','btn.stop-server':'Stop server',
    'btn.run-session':'Run session →',
    'status.enter-name':'Enter student name.','status.provide-essay':'Provide essay text or URL.',
    'status.connecting':'Connecting…','status.running':'Running debate session — this takes ~20s...',
    'status.complete':'Session complete.',
    'label.fullname':'Full name','btn.paste-text':'Paste text','btn.gdoc-url':'Google Doc URL',
    'label.student-name':'Student name','label.essay':'Essay',
    'radio.paste':'Paste text','radio.url':'Google Doc URL',
    'placeholder.essay-text':"Paste the student's essay here...",'placeholder.response':'Enter your response...',
    'btn.start-debate':'Start Session','btn.starting':'Starting...','btn.starting-debate':'Starting...',
    'btn.send':'Send (Ctrl+↵)','btn.sending':'Sending...','hint.ctrl-enter':'Ctrl+Enter to send quickly',
    'error.enter-name':'Please enter student name.','error.enter-essay':'Please enter essay or URL.',
    'btn.new-session':'Start new session',
    'ai.thinking':'AI is thinking...',
    'interactive.desc':'Real student interaction — AI asks questions, you answer, 3 escalating rounds, then receive a report.',
    'session.started':'Session started',
    'report.title':'Session Complete','report.strengths':'Strengths','report.improve':'Areas to improve',
    'report.suggestions':'Suggestions for next session:','report.no-strengths':'(none at 4-5 level)',
    'report.no-gaps':'(no critical gaps)',
    'report.draft-created':'✓ Draft email created in teacher\'s Gmail — awaiting approval before sending.',
    'report.draft-failed':'Gmail MCP not connected — draft could not be created.',
  },
  vi: {
    'tab.configure':'C\xe0i đặt','tab.session':'Demo nhanh','tab.interactive':'Tranh luận','tab.scorer':'Cấu h\xecnh chấm điểm',
    'logo.sub':'Khung Paul–Elder \xb7 Huấn luyện vi\xean tranh luận Socratic',
    'eyebrow.env':'M\xf4i trường','eyebrow.mcp':'MCP chấm điểm','eyebrow.student':'Học sinh','eyebrow.essay':'B\xe0i luận',
    'eyebrow.interactive':'Chế độ tương t\xe1c','eyebrow.scorer':'Cấu h\xecnh chấm điểm',
    'scorer.desc':'Điều chỉnh danh s\xe1ch từ kh\xf3a v\xe0 ngưỡng điểm cho từng chiều Paul-Elder.',
    'scorer.title.logical':'T\xednh logic','scorer.title.evidence':'Chất lượng bằng chứng',
    'scorer.title.counter':'Xử l\xfd phản biện','scorer.title.scope':'Nhận thức phạm vi',
    'btn.save-settings':'Lưu c\xe0i đặt','saved':'✓ Đ\xe3 lưu',
    'btn.save-scorer':'Lưu cấu h\xecnh chấm điểm','scorer.saved':'✓ Đ\xe3 lưu cấu h\xecnh',
    'mcp.running':'Đang chạy — chấp nhận kết nối MCP stdio',
    'mcp.stopped':'Đ\xe3 dừng — chấm điểm Paul-Elder x\xe1c định, kh\xf4ng d\xf9ng LLM',
    'mcp.badge.running':'argument-scorer \xb7 đang chạy','mcp.badge.stopped':'argument-scorer',
    'btn.start-server':'Khởi động server','btn.stop-server':'Dừng server',
    'btn.run-session':'Chạy phi\xean →',
    'status.enter-name':'Vui l\xf2ng nhập t\xean học sinh.','status.provide-essay':'Vui l\xf2ng nhập b\xe0i luận hoặc URL.',
    'status.connecting':'Đang kết nối…','status.running':'Đang chạy phi\xean tranh luận — khoảng 20 gi\xe2y...',
    'status.complete':'Phi\xean ho\xe0n tất.',
    'label.fullname':'Họ v\xe0 t\xean','btn.paste-text':'D\xe1n text','btn.gdoc-url':'Google Doc URL',
    'label.student-name':'T\xean học sinh','label.essay':'B\xe0i luận',
    'radio.paste':'D\xe1n text','radio.url':'Google Doc URL',
    'placeholder.essay-text':'D\xe1n nội dung b\xe0i luận v\xe0o đ\xe2y...','placeholder.response':'Nhập c\xe2u trả lời của bạn...',
    'btn.start-debate':'Bắt đầu Session','btn.starting':'Khởi động...','btn.starting-debate':'Đang khởi động...',
    'btn.send':'Gửi (Ctrl+↵)','btn.sending':'Đang gửi...','hint.ctrl-enter':'Ctrl+Enter để gửi nhanh',
    'error.enter-name':'Vui l\xf2ng nhập t\xean học sinh.','error.enter-essay':'Vui l\xf2ng nhập b\xe0i luận hoặc URL.',
    'btn.new-session':'Bắt đầu session mới',
    'ai.thinking':'AI đang suy nghĩ...',
    'interactive.desc':'Học sinh tương t\xe1c thật — AI đặt c\xe2u hỏi, bạn trả lời, 3 v\xf2ng leo thang, rồi nhận b\xe1o c\xe1o.',
    'session.started':'Đ\xe3 bắt đầu session',
    'report.title':'Ho\xe0n tất phiên','report.strengths':'Điểm mạnh','report.improve':'Cần cải thiện',
    'report.suggestions':'Gợi ý cho session tiếp theo:','report.no-strengths':'(chưa đạt mức 4-5)',
    'report.no-gaps':'(không có điểm yếu nghiêm trọng)',
    'report.draft-created':'✓ Đ\xe3 tạo draft email trong Gmail giáo vi\xean — chờ ph\xea duyệt trước khi gửi.',
    'report.draft-failed':'Gmail MCP chưa kết nối — kh\xf4ng tạo được draft.',
  },
  ja: {
    'tab.configure':'設定','tab.session':'デモ','tab.interactive':'ディベート','tab.scorer':'採点設定',
    'logo.sub':'Paul–Elderフレームワーク \xb7 ソクラテス式ディベートコーチ',
    'eyebrow.env':'環境設定','eyebrow.mcp':'MCPスコアラー','eyebrow.student':'学生','eyebrow.essay':'論文',
    'eyebrow.interactive':'インタラクティブモード','eyebrow.scorer':'採点設定',
    'scorer.desc':'Paul-Elderの各次元のキーワードリストと採点間値を調整します。',
    'scorer.title.logical':'論理的整合性','scorer.title.evidence':'証拠の質',
    'scorer.title.counter':'反論への対応','scorer.title.scope':'範囲の認識',
    'btn.save-settings':'設定を保存','saved':'✓ 保存しました',
    'btn.save-scorer':'採点設定を保存','scorer.saved':'✓ 設定を保存しました',
    'mcp.running':'稼働中 — MCP stdio接続を受け付けています',
    'mcp.stopped':'停止中 — 決定論的Paul-Elder採点、LLMトークン不使用',
    'mcp.badge.running':'argument-scorer \xb7 稼働中','mcp.badge.stopped':'argument-scorer',
    'btn.start-server':'サーバー起動','btn.stop-server':'サーバー停止',
    'btn.run-session':'セッション実行 →',
    'status.enter-name':'学生名を入力してください。','status.provide-essay':'論文テキストまたはURLを入力してください。',
    'status.connecting':'接続中…','status.running':'ディベートセッション実行中 — 約20秒かかります...',
    'status.complete':'セッション完了。',
    'label.fullname':'氏名','btn.paste-text':'テキストを貼り付け','btn.gdoc-url':'Google Doc URL',
    'label.student-name':'学生名','label.essay':'論文',
    'radio.paste':'テキストを貼り付け','radio.url':'Google Doc URL',
    'placeholder.essay-text':'論文をここに貼り付けてください...','placeholder.response':'返答を入力してください...',
    'btn.start-debate':'セッション開始','btn.starting':'起動中...','btn.starting-debate':'起動中...',
    'btn.send':'送信 (Ctrl+↵)','btn.sending':'送信中...','hint.ctrl-enter':'Ctrl+Enterで素早く送信',
    'error.enter-name':'学生名を入力してください。','error.enter-essay':'論文またはURLを入力してください。',
    'btn.new-session':'新しいセッションを開始',
    'ai.thinking':'AIが考え中...',
    'interactive.desc':'リアルな学生インタラクション — AIが質問し、あなたが答え、3ラウンドのエスカレーション後にレポートを受け取ります。',
    'session.started':'セッション開始',
    'report.title':'セッション完了','report.strengths':'強み','report.improve':'改善点',
    'report.suggestions':'次回セッションへの提案:','report.no-strengths':'(4-5レベル未達)',
    'report.no-gaps':'(重大な弱点なし)',
    'report.draft-created':'✓ 教師のGmailにドラフトメールを作成しました — 送信前に承認が必要です。',
    'report.draft-failed':'Gmail MCPが接続されていません — ドラフトを作成できませんでした。',
  }
};

function t(key) { return (I18N[_lang] || I18N.en)[key] || I18N.en[key] || key; }

function setLang(lang) {
  _lang = lang;
  localStorage.setItem('critiq-lang', lang);
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.toggle('active', b.dataset.lang === lang));

  // Tabs
  document.querySelector('[data-tab="configure"]').textContent = t('tab.configure');
  document.querySelector('[data-tab="session"]').textContent = t('tab.session');
  document.querySelector('[data-tab="interactive"]').textContent = t('tab.interactive');
  document.querySelector('[data-tab="scorer"]').textContent = t('tab.scorer');

  // Logo subtitle
  document.querySelector('.logo-sub').textContent = t('logo.sub');

  // Section eyebrows
  const eyebrows = {
    'eyebrow-env':'eyebrow.env','eyebrow-mcp':'eyebrow.mcp','eyebrow-student':'eyebrow.student',
    'eyebrow-essay':'eyebrow.essay','eyebrow-interactive':'eyebrow.interactive','eyebrow-scorer':'eyebrow.scorer',
  };
  Object.entries(eyebrows).forEach(([id, key]) => { const el = document.getElementById(id); if (el) el.textContent = t(key); });

  // Buttons
  const saveBtn = document.getElementById('saveConfigBtn');
  if (saveBtn) saveBtn.textContent = t('btn.save-settings');
  const saveScorerBtn = document.getElementById('saveScorerBtn');
  if (saveScorerBtn) saveScorerBtn.textContent = t('btn.save-scorer');
  const runBtn2 = document.getElementById('runBtn');
  if (runBtn2) runBtn2.textContent = t('btn.run-session');
  const startLabel = document.getElementById('d-start-label');
  if (startLabel) startLabel.textContent = t('btn.start-debate');
  const sendLabel = document.getElementById('d-send-label');
  if (sendLabel) sendLabel.textContent = t('btn.send');
  const hintCtrl = document.getElementById('d-hint-ctrl');
  if (hintCtrl) hintCtrl.textContent = t('hint.ctrl-enter');

  // Interactive desc + form labels
  const idesc = document.getElementById('interactive-desc');
  if (idesc) idesc.textContent = t('interactive.desc');
  const dLabelName = document.getElementById('d-label-name');
  if (dLabelName) dLabelName.textContent = t('label.student-name');
  const dLabelEssay = document.getElementById('d-label-essay');
  if (dLabelEssay) dLabelEssay.textContent = t('label.essay');
  const dLabelModeText = document.getElementById('d-label-mode-text');
  if (dLabelModeText) dLabelModeText.textContent = t('radio.paste');
  const dLabelModeUrl = document.getElementById('d-label-mode-url');
  if (dLabelModeUrl) dLabelModeUrl.textContent = t('radio.url');
  const dEssayText = document.getElementById('d-essay-text');
  if (dEssayText) dEssayText.placeholder = t('placeholder.essay-text');
  const dResponseInput = document.getElementById('d-response-input');
  if (dResponseInput) dResponseInput.placeholder = t('placeholder.response');

  // Scorer desc + titles
  const sdesc = document.getElementById('scorer-desc');
  if (sdesc) sdesc.textContent = t('scorer.desc');
  ['logical','evidence','counter','scope'].forEach(dim => {
    const el = document.getElementById('scorer-title-' + dim);
    if (el) el.textContent = t('scorer.title.' + dim);
  });

  // MCP UI
  updateMcpUI();
}

// Wire lang buttons
document.querySelectorAll('.lang-btn').forEach(btn => {
  btn.addEventListener('click', () => setLang(btn.dataset.lang));
});
setLang(_lang);

// ── SCORER CONFIG ─────────────────────────────────────────────────────────────
const SCORER_DIMS = ['logical','evidence','counter','scope'];
const SCORER_DIM_KEYS = {
  logical: 'logical_coherence', evidence: 'evidence_quality',
  counter: 'counterargument_handling', scope: 'scope_awareness',
};

async function loadScorerConfig() {
  try {
    const res = await fetch('/api/scorer/config');
    const cfg = await res.json();
    SCORER_DIMS.forEach(dim => {
      const key = SCORER_DIM_KEYS[dim];
      const d = cfg[key];
      if (!d) return;
      const posEl = document.getElementById('scorer-pos-' + dim);
      const negEl = document.getElementById('scorer-neg-' + dim);
      if (posEl) posEl.value = (d.positive_keywords || []).join(', ');
      if (negEl) negEl.value = (d.negative_keywords || []).join(', ');
      ['5','4','3'].forEach(n => {
        const el = document.getElementById('scorer-thresh' + n + '-' + dim);
        if (el && d['thresh_' + n + '_min_pos'] !== undefined) el.value = d['thresh_' + n + '_min_pos'];
      });
      ['5','4'].forEach(n => {
        const el = document.getElementById('scorer-maxneg' + n + '-' + dim);
        if (el && d['thresh_' + n + '_max_neg'] !== undefined) el.value = d['thresh_' + n + '_max_neg'];
      });
    });
  } catch (e) { /* silent */ }
}
loadScorerConfig();

document.getElementById('saveScorerBtn').addEventListener('click', async () => {
  const payload = {};
  SCORER_DIMS.forEach(dim => {
    const key = SCORER_DIM_KEYS[dim];
    const posEl = document.getElementById('scorer-pos-' + dim);
    const negEl = document.getElementById('scorer-neg-' + dim);
    payload[key] = {
      positive_keywords: (posEl ? posEl.value : '').split(',').map(s => s.trim()).filter(Boolean),
      negative_keywords: (negEl ? negEl.value : '').split(',').map(s => s.trim()).filter(Boolean),
      thresh_5_min_pos: parseInt(document.getElementById('scorer-thresh5-' + dim)?.value) || 3,
      thresh_4_min_pos: parseInt(document.getElementById('scorer-thresh4-' + dim)?.value) || 2,
      thresh_3_min_pos: parseInt(document.getElementById('scorer-thresh3-' + dim)?.value) || 1,
      thresh_5_max_neg: parseInt(document.getElementById('scorer-maxneg5-' + dim)?.value) || 0,
      thresh_4_max_neg: parseInt(document.getElementById('scorer-maxneg4-' + dim)?.value) || 1,
    };
  });
  try {
    await fetch('/api/scorer/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const fb = document.getElementById('scorerFeedback');
    fb.textContent = t('scorer.saved');
    fb.classList.add('visible');
    setTimeout(() => fb.classList.remove('visible'), 2200);
  } catch (e) { alert('Failed: ' + e.message); }
});

function debateShowReport(data) {
  const report = data.report;
  const scores = report.scores || {};
  const dims = [
    {key:'logical_coherence', label:'Logical Coherence'},
    {key:'evidence_quality', label:'Evidence Quality'},
    {key:'counterargument_handling', label:'Counterargument Handling'},
    {key:'scope_awareness', label:'Scope Awareness'},
  ];

  // Store email preview for the modal
  _emailPreview = data.email_preview || null;

  function scoreBars(dims, scores) {
    return dims.map(d => {
      const v = scores[d.key] || 0;
      const pct = (v / 5) * 100;
      const color = v >= 4 ? '#4A6741' : v >= 3 ? '#B8860B' : 'var(--accent)';
      return `<div style="margin-bottom:.6rem;">
        <div style="display:flex;justify-content:space-between;font-size:.82rem;margin-bottom:.2rem;">
          <span>${esc(d.label)}</span><span style="font-weight:600;">${v}/5</span>
        </div>
        <div style="background:#E0DBD2;border-radius:4px;height:6px;">
          <div style="background:${color};width:${pct}%;height:6px;border-radius:4px;transition:width .4s;"></div>
        </div>
      </div>`;
    }).join('');
  }

  const draftNote = data.draft_created
    ? `<p style="font-size:.82rem;color:#4A6741;margin-top:.75rem;">${t('report.draft-created')}</p>`
    : `<p style="font-size:.82rem;color:var(--muted);margin-top:.75rem;">${t('report.draft-failed')}</p>`;

  const showEmailBtn = data.email_preview
    ? `<button class="btn btn-run" onclick="showGmailPreview()" style="margin-top:.75rem;font-size:.82rem;padding:.45rem 1rem;background:#4285F4;display:inline-flex;align-items:center;gap:.4rem;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0"><rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="2,4 12,13 22,4"/></svg>
        View Gmail Draft Preview
       </button>`
    : '';

  const strengths = (report.key_strengths || []).map(s => `<li>${esc(s)}</li>`).join('');
  const weaknesses = (report.key_weaknesses || []).map(w => `<li>${esc(w)}</li>`).join('');
  const suggestions = (report.improvement_suggestions || []).map(s => `<li>${esc(s)}</li>`).join('');

  document.getElementById('debate-chat').style.display = 'none';
  const reportDiv = document.getElementById('debate-report');
  reportDiv.style.display = '';
  reportDiv.innerHTML = `
    <div style="border:2px solid var(--accent);border-radius:10px;padding:1.5rem;">
      <p class="section-eyebrow">${t('report.title')}</p>
      <h2 style="margin:.25rem 0 1rem;font-size:1.3rem;">
        ${esc(report.student_name)} — ${report.total_score}/${report.max_possible}
        <span style="font-size:.9rem;color:var(--muted);">(${report.percentage}%)</span>
      </h2>
      ${scoreBars(dims, scores)}
      <hr style="border:none;border-top:1px solid #E0DBD2;margin:1rem 0;" />
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;font-size:.85rem;">
        <div>
          <strong style="color:#4A6741;">${t('report.strengths')}</strong>
          <ul style="margin:.35rem 0 0 1rem;padding:0;">${strengths || `<li>${t('report.no-strengths')}</li>`}</ul>
        </div>
        <div>
          <strong style="color:var(--accent);">${t('report.improve')}</strong>
          <ul style="margin:.35rem 0 0 1rem;padding:0;">${weaknesses || `<li>${t('report.no-gaps')}</li>`}</ul>
        </div>
      </div>
      <div style="margin-top:1rem;font-size:.85rem;">
        <strong>${t('report.suggestions')}</strong>
        <ol style="margin:.35rem 0 0 1rem;padding:0;">${suggestions}</ol>
      </div>
      ${draftNote}
      ${showEmailBtn}
      <button class="btn btn-run" onclick="location.reload()" style="margin-top:1.25rem;font-size:.85rem;padding:.5rem 1rem;">
        ${t('btn.new-session')}
      </button>
    </div>`;
}

// ── GMAIL PREVIEW ─────────────────────────────────────────────────────────────
let _emailPreview = null;

function showGmailPreview() {
  if (!_emailPreview) return;
  document.getElementById('gmail-preview-to').textContent = _emailPreview.to || '(not configured)';
  document.getElementById('gmail-preview-subject').textContent = _emailPreview.subject || '';
  document.getElementById('gmail-preview-body').textContent = _emailPreview.body || '';
  document.getElementById('gmailPreviewOverlay').style.display = 'flex';
  // Allow closing with Escape key
  document.addEventListener('keydown', function onEsc(e) {
    if (e.key === 'Escape') {
      document.getElementById('gmailPreviewOverlay').style.display = 'none';
      document.removeEventListener('keydown', onEsc);
    }
  }, {once: true});
}

// Click outside the modal to close
document.getElementById('gmailPreviewOverlay').addEventListener('click', function(e) {
  if (e.target === this) this.style.display = 'none';
});

// ── SHOW RESULTS TOGGLE ──────────────────────────────────────────────────────
let _showStudentResults = false;

async function loadShowResultsSetting() {
  try {
    const res = await fetch('/api/config');
    const data = await res.json();
    _showStudentResults = data['SHOW_STUDENT_RESULTS'] === 'true';
    _applyShowResultsUI();
  } catch (e) { /* silent */ }
}

function _applyShowResultsUI() {
  const toggle = document.getElementById('show-results-toggle');
  const knob = document.getElementById('show-results-knob');
  const label = document.getElementById('show-results-label');
  const desc = document.getElementById('show-results-desc');
  if (!toggle) return;
  if (_showStudentResults) {
    toggle.style.background = 'var(--green)';
    knob.style.transform = 'translateX(18px)';
    label.textContent = 'ON';
    label.style.color = 'var(--green)';
    desc.textContent = 'After debate ends, student will see their score breakdown';
  } else {
    toggle.style.background = 'var(--border-mid)';
    knob.style.transform = 'translateX(0)';
    label.textContent = 'OFF';
    label.style.color = 'var(--muted)';
    desc.textContent = 'After debate ends, student sees a message to wait for teacher';
  }
}

async function toggleShowResults() {
  _showStudentResults = !_showStudentResults;
  _applyShowResultsUI();
  try {
    await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({SHOW_STUDENT_RESULTS: String(_showStudentResults)}),
    });
  } catch (e) { /* silent */ }
}

loadShowResultsSetting();

// ── STUDENT LINK ──────────────────────────────────────────────────────────────
(function() {
  const base = window.location.origin;
  const lang = _lang || 'en';
  const url = base + '/student?lang=' + lang;
  const el = document.getElementById('student-link-text');
  const openEl = document.getElementById('student-link-open');
  if (el) el.textContent = url;
  if (openEl) openEl.href = url;
})();

function copyStudentLink(btn) {
  const base = window.location.origin;
  const lang = _lang || 'en';
  const url = base + '/student?lang=' + lang;
  navigator.clipboard.writeText(url).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1800);
  }).catch(() => {
    const el = document.getElementById('student-link-text');
    if (el) el.select();
  });
}
</script>
</body>
</html>"""

# Rename the existing HTML to TEACHER_HTML
TEACHER_HTML = HTML

# ── STUDENT HTML ───────────────────────────────────────────────────────────────
STUDENT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CritiqAI — Debate Session</title>
<link rel="stylesheet" href="/static/critiqai.css">
<style>
/* Student-specific additions — teacher CSS is served from /static/critiqai.css */
.s-rdot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; background: var(--border-mid); transition: background .3s;
}
.s-rdot.done   { background: var(--green); }
.s-rdot.active { background: var(--accent); box-shadow: 0 0 6px rgba(168,50,37,.4); }
.student-badge {
  font-size: .68rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  background: rgba(45,63,110,.08); color: var(--accent-2);
  border: 1px solid rgba(45,63,110,.25); padding: .25rem .75rem; border-radius: 20px;
}
</style>
</head>
<body>

<header class="site-header">
  <div class="logo">
    <div class="logo-name">Critiq<span>AI</span></div>
    <div class="logo-sub" id="s-logo-sub">Socratic Debate Coach</div>
  </div>
  <div class="header-right">
    <div class="lang-switcher" role="group" aria-label="Language">
      <button class="lang-btn active" data-lang="en" type="button">EN</button>
      <button class="lang-btn" data-lang="vi" type="button">VI</button>
      <button class="lang-btn" data-lang="ja" type="button">日本語</button>
    </div>
    <span class="student-badge" id="s-role-badge">Student Session</span>
  </div>
</header>

<main class="main">

  <!-- ── SETUP PANEL ── -->
  <div id="s-setup">
    <p class="section-eyebrow" id="s-eyebrow">Debate Session</p>

    <div class="fields-grid" style="margin-bottom:1rem;">
      <div class="field-group">
        <label class="field-label" id="s-label-name" for="s-name">Your name</label>
        <input class="field-input" id="s-name" type="text" placeholder="Nguyen Van A">
      </div>
      <div class="field-group">
        <label class="field-label" for="s-apikey">Gemini API Key
          <span style="color:var(--border-mid);font-weight:400;text-transform:none;letter-spacing:0;">(optional)</span>
        </label>
        <div class="field-row">
          <input class="field-input secret" id="s-apikey" type="password" placeholder="AIza...">
          <button class="reveal-btn" type="button" onclick="toggleReveal('s-apikey',this)">show</button>
        </div>
        <div style="font-size:.65rem;color:var(--muted);margin-top:.25rem;">Only if your teacher has not pre-configured a key.</div>
      </div>
    </div>

    <div class="field-group" style="margin-bottom:.75rem;">
      <label class="field-label" id="s-label-essay">Essay</label>
      <div class="input-mode-toggle" role="group">
        <button class="mode-btn active" data-mode="text" type="button" id="s-mode-text">Paste text</button>
        <button class="mode-btn" data-mode="url"  type="button" id="s-mode-url">Google Doc URL</button>
      </div>
      <textarea class="field-textarea" id="s-essay-text" rows="7"
        placeholder="Paste your essay here (up to 2000 words)..."></textarea>
      <input class="field-input" id="s-essay-url" type="url"
        placeholder="https://docs.google.com/document/d/..." style="display:none;margin-top:.5rem;">
    </div>

    <div style="display:flex;align-items:center;gap:1rem;margin-top:1.25rem;">
      <button class="btn btn-run" id="s-start-btn" onclick="studentStart()">
        <span id="s-start-label">Start Session</span>
      </button>
      <span class="status-line" id="s-setup-error" style="color:var(--red);display:none;"></span>
    </div>
  </div><!-- /s-setup -->

  <!-- ── CHAT PANEL ── -->
  <div id="s-chat" style="display:none;">

    <div style="display:flex;align-items:center;gap:.75rem;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:.65rem 1rem;margin-bottom:1rem;">
      <div style="display:flex;gap:.4rem;">
        <span class="s-rdot" id="sd1"></span>
        <span class="s-rdot" id="sd2"></span>
        <span class="s-rdot" id="sd3"></span>
      </div>
      <span style="font-size:.8rem;color:var(--muted);flex:1;" id="s-round-label">Round 1 / 3</span>
      <span id="s-persona-chip" style="font-size:.68rem;font-weight:600;letter-spacing:.05em;background:rgba(45,63,110,.08);color:var(--accent-2);border:1px solid rgba(45,63,110,.22);padding:.2rem .6rem;border-radius:20px;"></span>
    </div>

    <div id="s-messages" style="background:var(--ground);border:1px solid #E0DBD2;border-radius:8px;padding:1rem;min-height:200px;max-height:480px;overflow-y:auto;display:flex;flex-direction:column;gap:.75rem;margin-bottom:1rem;scroll-behavior:smooth;"></div>

    <div style="display:flex;gap:.5rem;">
      <textarea id="s-response" class="field-textarea" rows="3"
        placeholder="Enter your response..."
        style="flex:1;min-height:80px;resize:vertical;"
        onkeydown="if(event.ctrlKey&&event.key==='Enter'){studentSend();}"></textarea>
      <button class="btn btn-run" id="s-send-btn" onclick="studentSend()"
        style="align-self:flex-end;white-space:nowrap;">
        <span id="s-send-label">Send (Ctrl+↵)</span>
      </button>
    </div>
    <p style="font-size:.75rem;color:var(--muted);margin-top:.35rem;" id="s-hint-ctrl">Ctrl+Enter to send quickly</p>

  </div><!-- /s-chat -->

  <!-- ── RESULT PANEL ── -->
  <div id="s-report" style="display:none;"></div>

</main>

<script>
// ── LANGUAGE ─────────────────────────────────────────────────────────────────
let _lang = localStorage.getItem('critiq-lang') || 'en';
(function() {
  const p = new URLSearchParams(window.location.search);
  const u = p.get('lang');
  if (u && ['en','vi','ja'].includes(u)) { _lang = u; localStorage.setItem('critiq-lang', u); }
})();

const I18N = {
  en: {
    'logo.sub':           'Socratic Debate Coach',
    'eyebrow':            'Debate Session',
    'role.badge':         'Student Session',
    'label.name':         'Your name',
    'label.essay':        'Essay',
    'paste.text':         'Paste text',
    'gdoc.url':           'Google Doc URL',
    'ph.essay':           'Paste your essay here (up to 2000 words)...',
    'ph.response':        'Enter your response...',
    'btn.start':          'Start Session',
    'btn.starting':       'Starting…',
    'btn.send':           'Send (Ctrl+↵)',
    'btn.sending':        'Sending…',
    'hint.ctrl':          'Ctrl+Enter to send quickly',
    'session.started':    'Session started',
    'btn.new':            'Start a New Session',
    'score.logical':      'Logical Coherence',
    'score.evidence':     'Evidence Quality',
    'score.counter':      'Counterargument Handling',
    'score.scope':        'Scope Awareness',
    'report.title':       'Session Report',
    'report.strengths':   'Key Strengths',
    'report.improve':     'Areas to Improve',
    'report.suggestions': 'Next Session Focus',
    'complete.title':     'Session Complete',
    'complete.sub':       'Your responses have been recorded. Your teacher will review and share your results.',
    'complete.note':      'Awaiting teacher review before results are shared.',
    'err.name':           'Please enter your name.',
    'err.essay':          'Please provide your essay text or Google Doc URL.',
  },
  vi: {
    'logo.sub':           'Huấn luyện viên tranh luận Socratic',
    'eyebrow':            'Phiên tranh luận',
    'role.badge':         'Học sinh',
    'label.name':         'Họ và tên',
    'label.essay':        'Bài luận',
    'paste.text':         'Dán text',
    'gdoc.url':           'Google Doc URL',
    'ph.essay':           'Dán bài luận của bạn vào đây (tối đa 2000 từ)...',
    'ph.response':        'Nhập câu trả lời của bạn...',
    'btn.start':          'Bắt đầu phiên tranh luận',
    'btn.starting':       'Đang khởi động…',
    'btn.send':           'Gửi (Ctrl+↵)',
    'btn.sending':        'Đang gửi…',
    'hint.ctrl':          'Ctrl+Enter để gửi nhanh',
    'session.started':    'Đã bắt đầu phiên',
    'btn.new':            'Bắt đầu phiên mới',
    'score.logical':      'Tính logic',
    'score.evidence':     'Chất lượng bằng chứng',
    'score.counter':      'Xử lý phản biện',
    'score.scope':        'Nhận thức phạm vi',
    'report.title':       'Báo cáo phiên',
    'report.strengths':   'Điểm mạnh',
    'report.improve':     'Cần cải thiện',
    'report.suggestions': 'Trọng tâm phiên tiếp theo',
    'complete.title':     'Phiên tranh luận hoàn tất',
    'complete.sub':       'Các phản hồi của bạn đã được ghi lại. Giáo viên sẽ xem xét và chia sẻ kết quả.',
    'complete.note':      'Chờ giáo viên xem xét trước khi chia sẻ kết quả.',
    'err.name':           'Vui lòng nhập tên của bạn.',
    'err.essay':          'Vui lòng nhập bài luận hoặc URL.',
  },
  ja: {
    'logo.sub':           'ソクラテス式ディベートコーチ',
    'eyebrow':            'ディベートセッション',
    'role.badge':         '学生セッション',
    'label.name':         'お名前',
    'label.essay':        '論文',
    'paste.text':         'テキストを貼り付け',
    'gdoc.url':           'Google Doc URL',
    'ph.essay':           '論文をここに貼り付けてください（最大00語）...',
    'ph.response':        '返答を入力してください...',
    'btn.start':          'セッション開始',
    'btn.starting':       '起動中…',
    'btn.send':           '送信 (Ctrl+↵)',
    'btn.sending':        '送信中…',
    'hint.ctrl':          'Ctrl+Enterで素早く送信',
    'session.started':    'セッション開始',
    'btn.new':            '新しいセッションを開始',
    'score.logical':      '論理的一貫性',
    'score.evidence':     '証拠の質',
    'score.counter':      '反論への対応',
    'score.scope':        '範囲の認識',
    'report.title':       'セッションレポート',
    'report.strengths':   '強み',
    'report.improve':     '改善点',
    'report.suggestions': '次回の焦点',
    'complete.title':     'セッション完了',
    'complete.sub':       'あなたの回答が記録されました。教師が確認後、結果を共有します。',
    'complete.note':      '教師の確認後に結果が共有されます。',
    'err.name':           'お名前を入力してください。',
    'err.essay':          '論文またはURLを入力してください。',
  },
};

function t(key) { return (I18N[_lang]||I18N.en)[key] || I18N.en[key] || key; }

function setLang(l) {
  _lang = l; localStorage.setItem('critiq-lang', l);
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.toggle('active', b.dataset.lang === l));
  applyI18n();
}

function applyI18n() {
  const set = (id, k) => { const el = document.getElementById(id); if (el) el.textContent = t(k); };
  const ph  = (id, k) => { const el = document.getElementById(id); if (el) el.placeholder = t(k); };
  set('s-logo-sub',   'logo.sub');
  set('s-role-badge', 'role.badge');
  set('s-eyebrow',    'eyebrow');
  set('s-label-name', 'label.name');
  set('s-label-essay','label.essay');
  set('s-mode-text',  'paste.text');
  set('s-mode-url',   'gdoc.url');
  set('s-start-label','btn.start');
  set('s-send-label', 'btn.send');
  set('s-hint-ctrl',  'hint.ctrl');
  ph('s-essay-text',  'ph.essay');
  ph('s-response',    'ph.response');
}

document.querySelectorAll('.lang-btn').forEach(b => b.addEventListener('click', () => setLang(b.dataset.lang)));
setLang(_lang);

// ── INPUT MODE TOGGLE ─────────────────────────────────────────────────────────
document.getElementById('s-mode-text').addEventListener('click', () => {
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('s-mode-text').classList.add('active');
  document.getElementById('s-essay-text').style.display = '';
  document.getElementById('s-essay-url').style.display = 'none';
});
document.getElementById('s-mode-url').addEventListener('click', () => {
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('s-mode-url').classList.add('active');
  document.getElementById('s-essay-text').style.display = 'none';
  document.getElementById('s-essay-url').style.display = '';
});

// ── REVEAL ────────────────────────────────────────────────────────────────────
function toggleReveal(id, btn) {
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
  btn.textContent = el.type === 'password' ? 'show' : 'hide';
}

// ── ROUND DOTS ────────────────────────────────────────────────────────────────
function updateRoundDots(round) {
  [1,2,3].forEach(i => {
    const el = document.getElementById('sd'+i);
    el.className = 's-rdot' + (i < round ? ' done' : i === round ? ' active' : '');
  });
  document.getElementById('s-round-label').textContent = 'Round ' + round + ' / 3';
}

// ── BUBBLES ───────────────────────────────────────────────────────────────────
function addBubble(text, role) {
  const msgs = document.getElementById('s-messages');
  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;gap:.5rem;' + (role !== 'ai' ? 'flex-direction:row-reverse;' : '');
  const av = document.createElement('div');
  av.style.cssText = 'width:32px;height:32px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;color:#fff;background:' + (role === 'ai' ? 'var(--accent-2)' : 'var(--accent)') + ';';
  av.textContent = role === 'ai' ? 'AI' : 'Me';
  const bbl = document.createElement('div');
  bbl.style.cssText = 'max-width:78%;padding:.65rem .9rem;border-radius:2px;font-size:.88rem;line-height:1.55;white-space:pre-wrap;' +
    (role === 'ai' ? 'background:#fff;border:1px solid #E0DBD2;color:var(--text);' : 'background:var(--accent-2);color:#fff;');
  bbl.textContent = text;
  wrap.appendChild(av); wrap.appendChild(bbl);
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
}

function addStatus(text) {
  const msgs = document.getElementById('s-messages');
  const div = document.createElement('div');
  div.style.cssText = 'text-align:center;font-size:.78rem;color:var(--muted);padding:.25rem 0;';
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addThinking() {
  removeThinking();
  const msgs = document.getElementById('s-messages');
  const wrap = document.createElement('div');
  wrap.id = 's-thinking'; wrap.className = 'thinking-wrap';
  const av = document.createElement('div');
  av.style.cssText = 'width:32px;height:32px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;background:var(--accent-2);color:#fff;';
  av.textContent = 'AI';
  const dots = document.createElement('div'); dots.className = 'thinking-dots';
  dots.innerHTML = '<span class="thinking-dot"></span><span class="thinking-dot"></span><span class="thinking-dot"></span>';
  wrap.appendChild(av); wrap.appendChild(dots);
  msgs.appendChild(wrap); msgs.scrollTop = msgs.scrollHeight;
}

function removeThinking() { const el = document.getElementById('s-thinking'); if (el) el.remove(); }

// ── SESSION START ─────────────────────────────────────────────────────────────
let _sid = null;

async function studentStart() {
  const name     = document.getElementById('s-name').value.trim();
  const isUrl    = document.getElementById('s-mode-url').classList.contains('active');
  const essayTxt = isUrl ? '' : document.getElementById('s-essay-text').value.trim();
  const essayUrl = isUrl ? document.getElementById('s-essay-url').value.trim() : '';
  const apiKey   = document.getElementById('s-apikey').value.trim();
  const errEl    = document.getElementById('s-setup-error');

  errEl.textContent = ''; errEl.style.display = 'none';
  if (!name)                { errEl.textContent = t('err.name');  errEl.style.display = ''; return; }
  if (!essayTxt && !essayUrl){ errEl.textContent = t('err.essay'); errEl.style.display = ''; return; }

  const btn = document.getElementById('s-start-btn'); btn.disabled = true;
  document.getElementById('s-start-label').textContent = t('btn.starting');

  try {
    const res  = await fetch('/api/session/start', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({student_name:name, essay_text:essayTxt, essay_url:essayUrl, api_key:apiKey}),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      errEl.textContent = data.error || 'Unknown error.'; errEl.style.display = '';
      btn.disabled = false; document.getElementById('s-start-label').textContent = t('btn.start');
      return;
    }
    _sid = data.session_id;
    document.getElementById('s-setup').style.display = 'none';
    document.getElementById('s-chat').style.display  = '';
    document.getElementById('s-persona-chip').textContent = (data.personas || []).join(' + ');
    updateRoundDots(data.round || 1);
    addStatus(t('session.started') + (data.personas ? ' · ' + data.personas.join(', ') : ''));
    if (data.reasoning) addStatus(data.reasoning);
    addBubble(data.challenge, 'ai');
    document.getElementById('s-response').focus();
  } catch(e) {
    errEl.textContent = 'Connection error: ' + e.message; errEl.style.display = '';
    btn.disabled = false; document.getElementById('s-start-label').textContent = t('btn.start');
  }
}

// ── SESSION RESPOND ───────────────────────────────────────────────────────────
async function studentSend() {
  const input    = document.getElementById('s-response');
  const response = input.value.trim();
  if (!response || !_sid) return;

  const btn = document.getElementById('s-send-btn'); btn.disabled = true;
  document.getElementById('s-send-label').textContent = t('btn.sending');
  input.disabled = true;

  addBubble(response, 'student'); input.value = '';
  addThinking();

  try {
    const res  = await fetch('/api/session/respond', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({session_id:_sid, student_response:response,
                            api_key: document.getElementById('s-apikey').value.trim()}),
    });
    const data = await res.json();
    removeThinking();

    if (!res.ok || data.error) {
      addStatus('⚠ ' + (data.error || 'Error'));
      btn.disabled = false; document.getElementById('s-send-label').textContent = t('btn.send');
      input.disabled = false; return;
    }

    if (data.complete) {
      document.getElementById('s-chat').style.display = 'none';
      data.show_results && data.report ? showStudentResults(data.report) : showSessionComplete();
    } else {
      updateRoundDots(data.round || 1);
      addBubble(data.challenge, 'ai');
      btn.disabled = false; document.getElementById('s-send-label').textContent = t('btn.send');
      input.disabled = false; input.focus();
    }
  } catch(e) {
    removeThinking(); addStatus('⚠ Connection error: ' + e.message);
    btn.disabled = false; document.getElementById('s-send-label').textContent = t('btn.send');
    input.disabled = false;
  }
}

// ── REPORT (show_results = true) ──────────────────────────────────────────────
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

const SCORE_DIMS = [
  {key:'logical_coherence',        lk:'score.logical'},
  {key:'evidence_quality',         lk:'score.evidence'},
  {key:'counterargument_handling', lk:'score.counter'},
  {key:'scope_awareness',          lk:'score.scope'},
];

function showStudentResults(report) {
  const scores = report.scores || {};
  const total  = report.total_score || scores.total || 0;
  const pct    = report.percentage  || scores.percentage || 0;

  const scoreDots = SCORE_DIMS.map(d => {
    const v = scores[d.key] || 0;
    const cls = v >= 4 ? 'high' : v <= 2 ? 'low' : '';
    const dots = Array.from({length:5}, (_,i) =>
      `<span class="score-dot ${i < v ? 'filled '+cls : ''}"></span>`).join('');
    return `<div class="score-row">
      <span class="score-dim-label">${esc(t(d.lk))}</span>
      <div class="score-dots">${dots}</div>
      <span class="score-num">${v}/5</span>
    </div>`;
  }).join('');

  const chips = (arr, cls) => (arr||[]).map(s => `<span class="report-chip ${cls}">${esc(s)}</span>`).join('');
  const strengths = chips(report.key_strengths,  'chip-strength');
  const gaps      = chips(report.key_weaknesses || report.critical_gaps, 'chip-improve');
  const next      = (report.improvement_suggestions||[])[0] || '';

  const r = document.getElementById('s-report');
  r.innerHTML = `
<div class="report-card">
  <div class="report-header">
    <div>
      <div class="report-student-name">${esc(report.student_name||'')}</div>
      <div class="report-meta">CritiqAI Session Report · Paul–Elder Framework</div>
    </div>
    <div class="report-total-stamp">
      <div class="stamp-score">${total}<span style="font-size:1.25rem;opacity:.6;">/20</span></div>
      <div class="stamp-label">${pct}% · total score</div>
    </div>
  </div>
  <div class="report-body">
    <div>
      <div class="report-section-title">${esc(t('report.title'))}</div>
      <div class="scores-table">${scoreDots}</div>
    </div>
    ${strengths || gaps ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;">
      ${strengths ? `<div><div class="report-section-title">${esc(t('report.strengths'))}</div><div class="report-chips">${strengths}</div></div>` : ''}
      ${gaps      ? `<div><div class="report-section-title">${esc(t('report.improve'))}</div><div class="report-chips">${gaps}</div></div>` : ''}
    </div>` : ''}
    ${next ? `<div>
      <div class="report-section-title">${esc(t('report.suggestions'))}</div>
      <div class="next-focus">${esc(next)}</div>
    </div>` : ''}
    <div><button class="btn btn-ghost" onclick="location.reload()">${esc(t('btn.new'))}</button></div>
  </div>
</div>`;
  r.style.display = '';
}

// ── COMPLETE (show_results = false) ──────────────────────────────────────────
function showSessionComplete() {
  const r = document.getElementById('s-report');
  r.innerHTML = `
<div class="report-card">
  <div class="report-header">
    <div>
      <div class="report-student-name">${esc(t('complete.title'))}</div>
      <div class="report-meta">CritiqAI Debate Session</div>
    </div>
    <div class="report-total-stamp">
      <div style="font-size:2.5rem;line-height:1;">✓</div>
      <div class="stamp-label">Complete</div>
    </div>
  </div>
  <div class="report-body">
    <p style="color:var(--muted);font-size:.9rem;line-height:1.65;">${esc(t('complete.sub'))}</p>
    <div class="next-focus" style="border-left-color:var(--green);">${esc(t('complete.note'))}</div>
    <div><button class="btn btn-ghost" onclick="location.reload()">${esc(t('btn.new'))}</button></div>
  </div>
</div>`;
  r.style.display = '';
}
</script>
</body>
</html>"""


# ── ROUTES ────────────────────────────────────────────────────────────────────

from fastapi.responses import RedirectResponse

@app.get("/", response_class=RedirectResponse)
async def index():
    return RedirectResponse(url="/teacher", status_code=302)


@app.get("/teacher", response_class=HTMLResponse)
async def teacher_dashboard():
    return TEACHER_HTML


@app.get("/student", response_class=HTMLResponse)
async def student_view():
    return STUDENT_HTML


@app.get("/static/critiqai.css")
async def shared_css():
    from fastapi.responses import Response
    start = HTML.index('<style>') + len('<style>')
    end   = HTML.index('</style>')
    return Response(content=HTML[start:end], media_type="text/css")


# Only these keys may be read/written through the dashboard. An open-ended
# .env writer would let any caller inject arbitrary process configuration.
ALLOWED_CONFIG_KEYS = frozenset({
    "GOOGLE_API_KEY", "TEACHER_EMAIL", "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET", "DEBATE_LOG_SHEET_ID", "GEMINI_SANDBOX",
    "SHOW_STUDENT_RESULTS", "GOOGLE_DRIVE_SUBMISSIONS_FOLDER_ID",
    "SCORER_URL", "GEMINI_MODEL", "GOOGLE_CLOUD_PROJECT",
})
# Substrings that mark a value as secret — never echoed back to the client.
_SECRET_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def _is_secret_key(name: str) -> bool:
    return any(m in name.upper() for m in _SECRET_MARKERS)


@app.get("/api/config")
async def get_config():
    """Return config for the dashboard. Secret values are masked so the
    OAuth secret / API key are never sent back over the wire."""
    if not ENV_FILE.exists():
        return JSONResponse({})
    vals = dotenv_values(str(ENV_FILE))
    safe = {}
    for k, v in vals.items():
        if k not in ALLOWED_CONFIG_KEYS:
            continue
        if v and _is_secret_key(k):
            safe[k] = "***configured***"
        else:
            safe[k] = v
    return JSONResponse(safe)


@app.post("/api/config")
async def save_config(request: Request):
    data = await request.json()
    if not ENV_FILE.exists():
        ENV_FILE.touch()
    written = []
    for k, v in data.items():
        # Ignore unknown keys and the masked placeholder (means "unchanged").
        if k not in ALLOWED_CONFIG_KEYS:
            continue
        if v == "***configured***":
            continue
        set_key(str(ENV_FILE), str(k), str(v))
        written.append(k)
    return JSONResponse({"ok": True, "updated": written})


@app.get("/api/mcp/status")
async def mcp_status():
    global _mcp_process
    if SCORER_URL:
        return JSONResponse({"running": True, "mode": "remote", "url": SCORER_URL})
    running = _mcp_process is not None and _mcp_process.poll() is None
    return JSONResponse({"running": running, "pid": _mcp_process.pid if running else None})


@app.post("/api/mcp/start")
async def mcp_start():
    global _mcp_process
    if SCORER_URL:
        return JSONResponse({"status": "remote", "url": SCORER_URL})
    if _mcp_process and _mcp_process.poll() is None:
        return JSONResponse({"status": "already_running", "pid": _mcp_process.pid})
    if not MCP_SCRIPT.exists():
        return JSONResponse({"error": "MCP server script not found."}, status_code=404)
    _mcp_process = subprocess.Popen(
        [sys.executable, str(MCP_SCRIPT)],
        cwd=str(MCP_SCRIPT.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return JSONResponse({"status": "started", "pid": _mcp_process.pid})


@app.post("/api/mcp/stop")
async def mcp_stop():
    global _mcp_process
    if SCORER_URL:
        return JSONResponse({"status": "remote_unmanaged"})
    if _mcp_process and _mcp_process.poll() is None:
        _mcp_process.terminate()
        _mcp_process = None
        return JSONResponse({"status": "stopped"})
    return JSONResponse({"status": "not_running"})


@app.post("/api/run")
async def run_session_endpoint(request: Request):
    data = await request.json()
    student_name = (data.get("student_name") or "").strip()
    essay_text = (data.get("essay_text") or "").strip()
    essay_url = (data.get("essay_url") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not student_name:
        return JSONResponse({"error": "Student name is required."}, status_code=400)

    async def generate():
        async with _api_lock:
            original_api_key = os.environ.get("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key
            try:
                from dotenv import load_dotenv
                load_dotenv(str(ENV_FILE), override=True)

                # Verify key is present
                if not os.environ.get("GOOGLE_API_KEY"):
                    yield f"data: {json.dumps({'type': 'error', 'text': 'Google API Key is required. Please enter it in the Configure tab or the Demo input.'})}\n\n"
                    return

                yield f"data: {json.dumps({'type': 'status', 'text': 'Connecting to Gemini...'})}\n\n"
                await asyncio.sleep(0.05)

                if str(ROOT) not in sys.path:
                    sys.path.insert(0, str(ROOT))
                import agents.orchestrator as orch

                yield f"data: {json.dumps({'type': 'status', 'text': 'Running debate session — this takes ~20s...'})}\n\n"

                result = await orch.run_session(
                    student_name=student_name,
                    essay_text=essay_text,
                    essay_url=essay_url,
                )

                response_text = result.get("response") or ""
                if not response_text:
                    response_text = "(No response returned from model.)"

                for line in response_text.split("\n"):
                    yield f"data: {json.dumps({'type': 'line', 'text': line})}\n\n"
                    await asyncio.sleep(0.018)

                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            except Exception:
                # Log server-side; send only a generic message to the browser
                # (the client renders this text, so never include raw exception detail).
                import traceback
                print("[/api/run] error:\n" + traceback.format_exc(), file=sys.stderr)
                yield f"data: {json.dumps({'type': 'error', 'text': 'Session failed — please retry.'})}\n\n"
            finally:
                if original_api_key is not None:
                    os.environ["GOOGLE_API_KEY"] = original_api_key
                elif "GOOGLE_API_KEY" in os.environ:
                    del os.environ["GOOGLE_API_KEY"]

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── INTERACTIVE DEBATE ENDPOINTS ──────────────────────────────────────────────

@app.post("/api/session/start")
async def session_start(request: Request):
    data = await request.json()
    student_name = (data.get("student_name") or "").strip()
    essay_text = (data.get("essay_text") or "").strip()
    essay_url = (data.get("essay_url") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not student_name:
        return JSONResponse({"error": "Student name required."}, status_code=400)
    if not essay_text and not essay_url:
        return JSONResponse({"error": "Essay text or URL required."}, status_code=400)

    async with _api_lock:
        original_api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key
        try:
            from dotenv import load_dotenv
            load_dotenv(str(ENV_FILE), override=True)

            if not os.environ.get("GOOGLE_API_KEY"):
                return JSONResponse({"error": "Google API Key is required. Please provide it in the UI."}, status_code=400)

            result = await _debate_manager.start_session(
                student_name=student_name,
                essay_text=essay_text,
                essay_url=essay_url,
            )
            if result.get("error"):
                return JSONResponse(result, status_code=400)
            return JSONResponse(result)
        except Exception as exc:
            # Log the full traceback server-side; never leak it to the browser.
            import traceback
            print("[/api/session/start] error:\n" + traceback.format_exc(), file=sys.stderr)
            return JSONResponse({"error": "Internal server error — please retry."}, status_code=500)
        finally:
            if original_api_key is not None:
                os.environ["GOOGLE_API_KEY"] = original_api_key
            elif "GOOGLE_API_KEY" in os.environ:
                del os.environ["GOOGLE_API_KEY"]


@app.post("/api/session/respond")
async def session_respond(request: Request):
    data = await request.json()
    session_id = (data.get("session_id") or "").strip()
    student_response = (data.get("student_response") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not session_id:
        return JSONResponse({"error": "session_id required."}, status_code=400)
    if not student_response:
        return JSONResponse({"error": "student_response required."}, status_code=400)

    async with _api_lock:
        original_api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key
        try:
            from dotenv import load_dotenv
            load_dotenv(str(ENV_FILE), override=True)
            result = await _debate_manager.submit_response(session_id, student_response)
            if result.get("complete"):
                show_results = dotenv_values(str(ENV_FILE)).get("SHOW_STUDENT_RESULTS", "false") == "true"
                result["show_results"] = show_results
            return JSONResponse(result)
        except KeyError:
            return JSONResponse({"error": "Session not found or expired."}, status_code=404)
        except Exception:
            import traceback
            print("[/api/session/respond] error:\n" + traceback.format_exc(), file=sys.stderr)
            return JSONResponse({"error": "Internal server error — please retry."}, status_code=500)
        finally:
            if original_api_key is not None:
                os.environ["GOOGLE_API_KEY"] = original_api_key
            elif "GOOGLE_API_KEY" in os.environ:
                del os.environ["GOOGLE_API_KEY"]


@app.get("/api/scorer/config")
async def get_scorer_config():
    if SCORER_CONFIG_FILE.exists():
        with open(SCORER_CONFIG_FILE) as f:
            return JSONResponse(json.load(f))
    return JSONResponse(DEFAULT_SCORER_CONFIG)


@app.post("/api/scorer/config")
async def save_scorer_config(request: Request):
    # Cap the payload — this file is read on every scoring request, so an
    # unbounded write would be a cheap DoS vector.
    raw = await request.body()
    if len(raw) > 64_000:
        return JSONResponse({"error": "Payload too large."}, status_code=413)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)
    # Validate structure: only the 4 known dimensions, each with keyword lists.
    valid_dims = {"logical_coherence", "evidence_quality",
                  "counterargument_handling", "scope_awareness"}
    if not isinstance(data, dict) or not set(data).issubset(valid_dims):
        return JSONResponse({"error": "Unexpected scorer config schema."}, status_code=400)
    for dim, cfg in data.items():
        if not isinstance(cfg, dict):
            return JSONResponse({"error": f"Invalid entry for {dim}."}, status_code=400)
        for field, val in cfg.items():
            if isinstance(val, list) and len(val) > 500:
                return JSONResponse({"error": f"Too many keywords in {dim}.{field}."}, status_code=400)
    with open(SCORER_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return JSONResponse({"ok": True})


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import logging
    import uvicorn
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    port = int(os.environ.get("PORT", 8000))
    print(f"\nCritiqAI Teacher Dashboard → http://127.0.0.1:{port}/teacher")
    print(f"CritiqAI Student Interface  → http://127.0.0.1:{port}/student\n")
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_level="info")

