"""
Model selection with automatic fallback chain.

Priority order:
  1. gemini-2.5-flash        — primary (lite models hit free-tier daily quota too fast)
  2. gemini-2.0-flash        — first fallback
  3. gemini-2.5-flash-lite   — second fallback (20/day limit)
  4. gemini-2.0-flash-lite   — last resort

Override primary with GEMINI_MODEL env var.

TEST MODE: If critiqai_mode.json exists at project root, all AI calls are
routed through ai_module (Kaggle / Vertex AI) instead of Google AI API.
To deploy: delete critiqai_mode.json. Search "TEST MODE" to find related code.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Suppress ADK stderr noise
# ADK prints "Node execution failed" / "Root node X failed" + full tracebacks
# directly via print()/traceback.print_exc() to stderr — not via logging —
# so logger.setLevel() has no effect. We wrap sys.stderr to drop those lines.
# ---------------------------------------------------------------------------

_ADK_NOISE_PREFIXES = (
    "Node execution failed",
    "Root node ",
    "Traceback (most recent call last):",
)
# Substrings that indicate we're inside an ADK-internal traceback block.
_ADK_NOISE_PATHS = (
    "google/adk/",
    "google\\adk\\",
    "google/genai/",
    "google\\genai\\",
    "site-packages\\tenacity",
    "site-packages/tenacity",
)


class _AdkStderrFilter:
    """Proxy for sys.stderr that silences ADK internal traceback spam."""

    def __init__(self, real: object) -> None:
        self._real = real
        self._suppressing = False

    def write(self, text: str) -> int:
        if not text or text == "\n":
            if not self._suppressing:
                result = self._real.write(text)
                return result if result is not None else len(text)
            return len(text)

        # Start suppressing when we see an ADK noise header.
        if any(text.startswith(p) for p in _ADK_NOISE_PREFIXES):
            self._suppressing = True

        if self._suppressing:
            # Stop suppressing on a blank line that ends a traceback block,
            # but only after we've passed the exception line itself.
            stripped = text.strip()
            if not stripped and self._suppressing:
                self._suppressing = False
            return len(text)

        # Also swallow lines that are purely ADK/genai/tenacity stack frames.
        if any(p in text for p in _ADK_NOISE_PATHS):
            return len(text)

        result = self._real.write(text)
        return result if result is not None else len(text)

    def flush(self) -> None:
        self._real.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


# Install once — guard against double-wrapping on module reload.
if not isinstance(sys.stderr, _AdkStderrFilter):
    sys.stderr = _AdkStderrFilter(sys.stderr)

# ---------------------------------------------------------------------------
# TEST MODE — load critiqai_mode.json if present
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.parent
_MODE_FILE = _ROOT / "critiqai_mode.json"


def _load_test_mode() -> dict | None:
    """Return test mode config dict, or None if in production mode."""
    if not _MODE_FILE.exists():
        return None
    try:
        return json.loads(_MODE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("critiqai_mode.json unreadable (%s) — falling back to production mode.", exc)
        return None


def _resolve_kaggle_cfg(kaggle_section: dict) -> dict:
    """Load active account from kaggle.json and merge into provider cfg."""
    creds_path = kaggle_section.get("credentials_json", "")
    if not os.path.isabs(creds_path):
        creds_path = str(_ROOT / creds_path)

    model = kaggle_section.get("model", "google/gemini-3.1-flash-lite-preview")

    if not os.path.exists(creds_path):
        logger.warning("Kaggle credentials not found at %s", creds_path)
        return {"model": model}

    try:
        data = json.loads(Path(creds_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Cannot read Kaggle credentials: %s", exc)
        return {"model": model}

    active_id = data.get("active_account_id", "")
    accounts = data.get("accounts", [])

    # Find active account
    account = next((a for a in accounts if a.get("id") == active_id), None)
    if not account and accounts:
        account = accounts[0]

    if not account:
        return {"model": model}

    return {
        "username": account.get("username", ""),
        "api_key": account.get("api_key", ""),
        "model_proxy_url": account.get("model_proxy_url", ""),
        "model_proxy_api_key": account.get("model_proxy_api_key", ""),
        "model": model,
    }


def _extract_prompt_from_message(message: Any) -> str:
    """Extract plain text from a google.genai Content object."""
    if hasattr(message, "parts"):
        parts = []
        for part in message.parts:
            if hasattr(part, "text") and part.text:
                parts.append(part.text)
        return "\n".join(parts)
    if isinstance(message, str):
        return message
    return str(message)


async def _run_via_ai_module(
    agent_factory: Callable,
    message: Any,
    provider: str,
    provider_cfg: dict,
) -> tuple[str, str]:
    """
    TEST MODE path: call ai_module instead of Google ADK.
    Builds full prompt = system_instruction + user_message, then calls AIHub.ask().
    """
    import asyncio
    from ai_module.hub import AIHub  # TEST MODE import

    # Extract system instruction from a dummy agent instance
    try:
        dummy = agent_factory("dummy-model")
        system_prompt = getattr(dummy, "instruction", "") or ""
    except Exception:
        system_prompt = ""

    user_text = _extract_prompt_from_message(message)
    full_prompt = f"{system_prompt}\n\n---\n\n{user_text}" if system_prompt else user_text

    logger.info("[TEST MODE] Routing via ai_module provider=%s model=%s", provider, provider_cfg.get("model", "?"))

    # AIHub.ask() is synchronous — run in thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(
        None,
        lambda: AIHub.ask(provider, full_prompt, provider_cfg),
    )
    return text.strip(), f"test:{provider}:{provider_cfg.get('model', '?')}"

# ---------------------------------------------------------------------------
# Fallback chain — preference order (overridden at runtime by quota state)
# ---------------------------------------------------------------------------

# Preference order for flash-family models. At runtime, models that hit their
# daily quota are skipped automatically; per-minute rate-limited models are
# skipped until their retry window expires.
_PREFERRED_MODELS: list[str] = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
]

# Populated at startup by fetch_available_models(); falls back to _PREFERRED_MODELS.
FALLBACK_MODELS: list[str] = []

# ---------------------------------------------------------------------------
# Per-session quota tracking — avoids re-hitting exhausted models each call
# ---------------------------------------------------------------------------

import re as _re
import time as _time
import datetime as _dt

# ---------------------------------------------------------------------------
# Persistent daily-quota cache — survives process restarts within the same UTC day.
# Stored at <project_root>/.quota_cache.json  {date: "YYYY-MM-DD", exhausted: [...]}
# ---------------------------------------------------------------------------

_QUOTA_CACHE_FILE = _ROOT / ".quota_cache.json"

def _today_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")

def _load_quota_cache() -> set[str]:
    """Load persisted exhausted-model set; discard if it's from a previous UTC day."""
    try:
        data = json.loads(_QUOTA_CACHE_FILE.read_text(encoding="utf-8"))
        if data.get("date") == _today_utc():
            return set(data.get("exhausted", []))
    except Exception:
        pass
    return set()

