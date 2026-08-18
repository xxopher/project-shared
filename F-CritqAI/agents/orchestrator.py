"""
Orchestrator — two modes:
1. Standalone async functions used by DebateSessionManager (real interactive flow)
2. create_orchestrator() for ADK CLI / agents/__init__.py (one-shot demo)
"""

import json
import os

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from google.adk.agents import LlmAgent
from google.genai.types import Content, Part

from .model_config import (
    build_instruction_with_skill,
    get_primary_model,
    run_adk_with_fallback,
)


# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------

_SUMMARIZER_BASE = """You are an academic essay summarizer. Compress the essay into structured JSON.

Output ONLY valid JSON, no markdown fences, no extra text:
{
  "main_claim": "<one sentence — the core thesis>",
  "supporting_points": ["<point 1>", "<point 2>", "<point 3 if present>"],
  "evidence": ["<evidence item 1>", "<evidence item 2>"],
  "conclusion": "<one sentence — what the student concludes>"
}

Rules:
- Do NOT evaluate or correct the essay
- Preserve the student's exact claim, even if weak or wrong
- Keep concise — this output is for AI agents, not humans"""

SUMMARIZER_PROMPT = _SUMMARIZER_BASE  # no skill needed for summarizer


async def run_summarizer(essay_text: str) -> dict:
    """Summarize essay text. Returns dict with main_claim, supporting_points, evidence, conclusion."""

    def make_agent(model: str) -> LlmAgent:
        return LlmAgent(name="summarizer", model=model, instruction=SUMMARIZER_PROMPT)

    message = Content(
        role="user", parts=[Part(text=f"Summarize this essay:\n\n{essay_text}")]
    )
    text, _ = await run_adk_with_fallback(make_agent, "critiqai", "summarizer", message)

    try:
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean.strip())
    except Exception:
        return {
            "main_claim": text[:200],
            "supporting_points": [],
            "evidence": [],
            "conclusion": "",
        }


# ---------------------------------------------------------------------------
# Persona Selector — injects persona-selector SKILL.md
# ---------------------------------------------------------------------------

_PERSONA_BASE = """You are a debate strategy expert. Given an essay summary JSON, choose EXACTLY 2 debate personas.

Step 1 — score each dimension (0-2) based on the essay summary:
- Skeptic: score 2 if evidence is vague/missing/sparse, 1 if evidence exists but weak, 0 if evidence is strong
- DevilsAdvocate: score 2 if no counterarguments addressed, 1 if partially addressed, 0 if well-handled
- Nitpicker: score 2 if logical leaps or inconsistent terms present, 1 if minor issues, 0 if tight logic
- Expander: score 2 if scope is very narrow or unstated assumptions, 1 if some hedging, 0 if well-scoped

Step 2 — pick the 2 highest-scoring personas. If tied, prefer in this order: Skeptic > DevilsAdvocate > Nitpicker > Expander.

Output ONLY valid JSON, no markdown fences:
{
  "selected_personas": ["PersonaName1", "PersonaName2"],
  "reasoning": "<one sentence explaining the two weaknesses targeted>"
}

Valid names: Skeptic, DevilsAdvocate, Nitpicker, Expander"""

PERSONA_SELECTOR_PROMPT = build_instruction_with_skill(_PERSONA_BASE, "persona-selector")


async def run_persona_selector(essay_summary: dict) -> dict:
    """Select 1-2 debate personas. Returns dict with selected_personas and reasoning."""

    def make_agent(model: str) -> LlmAgent:
        return LlmAgent(
            name="persona_selector",
            model=model,
            instruction=PERSONA_SELECTOR_PROMPT,
        )

    message = Content(
        role="user",
        parts=[
            Part(
                text=f"Select personas for this essay summary:\n\n{json.dumps(essay_summary, ensure_ascii=False)}"
            )
        ],
    )
    text, _ = await run_adk_with_fallback(
        make_agent, "critiqai", "persona_selector", message
    )

    try:
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean.strip())
    except Exception:
        return {
            "selected_personas": ["Skeptic", "DevilsAdvocate"],
            "reasoning": "Default: challenge evidence quality and counterargument handling.",
        }


# ---------------------------------------------------------------------------
# One-shot orchestrator (ADK CLI / demo tab)
# ---------------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are CritiqAI — a Socratic debate coach for students.

When given a student name and essay text, run the following pipeline in sequence:

## Step 1: Summarize the essay
Extract and output:
- main_claim: the core thesis (one sentence)
- supporting_points: list of 2-3 key points
- evidence: specific data or sources cited
- conclusion: what the student concludes

