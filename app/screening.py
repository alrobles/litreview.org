"""LitReview screening — security, soft quality (spam), scientific impact score.

Three modules run on every submission AFTER it lands on disk (async from the
API). Results are written to .submissions/<sid>/screening.json. Nothing here
publishes anything — the human approve remains the only gate.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import nh3
except Exception:  # pragma: no cover
    nh3 = None

# ---------- config ----------
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL_PRIMARY = os.environ.get("LITREVIEW_SCORE_MODEL", "minimax/minimax-m3:free")
MODEL_FALLBACK = "nvidia/nemotron-3.5-lightning:free"

LLM_TIMEOUT = int(os.environ.get("LITREVIEW_LLM_TIMEOUT", "20"))
LLM_MAX_TOKENS = int(os.environ.get("LITREVIEW_LLM_MAX_TOKENS", "700"))
MAX_CONTENT_CHARS = 30_000  # truncate before the LLM call (price/latency)

# LaTeX: patterns that are never acceptable in a submission
LATEX_FORBIDDEN = [
    (r"\\write18", "shell escape (write18)"),
    (r"\\(?:openout|openin|read)\s*[0-9]+\s*=", "file I/O"),
    (r"\\input\s*[{/]?\s*[~/.]", "path traversal in \\input"),
    (r"\\include\s*[{/]?\s*[~/.]", "path traversal in \\include"),
    (r"\\includegraphics\s*\[?[^\]]*\]?\s*\{\s*(?:/|~/|\.\.)", "absolute/relative image path"),
    (r"\\href\s*\{?\s*(?:javascript|file|data):", "dangerous href scheme"),
    (r"\\special", "\\special"),
    (r"\\pdf(?:include|annot)", "pdf primitives"),
    (r"\\usepackage\s*\{[^}]*\}",
     "package use (must be whitelisted)"),  # matched only for whitelist check
]
LATEX_ALLOWED_PACKAGES = {
    "inputenc", "fontenc", "amsmath", "amssymb", "amsthm", "amsfonts",
    "geometry", "graphicx", "hyperref", "cite", "natbib", "setspace",
    "booktabs", "tabularx", "multirow", "array", "xcolor", "color",
    "microtype", "url", "xurl", "bm", "mathtools", "enumitem", "caption",
    "subcaption", "float", "textcomp", "lmodern", "parskip", "titlesec",
}
MARKDOWN_FORBIDDEN = [
    (r"<\s*script", "script tag"),
    (r"<\s*(?:iframe|object|embed|svg|math)\b", "embedded object tag"),
    (r"\bon(?:error|load|click|mouseover|focus|blur)\s*=", "inline event handler"),
    (r"(?:href|src)\s*=\s*[\"']?\s*(?:javascript|data:text/html|vbscript):", "dangerous URL scheme"),
]
SPAM_WORDS = {
    "click here", "free money", "buy now", "limited offer", "act now",
    "guaranteed", "earn money", "crypto", "bitcoin", "viagra", "casino",
    "lottery", "discount", "promotion", "seo", "backlink", "traffic",
    "subscribe", "follow me", "check this out", "amazing offer", "weight loss",
}
SCORE_SYSTEM = (
    "You are the scientific quality assessor for LitReview, an open repository "
    "of literature reviews written by scientists with AI assistance. Score the "
    "submitted review on five rubric dimensions and give an overall impact "
    "index (a 1-10 predictor of the scientific impact / citation potential of "
    "this review, like a journal impact factor but for THIS paper)."
    " Be tough and quantitative: 5-6 is average, 8+ exceptional, 3- weak. "
    "Judge ONLY the text provided; never penalize or praise the author, style "
    "extras, length, or lack of novelty alone. Base every score on textual "
    "evidence. Answer with JSON ONLY, no markdown, no prose: "
    '{"scores":{"originality":int,"methodological_rigor":int,"clarity":int,'
    '"relevance":int,"bibliography":int},"impact_index":{"score":float,'
    '"confidence":float},"red_flags":[string],"one_line":string}'
)


def truncate(text: str, limit: int = MAX_CONTENT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[...truncated by LitReview screening...]"


# ---------- module 1: security ----------
def _check_latex(text: str) -> list[str]:
    flags = []
    for pattern, label in LATEX_FORBIDDEN:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            if label == "package use (must be whitelisted)":
                pkg = m.group(0)
                m2 = re.search(r"\\usepackage(\[[^\]]*\])?\{([^}]+)\}", text, re.IGNORECASE)
                if m2:
                    pkgs = [p.strip() for p in m2.group(2).split(",")]
                    bad = [p for p in pkgs if p not in LATEX_ALLOWED_PACKAGES]
                    if bad:
                        flags.append(f"non-whitelisted package(s): {', '.join(bad)}")
                continue
            flags.append(label)
    return flags


def _check_markdown(text: str) -> list[str]:
    flags = []
    for pattern, label in MARKDOWN_FORBIDDEN:
        if re.search(pattern, text, re.IGNORECASE):
            flags.append(label)
    return flags


def security_check(format_: str, content: str) -> dict[str, Any]:
    """Deterministic local checks. Returns flags + verdict."""
    content = content.lower()
    if format_ == "latex":
        src_flags = _check_latex(content)
        # extra: PDF embed / external file references
        if re.search(r"\\includegraphics.*\.(?:png|jpe?g|pdf)", content):
            src_flags.append("external image file (must be inlined/base64 in a single-file review)")
    else:
        src_flags = _check_markdown(content)
    blocked = bool(src_flags)
    return {
        "verdict": "blocked" if blocked else "ok",
        "flags": src_flags,
        "checks": len(LATEX_FORBIDDEN) + len(MARKDOWN_FORBIDDEN),
        "method": "deterministic-regex",
        "ts": time.time(),
    }


# ---------- module 2: soft quality (spam / random text) ----------
_STOP = frozenset("the a an and or but of to in on for with as by at from it its this that is are was were be been being have has had do does did not no yes so if then than too very also more most such only own same other new now just about into over after before during while through among between under against these those there here where when why how what which who whom whose all any both each few many much some such".split())


def _lexical_diversity(text: str) -> float:
    words = re.findall(r"[a-z]{3,}", text.lower())
    if len(words) < 50:
        return 0.0
    return len(set(words)) / len(words)


def _bigram_rep(text: str) -> float:
    words = re.findall(r"[a-z]{3,}", text.lower())
    if len(words) < 20:
        return 0.0
    grams = zip(words, words[1:])
    counts: dict = {}
    for g in grams:
        counts[g] = counts.get(g, 0) + 1
    top = max(counts.values())
    return top / len(counts)


def _entropy(text: str) -> float:
    import math
    if not text:
        return 0.0
    text = text.lower()
    counts: dict = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(text)
    ent = -sum((c / n) * math.log2(c / n) for c in counts.values())
    return ent


def soft_quality_check(content: str) -> dict[str, Any]:
    """Heuristic spam/random detection (deterministic, no LLM)."""
    flags = []
    text = re.sub(r"\s+", " ", content).strip()
    n_words = len(re.findall(r"[a-z]{3,}", text.lower()))
    if n_words == 0:
        return {"verdict": "blocked", "flags": ["no recognizable words"], "scores": {}}
    div = _lexical_diversity(text)
    rep = _bigram_rep(text)
    ent = _entropy(content)
    lower = content.lower()
    spam_hits = [w for w in SPAM_WORDS if w in lower]
    # thresholds (tuned on the survey corpus baseline; flag not auto-reject)
    if n_words < 120:
        flags.append(f"very short ({n_words} words) — possible stub")
    if div < 0.35:
        flags.append(f"low lexical diversity ({div:.2f}) — possible spam/repetitive")
    if rep > 0.10:
        flags.append(f"high bigram repetition ({rep:.2f}) — possible template text")
    if ent < 3.0:
        flags.append(f"very low character entropy ({ent:.1f}) — possible random/garbled")
    if spam_hits:
        flags.append("spam keywords: " + ", ".join(spam_hits[:4]))
    blocked = len(spam_hits) >= 2 and div < 0.45
    return {
        "verdict": "blocked" if blocked else ("flag" if flags else "ok"),
        "flags": flags,
        "scores": {
            "lexical_diversity": round(div, 3),
            "bigram_repetition": round(rep, 3),
            "char_entropy": round(ent, 2),
            "word_count": n_words,
        },
        "method": "heuristics",
        "ts": time.time(),
    }


# ---------- module 3: scientific impact score (LLM via OpenRouter) ----------
def _strip_markdown_fence(text: str) -> str:
    """Nemotron sometimes wraps JSON in ```json ... ``` — extract the JSON."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return text[first:last + 1]
    return text