def _save_quota_cache(exhausted: set[str]) -> None:
    try:
        _QUOTA_CACHE_FILE.write_text(
            json.dumps({"date": _today_utc(), "exhausted": sorted(exhausted)}),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug("quota cache write failed: %s", e)

# Models whose DAILY quota is exhausted — persisted across restarts within the same UTC day.
_daily_exhausted: set[str] = _load_quota_cache()
if _daily_exhausted:
    logger.info("quota cache loaded: skipping %d exhausted model(s) → %s", len(_daily_exhausted), sorted(_daily_exhausted))

# Models rate-limited per minute: model → monotonic timestamp when the window reopens.
_rate_limited: dict[str, float] = {}


def _parse_retry_delay(exc: Exception) -> float:
    """Extract retryDelay seconds from a 429 error message (default 60s)."""
    m = _re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)s", str(exc))
    return float(m.group(1)) if m else 60.0


def _is_daily_quota(exc: Exception) -> bool:
    """True when the 429 is a daily (not per-minute) quota violation."""
    return "perday" in str(exc).lower() or "per_day" in str(exc).lower()


def _mark_quota_state(model: str, exc: Exception) -> None:
    """Record that model hit a quota limit so future calls skip it instantly."""
    if _is_daily_quota(exc):
        _daily_exhausted.add(model)
        _save_quota_cache(_daily_exhausted)
        logger.warning("⛔ %s — daily quota exhausted, skipping for rest of day", model)
    else:
        delay = _parse_retry_delay(exc)
        _rate_limited[model] = _time.monotonic() + delay
        logger.warning("⏳ %s — rate-limited, skipping for %.0fs", model, delay)


def _model_available(model: str) -> bool:
    """Return False if model is known to be quota-exhausted right now."""
    if model in _daily_exhausted:
        return False
    expire = _rate_limited.get(model)
    if expire is not None:
        if _time.monotonic() < expire:
            return False
        del _rate_limited[model]  # window has passed, allow retry
    return True


