"""
Summarizer Agent 窶・compresses full essay to ~200 tokens preserving key claims.
Reduces token cost for all downstream agents by ~75%.
"""

from google.adk.agents import LlmAgent

from .model_config import get_primary_model

SUMMARIZER_PROMPT = """You are an academic essay summarizer. Your only job is to compress a student essay into a structured summary of ~200 tokens.

Output JSON with exactly these fields:
{
  "main_claim": "<one sentence - the core thesis>",
  "supporting_points": ["<point 1>", "<point 2>", "<point 3 if present>"],
  "evidence": ["<evidence item 1>", "<evidence item 2>"],
  "conclusion": "<one sentence - what the student concludes>"
}

Rules:
- Do NOT evaluate, critique, or correct the essay
- Do NOT add information not in the original
- Preserve the student's exact claim, even if it is weak or wrong
- Keep each field concise - this output is for AI agents, not humans"""


def create_summarizer() -> LlmAgent:
    return LlmAgent(
        name="summarizer",
        model=get_primary_model(),
        instruction=SUMMARIZER_PROMPT,
        output_key="essay_summary",
    )