def _llm_call(model: str, sysmsg: str, usermsg: str) -> Optional[dict]:
    if not OPENROUTER_KEY:
        return None
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": sysmsg},
                     {"role": "user", "content": usermsg}],
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
        out = json.load(resp)
    if "choices" not in out or not out["choices"]:
        return None
    content = out["choices"][0]["message"]["content"]
    parsed = _parse_json(content)
    return parsed


def _parse_json(content: str) -> Optional[dict]:
    cleaned = _strip_markdown_fence(content)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    # tolerate trailing commas / single-quote JSON-ish
    try:
        import ast
        parsed = ast.literal_eval(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return None


def _normalize_scores(parsed: dict) -> dict[str, Any]:
    scores = parsed.get("scores", {}) if isinstance(parsed.get("scores"), dict) else {}
    ii = parsed.get("impact_index", {}) if isinstance(parsed.get("impact_index"), dict) else {}
    def num(v, lo=1, hi=10, default=5.0):
        try:
            f = float(v)
            return max(lo, min(hi, f))
        except Exception:
            return default
    return {
        "scores": {
            "originality": num(scores.get("originality")),
            "methodological_rigor": num(scores.get("methodological_rigor")),
            "clarity": num(scores.get("clarity")),
            "relevance": num(scores.get("relevance")),
            "bibliography": num(scores.get("bibliography")),
        },
        "impact_index": {
            "score": num(ii.get("score")),
            "confidence": num(ii.get("confidence"), 0, 1, 0.5),
        },
        "red_flags": parsed.get("red_flags", []) if isinstance(parsed.get("red_flags"), list) else [],
        "one_line": str(parsed.get("one_line", ""))[:300],
    }


def scientific_score(title: str, abstract: str, content: str) -> dict[str, Any]:
    """LLM impact-index predictor with model fallback chain."""
    result: dict[str, Any] = {"status": "pending"}
    user = (f"Title: {title}\n\nAbstract:\n{abstract}\n\n"
            f"Full text:\n{truncate(content)}")
    attempts = [("primary", MODEL_PRIMARY), ("fallback", MODEL_FALLBACK)]
    for label, model in attempts:
        t0 = time.time()
        try:
            parsed = _llm_call(model, SCORE_SYSTEM, user)
            if parsed:
                result = _normalize_scores(parsed)
                result["status"] = "done"
                result["model"] = model
                result["latency_s"] = round(time.time() - t0, 1)
                return result
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2)  # backoff for fallback
                continue
            result["last_error"] = f"HTTP {e.code}"
        except Exception as e:
            result["last_error"] = str(e)[:200]
    result["status"] = "degraded"
    result["model"] = "none"
    return result