# ---------------------------------------------------------------------------
# Dynamic model discovery
# ---------------------------------------------------------------------------

def fetch_available_models(api_key: str | None = None) -> list[str]:
    """
    Query the Gemini API for models that support generateContent, then sort
    by our preference order. Falls back to _PREFERRED_MODELS on any error.

    Populates the module-level FALLBACK_MODELS list in-place.
    """
    global FALLBACK_MODELS
    key = api_key or os.getenv("GOOGLE_API_KEY", "")
    if not key:
        logger.warning("fetch_available_models: no API key — using static preference list")
        FALLBACK_MODELS = list(_PREFERRED_MODELS)
        return FALLBACK_MODELS

    # Substrings that identify non-text models to exclude from the fallback chain.
    _EXCLUDE_KEYWORDS = (
        "image", "tts", "audio", "video", "speech", "embed",
        "robotics", "lyria", "gemma", "nano", "banana",
        "deep-research", "antigravity", "computer-use", "clip",
    )

    try:
        from google import genai as _genai  # type: ignore
        client = _genai.Client(api_key=key)
        raw = list(client.models.list())
        # Keep models that support generateContent and look like text-generation flash/pro models
        capable = set()
        for m in raw:
            model_id = getattr(m, "name", "") or ""
            model_id = model_id.removeprefix("models/")
            # Must support generateContent
            methods = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
            if "generateContent" not in methods:
                continue
            # Exclude non-text model families
            lower = model_id.lower()
            if any(kw in lower for kw in _EXCLUDE_KEYWORDS):
                continue
            capable.add(model_id)
        # Drop versioned aliases like -001, -002 — they share quota with their
        # base model (e.g. gemini-2.0-flash-001 burns gemini-2.0-flash quota)
        # so including them just wastes fallback slots.
        import re as _re_alias
        capable = {
            m for m in capable
            if not _re_alias.search(r"-0\d\d$", m)
        }
        # Sort by preference; append any extra capable models not in our list
        ordered = [m for m in _PREFERRED_MODELS if m in capable]
        extras = sorted(capable - set(_PREFERRED_MODELS))
        ordered.extend(extras)
        if not ordered:
            raise ValueError("No generateContent-capable models returned")
        FALLBACK_MODELS = ordered
        logger.info(
            "fetch_available_models: %d models available → %s",
            len(ordered), ordered,
        )
    except Exception as exc:
        logger.warning("fetch_available_models failed (%s) — using static list", exc)
        FALLBACK_MODELS = list(_PREFERRED_MODELS)

    # Honour GEMINI_MODEL env override — put it first if set
    env_model = os.getenv("GEMINI_MODEL", "")
    if env_model and env_model in FALLBACK_MODELS:
        FALLBACK_MODELS.remove(env_model)
        FALLBACK_MODELS.insert(0, env_model)
    elif env_model:
        FALLBACK_MODELS.insert(0, env_model)

    return FALLBACK_MODELS


# Initialise with the static list so callers before startup never see []
FALLBACK_MODELS = list(_PREFERRED_MODELS)


def get_primary_model() -> str:
    available = [m for m in FALLBACK_MODELS if _model_available(m)]
    return available[0] if available else FALLBACK_MODELS[0]


_RETRYABLE: tuple[str, ...] = (
    "quota",
    "rate limit",
    "429",
    "503",
    "resource exhausted",
    "model not found",
    "not found",      # catches 404 NOT_FOUND for unavailable/deprecated models
    "not available",
    "overloaded",
    "deadline exceeded",
)


def _is_retryable(exc: Exception) -> bool:
    return any(s in str(exc).lower() for s in _RETRYABLE)


# ---------------------------------------------------------------------------
# Skill loader
# ---------------------------------------------------------------------------

_SKILLS_ROOT = Path(__file__).parent.parent / "skills"


def load_skill(skill_name: str) -> str:
    """Return SKILL.md content for injection into agent instructions. Empty string if not found."""
    skill_file = _SKILLS_ROOT / skill_name / "SKILL.md"
    if skill_file.exists():
        return skill_file.read_text(encoding="utf-8")
    logger.warning("Skill not found: %s", skill_file)
    return ""


def build_instruction_with_skill(base_prompt: str, skill_name: str) -> str:
    """Append skill content to a base agent instruction."""
    skill = load_skill(skill_name)
    if not skill:
        return base_prompt
    return f"{base_prompt}\n\n---\n## Skill Reference: {skill_name}\n\n{skill}"


