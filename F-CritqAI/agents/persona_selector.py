"""
Persona Selector Agent 窶・reads essay summary, picks 1-2 personas to activate.
Decision tree: weakness pattern 竊・persona name.
"""

from google.adk.agents import LlmAgent

PERSONA_SELECTOR_PROMPT = """You are a debate strategy expert. Given a structured essay summary, choose 1-2 debate personas that will most effectively expose the essay's weaknesses.

Persona decision rules (apply in order, pick first match):
1. If evidence is vague, anecdotal, or missing 竊・pick "Skeptic"
2. If the essay ignores or dismisses counterarguments 竊・pick "DevilsAdvocate"
3. If conclusion doesn't follow from premises, or terms are used inconsistently 竊・pick "Nitpicker"
4. If the argument is too narrow, ignores context, or has hidden assumptions 竊・pick "Expander"

You may pick 2 personas if the essay has 2 distinct major weaknesses. Never pick more than 2.

Output JSON:
{
  "selected_personas": ["PersonaName"],
  "reasoning": "<one sentence explaining why these personas fit this essay>"
}

Valid persona names: Skeptic, DevilsAdvocate, Nitpicker, Expander"""


def create_persona_selector() -> LlmAgent:
    return LlmAgent(
        name="persona_selector",
        model="gemini-2.5-flash-lite",
        instruction=PERSONA_SELECTOR_PROMPT,
        output_key="active_personas",
    )
