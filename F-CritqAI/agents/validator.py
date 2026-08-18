"""
Challenge Validator Agent — quality gate between Debate Agent and student.

Role in multi-agent pipeline:
  Debate Agent  →  [Challenge Validator]  →  Student

The Validator uses purely deterministic checks — zero LLM calls, zero API quota.
Applies identically in both production and test mode.

Checks:
  1. No answer leakage (keyword patterns — Pillar 7 Behavioral Monitoring)
  2. Single-question rule (count '?' — hard fail if > 2)
  3. Length sanity (warn if > 150 words)

Why no LLM validator: an LLM judging another LLM's output is unreliable,
slow (1-3 extra API calls per round), and prone to false positives — the
DevilsAdvocate persona was repeatedly flagged for "answer leakage" simply
because it correctly presented specific opposing examples, which is its
entire purpose.
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Answer-leakage pattern detection (Pillar 7 — behavioral monitoring)
# ---------------------------------------------------------------------------

_ANSWER_LEAK_PATTERNS: list[str] = [
    "you should say",
    "you should argue",
    "you should cite",
    "the correct answer",
    "the right answer",
    "a better argument would be",
    "here is a better",
    "the answer is",
    "you need to say",
    "try using",
    "a good source would be",
    "you should mention",
    "the right conclusion",
    "here is why your argument is wrong",
    "your argument is wrong because",
    "what you should do is",
    "let me tell you the answer",
    "the model argument",
]


def fast_check_answer_leak(challenge: str) -> tuple[bool, str]:
    """
    Deterministic check for answer-leakage patterns.
    Returns (is_clean, matched_pattern_or_empty).
    """
    lowered = challenge.lower()
    for pattern in _ANSWER_LEAK_PATTERNS:
        if pattern in lowered:
            return False, pattern
    return True, ""


def _check_single_question(challenge: str) -> tuple[bool, str]:
    """
    Count '?' in challenge. More than 2 almost certainly means multiple questions.
    We allow up to 2: one main question + one short rhetorical follow-up.
    Returns (passes, issue_message).
    """
    count = challenge.count("?")
    if count > 2:
        return False, f"Multiple questions detected ({count} '?' found) — must be a single challenge"
    return True, ""


def _check_length(challenge: str) -> tuple[bool, str]:
    """Warn if challenge exceeds 150 words."""
    words = len(challenge.split())
    if words > 150:
        return False, f"Challenge is long ({words} words) — aim for ≤ 120 words"
    return True, ""


# ---------------------------------------------------------------------------
# Main validation entry point (deterministic only — no LLM calls)
# ---------------------------------------------------------------------------

async def validate_challenge(
    challenge: str,
    persona: str,
    round_number: int,
    essay_language: str = "English",
) -> dict:
    """
    Validate a debate challenge using deterministic checks only (zero API calls).
    Works identically in production and test mode.

    Design note: skills/answer-leak-patterns/SKILL.md describes an optional
    step-2 LLM "semantic leak" check. It is deliberately NOT implemented here —
    each call would add one Gemini request per round (3/session), eroding the
    free-tier budget. The 18 deterministic regex patterns cover the leak surface
    at zero token cost. `async` is kept so the interface stays uniform with the
    awaitable agents and a future semantic layer could slot in without churn.

    Returns:
        {
          "valid": bool,
          "issues": list[str],
          "severity": "pass" | "warn" | "fail",
          "reasoning": str,
          "fast_check_passed": bool,
        }
    """
    issues: list[str] = []
    severity = "pass"

    # 1. Answer-leak pattern check (hard fail)
    is_clean, leaked_pattern = fast_check_answer_leak(challenge)
    if not is_clean:
        logger.warning(
            "[SECURITY] Answer-leak pattern in debate output (round=%d, persona=%s): '%s'",
            round_number, persona, leaked_pattern,
        )
        return {
            "valid": False,
            "issues": [f"Answer leakage: contains pattern '{leaked_pattern}'"],
            "severity": "fail",
            "reasoning": "Deterministic answer-leak check failed.",
            "fast_check_passed": False,
        }

    # 2. Single-question rule (hard fail)
    ok, msg = _check_single_question(challenge)
    if not ok:
        issues.append(msg)
        severity = "fail"

    # 3. Length check (warn only — challenge still usable)
    ok, msg = _check_length(challenge)
    if not ok:
        issues.append(msg)
        if severity == "pass":
            severity = "warn"

    if severity == "fail":
        logger.warning(
            "[VALIDATOR] Challenge failed deterministic check (round=%d, persona=%s): %s",
            round_number, persona, "; ".join(issues),
        )
    elif severity == "warn":
        logger.info(
            "[VALIDATOR] Challenge passed with warning (round=%d, persona=%s): %s",
            round_number, persona, "; ".join(issues),
        )

    return {
        "valid": severity != "fail",
        "issues": issues,
        "severity": severity,
        "reasoning": "; ".join(issues) if issues else "All deterministic checks passed.",
        "fast_check_passed": True,
    }


async def validate_and_maybe_retry(
    generate_fn,
    persona: str,
    round_number: int,
    essay_language: str = "English",
    max_retries: int = 1,
) -> tuple[str, dict]:
    """
    Generate a challenge via generate_fn(), validate it, retry up to max_retries
    times if severity == 'fail'.

    Args:
        generate_fn: async callable () -> str — calls the Debate Agent
        persona, round_number, essay_language: passed to validator
        max_retries: max regeneration attempts on hard failure

    Returns:
        (challenge_text, final_validation_result)
    """
    for attempt in range(max_retries + 1):
        challenge = await generate_fn()
        result = await validate_challenge(challenge, persona, round_number, essay_language)

        if result.get("severity") != "fail":
            if attempt > 0:
                logger.info(
                    "[VALIDATOR] Challenge accepted after %d regeneration(s).", attempt
                )
            return challenge, result

        if attempt < max_retries:
            logger.warning(
                "[VALIDATOR] Regenerating challenge (attempt %d/%d). Issues: %s",
                attempt + 1, max_retries, result.get("issues"),
            )

    # All retries exhausted — return last challenge anyway (don't block the debate)
    logger.error(
        "[VALIDATOR] All %d regeneration attempt(s) failed deterministic check. "
        "Returning last challenge. Issues: %s",
        max_retries, result.get("issues"),
    )
    return challenge, result