# ---------- orchestrator + sanitization ----------
def sanitize_html(html: str) -> str:
    """Clean rendered review HTML with nh3 (XSS). Falls back to escaping."""
    if nh3 is None:
        import html as _html
        return _html.escape(html)
    TAGS = {"p", "a", "strong", "em", "li", "ul", "ol", "h1", "h2", "h3", "h4",
            "h5", "h6", "code", "pre", "table", "thead", "tbody", "tr", "th",
            "td", "blockquote", "hr", "br", "img", "sup", "span", "div",
            "math", "mrow", "mi", "mo", "mn", "mtext", "figure", "figcaption"}
    ATTRS = {"a": {"href", "title"}, "img": {"src", "alt"},
             "th": {"align"}, "td": {"align"}, "*": {"class"}}
    return nh3.clean(html, tags=TAGS, attributes=ATTRS,
                     url_schemes={"http", "https", "mailto", "ftp"})


def run_screening(sid: str, root: Path) -> dict[str, Any]:
    """Execute all modules for a submission and persist screening.json."""
    subdir = root / ".submissions" / sid
    payload = json.loads((subdir / "payload.json").read_text())
    fmt = payload.get("format", "markdown")
    fname = "content.tex" if fmt == "latex" else "content.md"
    content = (subdir / fname).read_text()
    result = {
        "sid": sid,
        "ts": time.time(),
        "format": fmt,
        "security": security_check(fmt, content),
        "soft_quality": soft_quality_check(content),
        "score": scientific_score(payload.get("title", ""),
                                  payload.get("abstract", ""),
                                  content),
        "sanitized_html": sanitize_html(payload.get("abstract", "")),
    }
    # overall verdict (advisory; human approve is the gate)
    sec_verdict = result["security"]["verdict"]
    soft_verdict = result["soft_quality"]["verdict"]
    if sec_verdict == "blocked":
        result["overall"] = "reject_blocked_security"
    elif soft_verdict == "blocked":
        result["overall"] = "reject_blocked_spam"
    elif soft_verdict == "flag" or (result["score"].get("status") == "done"
                                    and result["score"]["impact_index"]["score"] < 4):
        result["overall"] = "review"
    else:
        result["overall"] = "ok"
    (subdir / "screening.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result