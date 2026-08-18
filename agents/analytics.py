"""
Analytics — pure Python, no LLM.
format_analytics() converts argument-scorer MCP output into a structured report dict.
create_analytics_agent() kept for backwards compat with agents.json.
"""

from google.adk.agents import LlmAgent

from .model_config import get_primary_model

DIMENSION_LABELS = {
    "logical_coherence": "Logical Coherence",
    "evidence_quality": "Evidence Quality",
    "counterargument_handling": "Counterargument Handling",
    "scope_awareness": "Scope Awareness",
}

IMPROVEMENT_TIPS = {
    "logical_coherence": "Use connective words (therefore, because, thus) to show how your evidence leads to your conclusion.",
    "evidence_quality": "Cite specific sources, studies, or data points with author, year, or publication.",
    "counterargument_handling": "Acknowledge the strongest objection to your argument and explain why your position still holds.",
    "scope_awareness": "Add hedging language (may, in some cases, this applies to...) to show you understand the limits of your argument.",
}


def format_analytics(scores: dict, student_name: str = "") -> dict:
    """
    Convert argument-scorer MCP output into structured analytics.
    Input: scores dict with logical_coherence, evidence_quality,
           counterargument_handling, scope_awareness, total, max_possible, percentage
    """
    dim_scores = {
        k: scores.get(k, 0)
        for k in ("logical_coherence", "evidence_quality", "counterargument_handling", "scope_awareness")
    }
    total = scores.get("total", sum(dim_scores.values()))
    max_possible = scores.get("max_possible", 20)
    percentage = scores.get("percentage", round(total / max(max_possible, 1) * 100))

    strengths = [DIMENSION_LABELS[k] for k, v in dim_scores.items() if v >= 4]
    weaknesses = [DIMENSION_LABELS[k] for k, v in dim_scores.items() if v <= 1]
    suggestions = [IMPROVEMENT_TIPS[k] for k, v in dim_scores.items() if v <= 2]

    if not strengths:
        strengths = ["Attempted to construct a structured argument"]
    if not suggestions:
        suggestions = ["Continue developing argumentation skills across all dimensions."]

    return {
        "student_name": student_name,
        "scores": dim_scores,
        "total_score": total,
        "max_possible": max_possible,
        "percentage": percentage,
        "key_strengths": strengths,
        "key_weaknesses": weaknesses,
        "improvement_suggestions": suggestions,
    }


# NOTE: The production analytics path is the deterministic pure-Python function
# above (zero LLM tokens) — it consumes the argument-scorer MCP output directly.
# The LlmAgent below exists only so `agents-cli` / agents.json can introspect a
# 6th agent node; it is not on the token-spending runtime path.
ANALYTICS_PROMPT = """You are a session analytics agent. Call score_argument MCP tool on student responses, then return structured JSON with scores, strengths, weaknesses."""


def create_analytics_agent() -> LlmAgent:
    return LlmAgent(
        name="analytics",
        model=get_primary_model(),
        instruction=ANALYTICS_PROMPT,
        output_key="analytics",
    )