## Step 2: Select 1-2 debate personas based on weaknesses
Decision rules:
- Weak/missing evidence → Skeptic
- Ignores counterarguments → DevilsAdvocate
- Logical leaps or inconsistent terms → Nitpicker
- Too narrow scope or hidden assumptions → Expander

## Step 3: Run 3 debate rounds
For each round, use the selected persona to challenge the student with ONE pointed question.
- Round 1: open probe
- Round 2: push harder on the same weak point
- Round 3: corner — force precision or admission of limit

PERSONA RULES:
[SKEPTIC] — challenge evidence reliability. Never suggest better evidence.
[DEVILS_ADVOCATE] — present strongest opposing case. Never say "you're wrong."
[NITPICKER] — find logical inconsistencies. Ask about specific terms and leaps.
[EXPANDER] — expose hidden assumptions and narrow scope.

UNIVERSAL: NEVER give the correct answer. NEVER confirm the student is right.
One question per round. Max 4 sentences per challenge.

## Step 4: Score the essay
Score each dimension 0-5 using ONLY these rules (no LLM judgment):

logical_coherence: count "therefore/because/thus/hence/since/so" = connectives,
  count "obviously/clearly it is/everyone knows" = non_sequiturs.
  ≥3 connectives & 0 non_sequiturs=5, ≥2 connectives=4, 1 connective=3, 0 connectives=2, 0 conn & ≥1 non_seq=1

evidence_quality: count specific sources/data ("according to/percent/reported/study by/published/found that") = concrete,
  count vague markers ("everyone knows/studies show/it's clear") = vague.
  ≥3 concrete=5, 2 concrete=4, 1 concrete & 0 vague=3, 1 concrete & ≥1 vague=2, ≥2 vague=1, nothing=0

counterargument_handling: count "while/although/however/critics argue/admittedly/despite/on the other hand" = ack.
  ≥3 ack=5, 2 ack=4, 1 ack & engaged=3, 1 ack & dismissed=2, 0 ack=1

scope_awareness: count "may/might/in some cases/assuming/limited to/this does not apply/one limitation" = hedges,
  count "always/never/everyone/all people/universally" = overgen.
  ≥3 hedges & 0 overgen=5, ≥2 hedges=4, 1 hedge=3, 0 hedges & ≥2 overgen=1, else=2

## Step 5: Output final report
Format your final response exactly like this:

=== CRITIQAI SESSION REPORT ===
Student: [first name]

ESSAY SUMMARY:
Main claim: [main_claim]
Evidence cited: [evidence]

PERSONAS ACTIVATED: [list]
REASON: [one sentence]

DEBATE CHALLENGES:
Round 1 [PERSONA]: [challenge question]
Round 2 [PERSONA]: [follow-up challenge]
Round 3 [PERSONA]: [final corner question]

SCORES:
- Logical Coherence: [0-5]/5
- Evidence Quality: [0-5]/5
- Counterargument Handling: [0-5]/5
- Scope Awareness: [0-5]/5
- TOTAL: [sum]/20 ([percent]%)

KEY STRENGTHS: [dimensions scoring 4-5]
AREAS TO IMPROVE: [dimensions scoring 0-2]
NEXT SESSION FOCUS: [one actionable suggestion]
================================"""


def create_orchestrator() -> LlmAgent:
    return LlmAgent(
        name="critiqai_orchestrator",
        model=get_primary_model(),
        instruction=ORCHESTRATOR_PROMPT,
    )


async def run_session(
    student_name: str, essay_url: str = "", essay_text: str = ""
) -> dict:
    """One-shot demo session (legacy). Used by /api/run endpoint and ADK CLI."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    first_name = student_name.split()[0]
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="critiqai", user_id=first_name.lower()
    )
    runner = Runner(
        agent=create_orchestrator(),
        app_name="critiqai",
        session_service=session_service,
    )

    if essay_text:
        prompt = f"Student: {first_name}\n\nEssay:\n{essay_text}"
    else:
        prompt = (
            f"Student: {first_name}\nEssay URL: {essay_url}\n"
            "(Read the essay from the URL, then run the full pipeline.)"
        )

    message = Content(role="user", parts=[Part(text=prompt)])
    final_response = None
    async for event in runner.run_async(
        user_id=first_name.lower(), session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text

    return {"response": final_response, "student": first_name}


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) < 3:
        print("Usage: python orchestrator.py <student_name> <essay_url_or_text>")
        sys.exit(1)

    arg = sys.argv[2]
    if arg.startswith("http"):
        result = asyncio.run(run_session(sys.argv[1], essay_url=arg))
    else:
        result = asyncio.run(run_session(sys.argv[1], essay_text=arg))
    print(result.get("response", "No response"))