# ---------------------------------------------------------------------------
# ADK runner with model fallback
# ---------------------------------------------------------------------------

async def run_adk_with_fallback(
    agent_factory: Callable[[str], Any],
    app_name: str,
    user_id: str,
    message: Any,
) -> tuple[str, str]:
    """
    Run an ADK LlmAgent with automatic model fallback.

    agent_factory(model: str) -> LlmAgent

    Returns (response_text, model_used).
    Tries each model in FALLBACK_MODELS; retries on quota/availability errors.

    TEST MODE: if critiqai_mode.json exists, routes through ai_module instead.
    """
    # ── TEST MODE CHECK ──────────────────────────────────────────────────────
    _mode_cfg = _load_test_mode()
    if _mode_cfg and _mode_cfg.get("mode") == "test":
        provider = _mode_cfg.get("provider", "kaggle")
        if provider == "kaggle":
            provider_cfg = _resolve_kaggle_cfg(_mode_cfg.get("kaggle", {}))
        elif provider == "vertex_ai":
            # Load from ai.config.json
            va_path = _mode_cfg.get("vertex_ai", {}).get("config_json", "ai_module/config/ai.config.json")
            if not os.path.isabs(va_path):
                va_path = str(_ROOT / va_path)
            try:
                full_cfg = json.loads(Path(va_path).read_text(encoding="utf-8"))
                provider_cfg = full_cfg.get("vertex_ai", {})
            except Exception as exc:
                raise RuntimeError(f"Cannot load Vertex AI config: {exc}")
        else:
            raise RuntimeError(f"critiqai_mode.json: unsupported provider '{provider}'")
        return await _run_via_ai_module(agent_factory, message, provider, provider_cfg)
    # ── END TEST MODE ────────────────────────────────────────────────────────

    import time
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    candidates = [m for m in FALLBACK_MODELS if _model_available(m)]
    if not candidates:
        raise RuntimeError("All models are quota-exhausted. Try again later.")

    last_exc: Exception | None = None
    for idx, model in enumerate(candidates):
        t0 = time.monotonic()
        label = f"[{idx+1}/{len(candidates)}]"
        logger.info("→ %s Trying model: %s  (app=%s)", label, model, app_name)
        try:
            session_service = InMemorySessionService()
            session = await session_service.create_session(
                app_name=app_name, user_id=user_id
            )
            agent = agent_factory(model)
            runner = Runner(
                agent=agent, app_name=app_name, session_service=session_service
            )

            text = ""
            async for event in runner.run_async(
                user_id=user_id, session_id=session.id, new_message=message
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    text = event.content.parts[0].text

            elapsed = time.monotonic() - t0
            if idx == 0:
                logger.info("✓ %s Model OK: %s  (%.1fs)", label, model, elapsed)
            else:
                logger.warning("✓ %s Fallback used: %s  (%.1fs)", label, model, elapsed)
            return text, model

        except Exception as exc:
            elapsed = time.monotonic() - t0
            if _is_retryable(exc):
                _mark_quota_state(model, exc)
                logger.warning(
                    "✗ %s Model FAILED: %s  (%.1fs) — %s: %s",
                    label, model, elapsed, type(exc).__name__, str(exc)[:200],
                )
                last_exc = exc
                continue
            logger.error(
                "✗ %s Model NON-RETRYABLE error: %s  (%.1fs) — %s: %s",
                label, model, elapsed, type(exc).__name__, str(exc)[:200],
            )
            raise

    raise RuntimeError(
        f"All models in fallback chain failed. Last error: {last_exc}"
    )


# ---------------------------------------------------------------------------
# OpenTelemetry — readable log-style span exporter
# ---------------------------------------------------------------------------

class _LogSpanExporter(SpanExporter):
    """Exports OTel spans as structured log lines (readable in Kaggle notebook output)."""

    def export(self, spans: Sequence[Any]) -> SpanExportResult:  # type: ignore[override]
        for span in spans:
            duration_ms = (span.end_time - span.start_time) / 1_000_000
            attrs = dict(span.attributes or {})
            attr_str = " | ".join(f"{k}={v}" for k, v in attrs.items())
            status = "OK" if span.status.is_ok else f"ERROR({span.status.description})"
            logger.info(
                "[trace] %-30s  %.0fms  %s  %s",
                span.name,
                duration_ms,
                status,
                attr_str,
            )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def setup_tracer(service_name: str = "critiqai") -> Any:
    """
    Configure and return an OpenTelemetry tracer.
    Call once at app startup (idempotent — safe to call multiple times).
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_LogSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
