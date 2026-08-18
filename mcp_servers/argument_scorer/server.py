"""
argument-scorer MCP Server
Deterministic, rule-based scoring of student debate responses.
Zero LLM tokens.

Transport modes:
  - stdio (default, local dev): python server.py
  - HTTP/Cloud Run (production): PORT=8080 python server.py
"""

import os

from fastmcp import FastMCP
from rubric import score_all

mcp = FastMCP("argument-scorer")


@mcp.tool()
def score_argument(text: str, rubric: str = "paul_elder") -> dict:
    """
    Score a student's argument text using the Paul-Elder critical thinking framework.
    Returns structured scores 0-5 for each of the four dimensions.

    Args:
        text: The student's argument or debate response to score.
        rubric: Scoring rubric to use. Currently only 'paul_elder' is supported.

    Returns:
        dict with keys: logical_coherence, evidence_quality,
                        counterargument_handling, scope_awareness,
                        total (0-20), max_possible (20), percentage (0-100)
    """
    if rubric != "paul_elder":
        return {"error": f"Unknown rubric '{rubric}'. Supported: 'paul_elder'"}

    if not text or not text.strip():
        return {"error": "text must be a non-empty string"}

    return score_all(text)


@mcp.tool()
def score_dimension(text: str, dimension: str) -> dict:
    """
    Score a single dimension of the Paul-Elder framework.

    Uses score_all internally so the LLM call (for non-English text) is made
    once and shared via LRU cache — calling score_dimension after score_argument
    on the same text costs zero additional tokens.

    Args:
        text: Student argument text.
        dimension: One of 'logical_coherence', 'evidence_quality',
                   'counterargument_handling', 'scope_awareness'

    Returns:
        dict with keys: dimension, score (0-5), max (5)
    """
    _DIMS = {
        "logical_coherence", "evidence_quality",
        "counterargument_handling", "scope_awareness",
    }
    if dimension not in _DIMS:
        return {"error": f"Unknown dimension '{dimension}'. Choose from: {sorted(_DIMS)}"}

    all_scores = score_all(text)
    return {
        "dimension": dimension,
        "score": all_scores[dimension],
        "max": 5,
        "language": all_scores.get("language", "en"),
        "scoring_method": all_scores.get("scoring_method", "keyword"),
    }


@mcp.tool()
def get_rubric_info() -> dict:
    """
    Return metadata about the Paul-Elder rubric dimensions and what each measures.
    Useful for Report Agent when generating feedback text.
    """
    return {
        "rubric": "paul_elder",
        "dimensions": {
            "logical_coherence": {
                "description": "Claims follow from premises",
                "signals": "Connectives (therefore, because, thus), absence of non-sequiturs",
            },
            "evidence_quality": {
                "description": "Concreteness and relevance of evidence",
                "signals": "Specific data/examples vs vague assertions (studies show, everyone knows)",
            },
            "counterargument_handling": {
                "description": "Acknowledges and addresses opposing views",
                "signals": "Phrases like 'while X may argue...', 'however', 'admittedly'",
            },
            "scope_awareness": {
                "description": "Student acknowledges limits of their argument",
                "signals": "Hedging language, explicit scope statements, edge case acknowledgment",
            },
        },
        "scale": "0-5 per dimension, 0-20 total",
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "0"))
    if port:
        # Cloud Run / serverless: bind explicitly to 0.0.0.0:PORT
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        # Local dev: run via stdio (ADK subprocess transport)
        mcp.run()
