"""
Paul-Elder critical thinking rubric.

Scoring strategy (token-optimised):
  - English text  → deterministic keyword matching  (0 LLM tokens)
  - Non-English   → 1 compact Gemini call, all 4 dims in one shot (~300 tokens)
  - LLM failure   → keyword fallback (always safe)

Requires only stdlib + fastmcp. LLM path uses urllib so no extra package.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(__file__).parent.parent.parent / "scorer_config.json"

# ── Defaults ────────────────────────────────────────────────────────────────────

_DEFAULT_MODEL = "gemini-2.0-flash-lite"
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

# Score prompt — ultra-compact: ~80 tokens template, ~60 tokens output
_SCORE_PROMPT = (
    "Score this student argument on 4 Paul-Elder dimensions (0-5 each).\n"
    'Return ONLY valid JSON: {{"logical_coherence":N,"evidence_quality":N,'
    '"counterargument_handling":N,"scope_awareness":N}}\n\n'
    "0=absent  3=partial  5=strong:\n"
    "- logical_coherence: premises→conclusions, logical connectives\n"
    "- evidence_quality: concrete cited data vs vague assertions\n"
    "- counterargument_handling: acknowledges & addresses opposing views\n"
    "- scope_awareness: hedges claims, acknowledges limits\n\n"
    "Text:\n{text}"
)

# ── Config helpers ──────────────────────────────────────────────────────────────

def _cfg() -> dict:
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _kw(cfg, dim, field, default):
    return cfg.get(dim, {}).get(field, default)


def _th(cfg, dim, key, default):
    return int(cfg.get(dim, {}).get(key, default))


# ── Language detection (regex, 0 tokens) ───────────────────────────────────────

_RE_JP = re.compile(r"[぀-ゟ゠-ヿ一-龯]")
_RE_VI = re.compile(
    r"[àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắặẳẵẻẽẹếềệểễỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]",
    re.IGNORECASE,
)
_RE_ZH = re.compile(r"[一-鿿㐀-䶿]")


def _detect_lang(text: str) -> str:
    """Detect language via Unicode patterns. Returns 'en', 'vi', 'ja', 'zh', or 'other'."""
    if _RE_JP.search(text):
        return "ja"
    if _RE_VI.search(text):
        return "vi"
    if _RE_ZH.search(text):
        return "zh"
    return "en"


# ── LLM scoring — one call for all 4 dims ──────────────────────────────────────

@lru_cache(maxsize=64)
def _llm_score(text: str) -> dict | None:
    """
    Call Gemini once to score all 4 dimensions.
    - Cached by text (LRU): same response scored only once per process lifetime.
    - Uses stdlib urllib — no extra package installed in the scorer container.
    - Token budget: ~300 tokens total for a typical 150-word student response.
    - Returns None on any failure → caller falls back to keyword scoring.
    """
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return None

    cfg = _cfg()
    if not cfg.get("llm_scoring", True):
        return None

    model = cfg.get("llm_model", _DEFAULT_MODEL)

    # Truncate to cap token usage (~400 words ≈ 500 tokens max input)
    words = text.split()
    input_text = " ".join(words[:400]) if len(words) > 400 else text

    payload = json.dumps({
        "contents": [{"parts": [{"text": _SCORE_PROMPT.format(text=input_text)}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 64,
            "responseMimeType": "application/json",
        },
    }).encode()

    url = _GEMINI_URL.format(model=model, key=api_key)
    try:
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())

        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        scores = json.loads(raw)

        _DIMS = (
            "logical_coherence", "evidence_quality",
            "counterargument_handling", "scope_awareness",
        )
        if not all(k in scores for k in _DIMS):
            logger.warning("LLM response missing dimensions: %s", scores)
            return None

        return {k: max(0, min(5, int(scores[k]))) for k in _DIMS}

    except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as exc:
        logger.warning("LLM scorer failed (%s) — falling back to keyword scoring", type(exc).__name__)
        return None


# ── Keyword scoring (English, deterministic) ────────────────────────────────────

def score_logical_coherence(text: str) -> int:
    """Claims follow from premises; presence of logical connectives."""
    cfg = _cfg()
    connectives = _kw(cfg, "logical_coherence", "positive_keywords",
        ["therefore", "because", "thus", "hence", "consequently", "it follows", "since", "so"])
    non_sequitur = _kw(cfg, "logical_coherence", "negative_keywords",
        ["obviously", "clearly it is", "everyone agrees", "needless to say", "it goes without saying"])
    t5p = _th(cfg, "logical_coherence", "thresh_5_min_pos", 3)
    t5n = _th(cfg, "logical_coherence", "thresh_5_max_neg", 0)
    t4p = _th(cfg, "logical_coherence", "thresh_4_min_pos", 2)
    t4n = _th(cfg, "logical_coherence", "thresh_4_max_neg", 1)
    t3p = _th(cfg, "logical_coherence", "thresh_3_min_pos", 1)

    text_lower = text.lower()
    conn_count = sum(1 for c in connectives if c in text_lower)
    ns_count = sum(1 for n in non_sequitur if n in text_lower)

    if conn_count >= t5p and ns_count <= t5n:
        return 5
    if conn_count >= t4p and ns_count <= t4n:
        return 4
    # Check fallacy-dominant cases BEFORE awarding the baseline 3 — otherwise
    # any single connective short-circuits to 3 and the lower bands are dead code.
    if conn_count == 0 and ns_count >= 1:
        return 1
    if ns_count >= 2:
        return 2
    if conn_count >= t3p:
        return 3
    return 2


def score_evidence_quality(text: str) -> int:
    """Concreteness and relevance of evidence cited."""
    cfg = _cfg()
    vague_markers = _kw(cfg, "evidence_quality", "negative_keywords",
        ["everyone knows", "it's clear that", "studies show", "obviously", "it is well known", "people say"])
    concrete_markers = _kw(cfg, "evidence_quality", "positive_keywords",
        ["according to", "percent", "reported", "published", "in 20", "in 19",
         "study by", "research by", "data from", "survey", "cited", "found that",
         "demonstrated", "showed that", "statistics"])
    t5p = _th(cfg, "evidence_quality", "thresh_5_min_pos", 3)
    t4p = _th(cfg, "evidence_quality", "thresh_4_min_pos", 2)
    t3p = _th(cfg, "evidence_quality", "thresh_3_min_pos", 1)

    text_lower = text.lower()
    vague_count = sum(text_lower.count(m) for m in vague_markers)
    concrete_count = sum(text_lower.count(m) for m in concrete_markers)

    if concrete_count >= t5p:
        return 5
    if concrete_count >= t4p:
        return 4
    if concrete_count >= t3p and vague_count == 0:
        return 3
    if concrete_count >= t3p and vague_count >= 1:
        return 2
    if vague_count >= 2:
        return 1
    return 0


def score_counterargument_handling(text: str) -> int:
    """Acknowledges and engages with opposing views."""
    cfg = _cfg()
    acknowledgment_phrases = _kw(cfg, "counterargument_handling", "positive_keywords",
        ["while", "although", "however", "on the other hand", "critics argue", "one might argue",
         "opponents claim", "this doesn't mean", "despite", "even though", "admittedly",
         "some may argue", "it could be argued", "a counterpoint"])
    # Multi-word phrases only — bare "wrong"/"false" fire on legitimate prose
    # ("a false dichotomy", "it would be wrong to ignore") and mis-penalize.
    dismissal_phrases = _kw(cfg, "counterargument_handling", "negative_keywords",
        ["simply wrong", "clearly wrong", "that is wrong", "completely false",
         "that is false", "obviously false", "no one believes"])
    t5p = _th(cfg, "counterargument_handling", "thresh_5_min_pos", 3)
    t5n = _th(cfg, "counterargument_handling", "thresh_5_max_neg", 0)
    t4p = _th(cfg, "counterargument_handling", "thresh_4_min_pos", 2)
    t3p = _th(cfg, "counterargument_handling", "thresh_3_min_pos", 1)

    text_lower = text.lower()
    ack_count = sum(1 for p in acknowledgment_phrases if p in text_lower)
    dism_count = sum(1 for p in dismissal_phrases if p in text_lower)

    if ack_count >= t5p and dism_count <= t5n:
        return 5
    if ack_count >= t4p:
        return 4
    if ack_count >= t3p and dism_count == 0:
        return 3
    if ack_count >= t3p and dism_count >= 1:
        return 2
    if ack_count == 0:
        return 1
    return 2


def score_scope_awareness(text: str) -> int:
    """Student acknowledges limits, assumptions, and edge cases."""
    cfg = _cfg()
    # Require phrase-level context — bare "may"/"could"/"always" are among the
    # most common English words and fire regardless of argumentative intent.
    hedging = _kw(cfg, "scope_awareness", "positive_keywords",
        ["may not apply", "might not", "could vary", "in some cases", "it depends",
         "under certain", "assuming that", "given that", "limited to",
         "in this context", "this does not apply", "within the scope",
         "one limitation", "applies specifically", "for example"])
    overgeneralization = _kw(cfg, "scope_awareness", "negative_keywords",
        ["always true", "always the case", "never changes", "for everyone",
         "all people", "in all cases", "universally", "without exception",
         "applies to all", "in every case"])
    t5p = _th(cfg, "scope_awareness", "thresh_5_min_pos", 3)
    t5n = _th(cfg, "scope_awareness", "thresh_5_max_neg", 0)
    t4p = _th(cfg, "scope_awareness", "thresh_4_min_pos", 2)
    t4n = _th(cfg, "scope_awareness", "thresh_4_max_neg", 1)
    t3p = _th(cfg, "scope_awareness", "thresh_3_min_pos", 1)

    text_lower = text.lower()
    hedge_count = sum(1 for h in hedging if h in text_lower)
    overgen_count = sum(1 for o in overgeneralization if o in text_lower)

    if hedge_count >= t5p and overgen_count <= t5n:
        return 5
    if hedge_count >= t4p and overgen_count <= t4n:
        return 4
    if hedge_count >= t3p and overgen_count <= t4n:
        return 3
    if hedge_count == 0 and overgen_count >= 2:
        return 1
    if hedge_count == 0:
        return 2
    return 3


# ── Public API ──────────────────────────────────────────────────────────────────

def score_all(text: str) -> dict:
    """
    Score all four Paul-Elder dimensions.

    Routing:
      English  → keyword matching (0 tokens, deterministic)
      Other    → 1 Gemini call for all 4 dims (~300 tokens, cached)
      Fallback → keyword matching if LLM unavailable / fails
    """
    lang = _detect_lang(text)

    if lang != "en":
        llm = _llm_score(text)
        if llm:
            total = sum(llm.values())
            return {
                **llm,
                "total": total,
                "max_possible": 20,
                "percentage": round(total / 20 * 100),
                "language": lang,
                "scoring_method": "llm",
            }
        logger.warning("LLM scoring unavailable for lang=%s — keyword fallback active", lang)

    scores = {
        "logical_coherence": score_logical_coherence(text),
        "evidence_quality": score_evidence_quality(text),
        "counterargument_handling": score_counterargument_handling(text),
        "scope_awareness": score_scope_awareness(text),
    }
    scores["total"] = sum(scores.values())
    scores["max_possible"] = 20
    scores["percentage"] = round(scores["total"] / 20 * 100)
    scores["language"] = lang
    scores["scoring_method"] = "keyword"
    return scores
