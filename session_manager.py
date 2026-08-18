"""
DebateSessionManager — orchestrates the real multi-turn interactive debate.

Flow per session:
  start_session()
    → (Drive MCP) read essay if URL given
    → run_summarizer()                    [Gemini — Summarizer Agent]
    → run_persona_selector()              [Gemini — Persona Selector Agent]
    → validate_and_maybe_retry(           [Gemini — Debate Agent + Validator Agent]
         run_debate_round(1))
    → append_debate_row(round=1, challenge)
    → return {session_id, challenge, round=1, personas}

  submit_response(session_id, student_response)
    → store response
    → append_debate_row(round=N, response)
    → if round < 3:
        validate_and_maybe_retry(         [Gemini — Debate Agent + Validator Agent]
           run_debate_round(N+1))
        append_debate_row(round=N+1, challenge)
        return {session_id, challenge, round=N+1}
    → if round == 3 (all 3 responses received):
        score_argument_via_mcp(combined responses)
        format_analytics(scores)          [Pure Python — Analytics Agent]
        build_report_email()              [Pure Python — Report Agent]
        → create_gmail_draft()
        append_debate_row(round="final", scores)
        return {session_id, complete=True, report, draft_id}

Multi-agent collaboration:
  Debate Agent generates challenges; Validator Agent independently quality-gates
  each challenge before it reaches the student (answer-leak detection + persona
  consistency check). This makes the pipeline genuinely cooperative, not sequential.
"""

import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass, field

from dotenv import load_dotenv
from opentelemetry import trace

from agents.model_config import setup_tracer

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)
_tracer = setup_tracer("critiqai.session")

_MAX_ESSAY_WORDS = 2000


def sanitize_essay(text: str) -> str:
    """Strip control characters and enforce 2000-word limit (Pillar 4 — input validation)."""
    # Remove control characters except standard whitespace
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = text.strip()
    words = text.split()
    if len(words) > _MAX_ESSAY_WORDS:
        text = ' '.join(words[:_MAX_ESSAY_WORDS])
        logger.warning("Essay truncated to %d words (was %d)", _MAX_ESSAY_WORDS, len(words))
    return text


@dataclass
class ExchangeEntry:
    round_num: int
    persona: str
    challenge: str
    student_response: str = ""


@dataclass
class SessionState:
    session_id: str
    student_name: str
    essay_text: str
    essay_summary: dict = field(default_factory=dict)
    personas: list = field(default_factory=list)
    exchanges: list[ExchangeEntry] = field(default_factory=list)
    current_round: int = 0       # 1-indexed; 0 = not started
    complete: bool = False
    essay_language: str = "English"


