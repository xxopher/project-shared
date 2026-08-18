"""
Debate Agent — core loop, max 3 rounds.
Personas loaded from personas.json at startup (no restart needed to update personas).
Active persona switched via role tag in user prompt.
Sliding window: only last 2 exchanges kept in context.
Injects critical-thinking-rubric SKILL.md so the agent uses Paul-Elder framework language.
CRITICAL: personas must NEVER reveal correct answers — only probe and challenge.
"""

import json
import re
from pathlib import Path

from google.adk.agents import LlmAgent
from google.genai.types import Content, Part

from .model_config import build_instruction_with_skill, run_adk_with_fallback

# ---------------------------------------------------------------------------
# Persona config loader — reads personas.json, falls back to hardcoded defaults
# ---------------------------------------------------------------------------

_PERSONAS_FILE = Path(__file__).parent.parent / "personas.json"
_personas_cache: dict | None = None


def load_personas() -> dict:
    """
    Load persona definitions from personas.json (cached after first load).
    Falls back to built-in defaults if file is missing or malformed.
    Hot-reload: call load_personas(force=True) to refresh without restart.
    """
    global _personas_cache
    if _personas_cache is not None:
        return _personas_cache
    try:
        data = json.loads(_PERSONAS_FILE.read_text(encoding="utf-8"))
        # Strip meta keys starting with '_'
        _personas_cache = {k: v for k, v in data.items() if not k.startswith("_")}
        return _personas_cache
    except Exception:
        # Fallback: minimal hardcoded definitions
        _personas_cache = {
            "Skeptic": {"tag": "[SKEPTIC]", "focus": "Challenge evidence reliability.", "tone": "calm, methodical", "rules": [], "opening_template": ""},
            "DevilsAdvocate": {"tag": "[DEVILS_ADVOCATE]", "focus": "Present the strongest opposing case.", "tone": "engaged, fair", "rules": [], "opening_template": ""},
            "Nitpicker": {"tag": "[NITPICKER]", "focus": "Target logical consistency.", "tone": "precise, surgical", "rules": [], "opening_template": ""},
            "Expander": {"tag": "[EXPANDER]", "focus": "Expose hidden assumptions and narrow scope.", "tone": "curious, expansive", "rules": [], "opening_template": ""},
        }
        return _personas_cache


def reload_personas() -> dict:
    """Force reload personas.json — useful after editing the file."""
    global _personas_cache
    _personas_cache = None
    return load_personas()


def _build_persona_block(name: str, defn: dict) -> str:
    """Build a persona instruction block from a persona definition dict."""
    tag = defn.get("tag", f"[{name.upper()}]")
    focus = defn.get("focus", "")
    tone = defn.get("tone", "")
    rules = defn.get("rules", [])
    opening = defn.get("opening_template", "")

    lines = [tag, f"Focus: {focus}"]
    if tone:
        lines.append(f"Tone: {tone}")
    for rule in rules:
        lines.append(rule)
    if opening:
        # ADK's inject_session_state matches {+[^{}]*}+ so even {{x}} is treated
        # as a session variable. Replace {} with [] to avoid false substitution.
        escaped = opening.replace("{", "[").replace("}", "]")
        lines.append(f'Example opening: "{escaped}"')
    return "\n".join(lines)


def _build_debate_base() -> str:
    """Build the full debate system prompt from personas.json definitions."""
    personas = load_personas()
    persona_blocks = "\n\n---\n\n".join(
        _build_persona_block(name, defn) for name, defn in personas.items()
    )
    return f"""You are a critical thinking coach running a Socratic debate session with a student.

You have four debate personas available. You will be told which persona to use via a [PERSONA_TAG] at the start of each turn.

---

{persona_blocks}

---

UNIVERSAL RULES (apply regardless of persona):
1. NEVER give the student the correct answer or model argument.
2. NEVER confirm the student's reasoning is correct — even if it is.
3. Ask exactly ONE question or challenge per response. No multi-part questions.
4. Each round escalates pressure: Round 1 = probe, Round 2 = push harder, Round 3 = corner.
5. If the student gives a strong response, acknowledge it briefly then immediately open a new angle.
6. Max response length: 4 sentences."""


def detect_essay_language(text: str) -> str:
    """Detect essay language from character patterns. Returns language name for LLM instruction."""
    sample = text[:500]
    # Japanese: hiragana or katakana
    if re.search(r'[぀-ヿ]', sample):
        return "Japanese"
    # Vietnamese: unique diacritics (ắ ặ ầ ổ ữ ứ ự ọ ộ ờ etc.) or đ/Đ
    if re.search(r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]', sample, re.IGNORECASE):
        return "Vietnamese"
    # Chinese: CJK unified ideographs (no hiragana/katakana already ruled out Japanese above)
    if re.search(r'[一-鿿]', sample):
        return "Chinese"
    return "English"

DEBATE_SYSTEM_PROMPT = build_instruction_with_skill(
    _build_debate_base(), "critical-thinking-rubric"
)


def build_debate_turn(
    persona: str,
    essay_summary: dict,
    exchange_history: list[dict],
    round_number: int,
    essay_language: str = "English",
) -> str:
    """Build the input message for a single debate turn (sliding window: last 2 exchanges)."""
    personas = load_personas()
    persona_tag = personas.get(persona, {}).get("tag", "[SKEPTIC]")

    recent_exchanges = exchange_history[-2:]
    history_text = ""
    for ex in recent_exchanges:
        history_text += f"Persona challenge: {ex.get('challenge', '')}\n"
        history_text += f"Student response: {ex.get('student_response', '')}\n\n"

    return f"""{persona_tag} Round {round_number}/3

LANGUAGE RULE: The student wrote their essay in {essay_language}. You MUST respond entirely in {essay_language}.

Essay summary:
Main claim: {essay_summary.get('main_claim', '')}
Supporting points: {', '.join(essay_summary.get('supporting_points', []))}
Evidence cited: {', '.join(essay_summary.get('evidence', []))}

{f'Recent exchanges:{chr(10)}{history_text}' if history_text else 'This is the opening challenge.'}

Generate your Round {round_number} challenge now."""


async def run_debate_round(
    persona: str,
    essay_summary: dict,
    exchange_history: list[dict],
    round_number: int,
    essay_language: str = "English",
) -> str:
    """
    Run one debate round with model fallback.
    Returns challenge text. History is managed externally by DebateSessionManager.
    """

    def make_agent(model: str) -> LlmAgent:
        return LlmAgent(
            name="debate",
            model=model,
            instruction=DEBATE_SYSTEM_PROMPT,
        )

    prompt = build_debate_turn(persona, essay_summary, exchange_history, round_number, essay_language)
    message = Content(role="user", parts=[Part(text=prompt)])
    text, _ = await run_adk_with_fallback(
        make_agent, "critiqai_debate", "debate_runner", message
    )
    return text.strip()


def create_debate_agent() -> LlmAgent:
    """Kept for ADK CLI / agents.json backwards compat."""
    from .model_config import get_primary_model

    return LlmAgent(
        name="debate",
        model=get_primary_model(),
        instruction=DEBATE_SYSTEM_PROMPT,
        output_key="debate_rounds",
    )
