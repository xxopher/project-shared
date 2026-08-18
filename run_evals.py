"""
CritiqAI Eval Runner — automated evaluation of all evalsets.

Runs:
  1. persona_trigger.evalset.json  — Persona Selector accuracy (20 cases)
  2. debate_quality.evalset.json   — Debate Agent quality, LLM-as-judge (6 cases)

Usage:
  python run_evals.py                      # run all evals, print summary
  python run_evals.py --eval persona       # run only persona_trigger
  python run_evals.py --eval debate        # run only debate_quality
  python run_evals.py --save               # save results to eval_results.json

Results saved to eval_results.json (checked into repo as evidence for judges).
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("eval_runner")

EVALS_DIR = Path(__file__).parent / "evals"
RESULTS_FILE = Path(__file__).parent / "eval_results.json"


# ---------------------------------------------------------------------------
# Eval 1: Persona Trigger (deterministic — no LLM judge needed)
# ---------------------------------------------------------------------------

async def run_persona_trigger_eval(cases: list) -> dict:
    """Test persona selector accuracy against expected personas."""
    from agents.orchestrator import run_persona_selector

    passed = 0
    failed = 0
    results = []

    for case in cases:
        case_id = case["id"]
        essay_summary = case["essay_summary"]
        expected = set(case["expected_personas"])
        weakness = case.get("weakness_pattern", "unknown")

        try:
            result = await run_persona_selector(essay_summary)
            selected = set(result.get("selected_personas", []))
            hit = bool(selected & expected)

            status = "PASS" if hit else "FAIL"
            if hit:
                passed += 1
            else:
                failed += 1

            results.append({
                "id": case_id,
                "status": status,
                "expected": list(expected),
                "got": list(selected),
                "weakness_pattern": weakness,
                "reasoning": result.get("reasoning", ""),
            })
            print(f"  [{status}] {case_id} — expected {expected}, got {selected}")

        except Exception as exc:
            failed += 1
            results.append({
                "id": case_id, "status": "ERROR",
                "expected": list(expected), "got": [],
                "error": str(exc),
            })
            print(f"  [ERROR] {case_id}: {exc}")

    total = passed + failed
    pass_rate = passed / total if total else 0
    threshold = 0.75
    overall = "PASS" if pass_rate >= threshold else "FAIL"

    print(f"\n  Persona Trigger: {passed}/{total} ({pass_rate:.0%}) — {overall} (threshold {threshold:.0%})")
    return {
        "evalset": "persona_trigger",
        "passed": passed,
        "failed": failed,
        "total": total,
        "pass_rate": round(pass_rate, 3),
        "threshold": threshold,
        "overall": overall,
        "cases": results,
    }


# ---------------------------------------------------------------------------
# Eval 2: Debate Quality (LLM-as-judge)
# ---------------------------------------------------------------------------

async def run_debate_quality_eval(cases: list, judge_prompt: str, pass_threshold: dict) -> dict:
    """Run debate agent then score output with LLM-as-judge."""
    from agents.debate import run_debate_round
    from agents.orchestrator import run_summarizer

    passed = 0
    failed = 0
    results = []

    for case in cases:
        case_id = case["id"]
        persona = case["persona"]
        essay_summary = case["essay_summary"]
        round_num = case["round"]
        must_not_contain = case.get("must_not_contain", [])

        try:
            # Generate challenge
            challenge = await run_debate_round(
                persona=persona,
                essay_summary=essay_summary,
                exchange_history=[],
                round_number=round_num,
            )

            # Fast-path: check must_not_contain patterns
            lowered = challenge.lower()
            hard_fail_reason = None
            for forbidden in must_not_contain:
                if forbidden.lower() in lowered:
                    hard_fail_reason = f"Contains forbidden phrase: '{forbidden}'"
                    break

            if hard_fail_reason:
                failed += 1
                results.append({
                    "id": case_id, "status": "FAIL",
                    "persona": persona, "round": round_num,
                    "challenge_preview": challenge[:200],
                    "reason": hard_fail_reason,
                    "scores": {},
                })
                print(f"  [FAIL] {case_id} — {hard_fail_reason}")
                continue

            # LLM-as-judge scoring
            judge_scores = await _llm_judge(challenge, essay_summary, judge_prompt)

            relevance = judge_scores.get("challenge_relevance", 0)
            withholding = judge_scores.get("answer_withholding", 0)
            case_pass = (
                relevance >= pass_threshold.get("challenge_relevance", 3)
                and withholding >= pass_threshold.get("answer_withholding", 4)
            )

            if case_pass:
                passed += 1
            else:
                failed += 1

            status = "PASS" if case_pass else "FAIL"
            results.append({
                "id": case_id, "status": status,
                "persona": persona, "round": round_num,
                "challenge_preview": challenge[:200],
                "scores": judge_scores,
                "reasoning": judge_scores.get("reasoning", ""),
            })
            print(f"  [{status}] {case_id} — relevance={relevance}/5, withholding={withholding}/5")

        except Exception as exc:
            failed += 1
            results.append({"id": case_id, "status": "ERROR", "error": str(exc)})
            print(f"  [ERROR] {case_id}: {exc}")

    total = passed + failed
    pass_rate = passed / total if total else 0
    overall = "PASS" if pass_rate >= 0.8 else "FAIL"

    print(f"\n  Debate Quality: {passed}/{total} ({pass_rate:.0%}) — {overall} (threshold 80%)")
    return {
        "evalset": "debate_quality",
        "passed": passed,
        "failed": failed,
        "total": total,
        "pass_rate": round(pass_rate, 3),
        "threshold": 0.8,
        "overall": overall,
        "cases": results,
    }


async def _llm_judge(challenge: str, essay_summary: dict, judge_prompt: str) -> dict:
    """Score a debate challenge using LLM-as-judge."""
    from google.adk.agents import LlmAgent
    from google.genai.types import Content, Part
    from agents.model_config import run_adk_with_fallback

    def make_agent(model: str) -> LlmAgent:
        return LlmAgent(name="eval_judge", model=model, instruction=judge_prompt)

    prompt = f"""Essay summary:
Main claim: {essay_summary.get('main_claim', '')}
Evidence: {', '.join(essay_summary.get('evidence', []))}

Debate challenge to evaluate:
{challenge}

Return JSON with challenge_relevance (0-5), answer_withholding (0-5), and reasoning."""

    message = Content(role="user", parts=[Part(text=prompt)])
    text, _ = await run_adk_with_fallback(make_agent, "critiqai_eval", "judge", message)

    import re as _re
    clean = text.strip()
    if clean.startswith("```"):
        clean = _re.sub(r"^```[a-z]*\n?", "", clean)
        clean = _re.sub(r"\n?```$", "", clean)
    return json.loads(clean.strip())


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def main(run_persona: bool = True, run_debate: bool = True, save: bool = False):
    results = {
        "timestamp": datetime.now().isoformat(),
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        "evals": {},
    }

    if run_persona:
        print("\n── Eval 1: Persona Trigger ──────────────────────────────")
        data = json.loads((EVALS_DIR / "persona_trigger.evalset.json").read_text())
        results["evals"]["persona_trigger"] = await run_persona_trigger_eval(data["cases"])

    if run_debate:
        print("\n── Eval 2: Debate Quality (LLM-as-judge) ───────────────")
        data = json.loads((EVALS_DIR / "debate_quality.evalset.json").read_text())
        results["evals"]["debate_quality"] = await run_debate_quality_eval(
            data["cases"], data["judge_prompt"], data["pass_threshold"]
        )

    # Summary
    print("\n══ SUMMARY ═══════════════════════════════════════════════")
    all_pass = True
    for name, r in results["evals"].items():
        status = r["overall"]
        if status != "PASS":
            all_pass = False
        print(f"  {name:30s}  {r['passed']}/{r['total']}  {r['pass_rate']:.0%}  {status}")
    print(f"\n  Overall: {'✓ ALL PASS' if all_pass else '✗ SOME FAILED'}")
    print("══════════════════════════════════════════════════════════")

    if save:
        RESULTS_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\n  Results saved to {RESULTS_FILE}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CritiqAI evaluation suite")
    parser.add_argument("--eval", choices=["persona", "debate", "all"], default="all")
    parser.add_argument("--save", action="store_true", help="Save results to eval_results.json")
    args = parser.parse_args()

    exit_code = asyncio.run(main(
        run_persona=args.eval in ("persona", "all"),
        run_debate=args.eval in ("debate", "all"),
        save=args.save,
    ))
    sys.exit(exit_code)