class DebateSessionManager:
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_session(
        self,
        student_name: str,
        essay_text: str = "",
        essay_url: str = "",
    ) -> dict:
        """
        Initialize a new debate session.
        Returns: {session_id, challenge, round, personas, reasoning}
        """
        from agents.orchestrator import run_summarizer, run_persona_selector
        from agents.debate import run_debate_round
        from agents.validator import validate_and_maybe_retry
        from mcp_client import read_essay_from_drive, append_debate_row

        # 1. Read essay
        drive_error = None
        if essay_url and not essay_text:
            logger.info("[%s] Đọc essay từ Drive URL: %s", student_name, essay_url)
            driven_text = await read_essay_from_drive(essay_url)
            if driven_text:
                essay_text = driven_text
            else:
                drive_error = (
                    "Không đọc được Google Doc từ URL này.\n"
                    "Nguyên nhân có thể:\n"
                    "• Token OAuth chưa có — chạy `python mcp_client.py` để đăng nhập lần đầu\n"
                    "• Google Docs API chưa được Enable trên Cloud Console\n"
                    "• File chưa được share với account đã đăng nhập\n"
                    "→ Thử dán nội dung bài luận trực tiếp vào ô 'Dán text'."
                )
        if not essay_text:
            return {
                "error": drive_error or "Chưa có nội dung bài luận. Vui lòng dán text hoặc nhập Google Doc URL hợp lệ.",
                "session_id": None,
            }

        essay_text = sanitize_essay(essay_text)
        word_count = len(essay_text.split())

        # Detect essay language once, reuse across all rounds
        from agents.debate import detect_essay_language
        essay_language = detect_essay_language(essay_text)
        logger.info("[%s] Detected essay language: %s", student_name, essay_language)

        # 2. Summarize
        logger.info("[%s] Summarizing essay...", student_name)
        with _tracer.start_as_current_span("summarize") as span:
            span.set_attribute("essay.word_count", word_count)
            span.set_attribute("student", student_name)
            essay_summary = await run_summarizer(essay_text)
            span.set_attribute("summary.fields", list(essay_summary.keys()))

        # 3. Select personas
        logger.info("[%s] Selecting personas...", student_name)
        with _tracer.start_as_current_span("select_persona") as span:
            span.set_attribute("student", student_name)
            persona_result = await run_persona_selector(essay_summary)
            personas = persona_result.get("selected_personas", ["Skeptic"])
            reasoning = persona_result.get("reasoning", "")
            span.set_attribute("personas.selected", str(personas))

        # 4. Generate Round 1 challenge — Debate Agent → Validator Agent
        persona = personas[0]
        logger.info("[%s] Generating Round 1 challenge (%s)...", student_name, persona)
        with _tracer.start_as_current_span("debate_round") as span:
            span.set_attribute("round", 1)
            span.set_attribute("persona", persona)
            span.set_attribute("student", student_name)

            async def _gen_round1():
                return await run_debate_round(
                    persona=persona,
                    essay_summary=essay_summary,
                    exchange_history=[],
                    round_number=1,
                    essay_language=essay_language,
                )

            challenge, validation = await validate_and_maybe_retry(
                _gen_round1, persona, 1, essay_language
            )
            span.set_attribute("challenge.length_chars", len(challenge))
            span.set_attribute("validator.severity", validation.get("severity", "pass"))

        # 5. Create session state
        session_id = str(uuid.uuid4())[:8]
        first_name = student_name.split()[0]
        state = SessionState(
            session_id=session_id,
            student_name=first_name,
            essay_text=essay_text,
            essay_summary=essay_summary,
            personas=personas,
            current_round=1,
            essay_language=essay_language,
        )
        entry = ExchangeEntry(round_num=1, persona=persona, challenge=challenge)
        state.exchanges.append(entry)
        self._sessions[session_id] = state

        # 6. Log to Sheets
        await append_debate_row(
            session_id=session_id,
            round_label="1-challenge",
            student_name=first_name,
            persona=persona,
            challenge=challenge,
            student_response="",
        )

        return {
            "session_id": session_id,
            "challenge": challenge,
            "round": 1,
            "personas": personas,
            "reasoning": reasoning,
        }

    async def submit_response(self, session_id: str, student_response: str) -> dict:
        """
        Process a student response. Returns next challenge or final report.
        Returns: {session_id, challenge, round}
              OR {session_id, complete=True, report, draft_id}
        """
        from agents.debate import run_debate_round
        from agents.validator import validate_and_maybe_retry
        from agents.analytics import format_analytics
        from agents.report import build_report_email
        from mcp_client import (
            append_debate_row,
            score_argument_via_mcp,
            create_gmail_draft,
        )

        state = self._sessions.get(session_id)
        if not state:
            raise KeyError(f"Session {session_id} not found.")
        if state.complete:
            raise ValueError(f"Session {session_id} already complete.")

        current_round = state.current_round
        current_entry = state.exchanges[-1]
        current_entry.student_response = student_response

        # Log student response to Sheets
        await append_debate_row(
            session_id=session_id,
            round_label=f"{current_round}-response",
            student_name=state.student_name,
            persona=current_entry.persona,
            challenge=current_entry.challenge,
            student_response=student_response,
        )

        if current_round < 3:
            # Generate next challenge
            next_round = current_round + 1
            persona = state.personas[min(next_round - 1, len(state.personas) - 1)]
            history = [
                {"challenge": e.challenge, "student_response": e.student_response}
                for e in state.exchanges
            ]
            logger.info("[%s] Generating Round %d challenge (%s)...", state.student_name, next_round, persona)
            with _tracer.start_as_current_span("debate_round") as span:
                span.set_attribute("round", next_round)
                span.set_attribute("persona", persona)
                span.set_attribute("student", state.student_name)
                span.set_attribute("response.word_count", len(student_response.split()))

                _history_snapshot = list(history)
                _persona_snap = persona
                _next_snap = next_round
                _lang_snap = state.essay_language
                _summary_snap = state.essay_summary

                async def _gen_next():
                    return await run_debate_round(
                        persona=_persona_snap,
                        essay_summary=_summary_snap,
                        exchange_history=_history_snapshot,
                        round_number=_next_snap,
                        essay_language=_lang_snap,
                    )

                challenge, validation = await validate_and_maybe_retry(
                    _gen_next, persona, next_round, state.essay_language
                )
                span.set_attribute("challenge.length_chars", len(challenge))
                span.set_attribute("validator.severity", validation.get("severity", "pass"))

            entry = ExchangeEntry(round_num=next_round, persona=persona, challenge=challenge)
            state.exchanges.append(entry)
            state.current_round = next_round

            await append_debate_row(
                session_id=session_id,
                round_label=f"{next_round}-challenge",
                student_name=state.student_name,
                persona=persona,
                challenge=challenge,
                student_response="",
            )

            return {
                "session_id": session_id,
                "challenge": challenge,
                "round": next_round,
                "complete": False,
            }

        # Round 3 response received — finalize
        logger.info("[%s] All 3 rounds complete. Scoring...", state.student_name)
        combined_responses = "\n\n".join(
            f"Round {e.round_num}: {e.student_response}"
            for e in state.exchanges
            if e.student_response
        )

        with _tracer.start_as_current_span("score_argument") as span:
            span.set_attribute("student", state.student_name)
            span.set_attribute("combined_words", len(combined_responses.split()))
            scores = await score_argument_via_mcp(combined_responses)
            span.set_attribute("scores.total", scores.get("total", 0))
            span.set_attribute("scores.percentage", scores.get("percentage", 0))

        analytics = format_analytics(scores, student_name=state.student_name)

        with _tracer.start_as_current_span("create_report_draft") as span:
            span.set_attribute("student", state.student_name)
            span.set_attribute("strengths_count", len(analytics.get("key_strengths", [])))
            subject, body = build_report_email(state.student_name, analytics)
            teacher_email = os.getenv("TEACHER_EMAIL", "")
            draft_id = await create_gmail_draft(to=teacher_email, subject=subject, body=body)
            span.set_attribute("draft_created", draft_id is not None)

        # In mock mode (no OAuth), pass email content for frontend preview
        is_mock_mode = not os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        email_preview = None
        if is_mock_mode:
            email_preview = {
                "to": teacher_email or "(teacher email not configured)",
                "subject": subject,
                "body": body,
            }

        await append_debate_row(
            session_id=session_id,
            round_label="final",
            student_name=state.student_name,
            persona="scorer",
            challenge="",
            student_response="",
            scores=scores,
        )

        state.complete = True
        report = {
            **analytics,
            "debate_transcript": [
                {
                    "round": e.round_num,
                    "persona": e.persona,
                    "challenge": e.challenge,
                    "response": e.student_response,
                }
                for e in state.exchanges
            ],
        }

        return {
            "session_id": session_id,
            "complete": True,
            "report": report,
            "draft_id": draft_id,
            "draft_created": draft_id is not None,
            "email_preview": email_preview,
            "mock_mode": is_mock_mode,
        }

    def get_session(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

async def _selftest():
    logging.basicConfig(level=logging.INFO)
    manager = DebateSessionManager()

    sample_essay = """
    Social media is harmful to teenagers. Many studies show that excessive use causes depression.
    Therefore, governments should ban social media for users under 18. Everyone agrees this is
    the right approach. Social media companies are clearly only motivated by profit.
    """

    print("=== Starting session ===")
    result = await manager.start_session("Test Student", essay_text=sample_essay)
    session_id = result["session_id"]
    print(f"Session ID: {session_id}")
    print(f"Personas: {result['personas']}")
    print(f"\nRound 1 Challenge:\n{result['challenge']}\n")

    for round_num in range(1, 4):
        response = input(f"Your response (Round {round_num}): ").strip()
        if not response:
            response = "I think my evidence is sufficient and my argument is sound."
        result = await manager.submit_response(session_id, response)
        if result.get("complete"):
            print("\n=== Session Complete ===")
            report = result["report"]
            print(f"Total Score: {report['total_score']}/{report['max_possible']} ({report['percentage']}%)")
            print(f"Strengths: {report['key_strengths']}")
            print(f"Weaknesses: {report['key_weaknesses']}")
            print(f"Draft ID: {result.get('draft_id')}")
            break
        else:
            print(f"\nRound {result['round']} Challenge:\n{result['challenge']}\n")


if __name__ == "__main__":
    asyncio.run(_selftest())
