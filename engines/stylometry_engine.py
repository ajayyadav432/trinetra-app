"""Pillar 3 — stylometric persona linkage.

Combines two signal families:
  1. our own interpretable feature set (punctuation habits, sentence shape,
     function-word rates, character n-grams)
  2. the StyleAnalyzer from the cloned `stylometry-python` research library
     (function-word vectorisation + cosine distance) when it is importable
"""

import math
import re
import sys
from collections import Counter
from functools import lru_cache

from config import Config

FUNCTION_WORDS = """
the of and to a in that is was he for it with as his on be at by i this had not
are but from or have an they which one you were her all she there would their we him
been has when who will more no if out so said what up its about into than them can
only other new some could time these two may then do first any my now such like our
over man me even most made after also did many before must through back years where
much your way well down should because each just those people mr how too little state
good very make world still own see men work long get here between both life being under
never day same another know while last might us great old year off come since against
go came right used take three
""".split()

PUNCT = [",", ".", "?", "!", ";", ":", "-", "—", "'", '"', "(", ")", "..."]

_LIB_ERR = None


@lru_cache(maxsize=1)
def library():
    """Import StyleAnalyzer from the cloned research repo (best effort)."""
    global _LIB_ERR
    try:
        if Config.STYLOMETRY_LIB and Config.STYLOMETRY_LIB not in sys.path:
            sys.path.insert(0, Config.STYLOMETRY_LIB)
        from stylometry.analyzer import StyleAnalyzer  # type: ignore

        return StyleAnalyzer
    except Exception as exc:  # pragma: no cover
        _LIB_ERR = str(exc)
        return None


def _tokens(text):
    return re.findall(r"[A-Za-z']+", (text or "").lower())


def _sentences(text):
    parts = re.split(r"[.!?]+(?:\s|$)", text or "")
    return [p.strip() for p in parts if len(p.strip()) > 2]


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[k] * b[k] for k in common)
    den = math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))
    return num / den if den else 0.0


def _char_ngrams(text, n=3):
    compact = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return Counter(compact[i:i + n] for i in range(max(0, len(compact) - n + 1)))


def profile(text: str) -> dict:
    toks = _tokens(text)
    sents = _sentences(text)
    words = len(toks)
    length = len(text or "")
    fw = Counter(t for t in toks if t in FUNCTION_WORDS)
    punct = {p: (text or "").count(p) for p in PUNCT}
    per100 = {p: round(1000.0 * c / words, 2) if words else 0.0 for p, c in punct.items()}
    char_counts = Counter(c for c in (text or "") if c.isalpha())
    upper = sum(1 for c in (text or "") if c.isupper())
    digits = sum(1 for c in (text or "") if c.isdigit())
    types = set(toks)
    hapax = sum(1 for t, c in Counter(toks).items() if c == 1)
    return {
        "words": words,
        "characters": length,
        "sentences": len(sents),
        "avg_sentence_len": round(words / len(sents), 2) if sents else 0.0,
        "avg_word_len": round(sum(len(t) for t in toks) / words, 2) if words else 0.0,
        "type_token_ratio": round(len(types) / words, 3) if words else 0.0,
        "hapax_ratio": round(hapax / len(types), 3) if types else 0.0,
        "uppercase_pct": round(100.0 * upper / length, 2) if length else 0.0,
        "digit_pct": round(100.0 * digits / length, 2) if length else 0.0,
        "punct_per_1000w": per100,
        "function_words": {w: round(1000.0 * c / words, 2) if words else 0.0
                           for w, c in fw.most_common(25)},
        "top_char3": dict(_char_ngrams(text).most_common(25)),
    }


def similarity(text_a: str, text_b: str) -> dict:
    """Blended style distance in [0, 1] with component breakdown."""
    fw_a = Counter(_tokens(text_a))
    fw_b = Counter(_tokens(text_b))
    fw_a = Counter({k: v for k, v in fw_a.items() if k in FUNCTION_WORDS})
    fw_b = Counter({k: v for k, v in fw_b.items() if k in FUNCTION_WORDS})

    fw_sim = _cosine(fw_a, fw_b)
    ng_sim = _cosine(_char_ngrams(text_a), _char_ngrams(text_b))

    pa, pb = profile(text_a), profile(text_b)

    def close(x, y, span):
        return 1.0 - min(abs(x - y) / span, 1.0) if span else 0.0

    shape_sim = sum(
        [
            close(pa["avg_sentence_len"], pb["avg_sentence_len"], 25),
            close(pa["avg_word_len"], pb["avg_word_len"], 6),
            close(pa["type_token_ratio"], pb["type_token_ratio"], 0.6),
            close(pa["uppercase_pct"], pb["uppercase_pct"], 40),
        ]
    ) / 4.0

    own = 0.20 * fw_sim + 0.55 * ng_sim + 0.25 * shape_sim

    lib_sim, lib_ok = None, False
    cls = library()
    if cls:
        try:
            analyzer = cls(language="en", min_words=30)
            d = analyzer.cosine_distance(text_a, text_b)
            lib_sim = max(0.0, 1.0 - float(d))
            lib_ok = True
        except Exception:
            lib_ok = False

    final = (0.7 * own + 0.3 * lib_sim) if (lib_ok and lib_sim is not None) else own
    return {
        "score": round(final, 3),
        "components": {
            "function_words": round(fw_sim, 3),
            "char_ngrams": round(ng_sim, 3),
            "statistical_shape": round(shape_sim, 3),
            "research_library": round(lib_sim, 3) if lib_ok else None,
        },
        "label": verdict(final),
    }


def verdict(score: float) -> str:
    if score >= 0.85:
        return "HIGH — same author highly likely"
    if score >= 0.65:
        return "MEDIUM — plausible rebrand/migration"
    if score >= 0.50:
        return "LOW — weak stylistic overlap"
    return "REJECTED — distinct authors"


def _aggregate(texts):
    return "\n\n".join(texts)


def analyse_posts(posts) -> dict:
    """posts: iterable of objects with .handle and .text"""
    by_handle: dict[str, list[str]] = {}
    for p in posts:
        by_handle.setdefault(p.handle, []).append(p.text)
    handles = sorted(by_handle)
    corpora = {h: _aggregate(v) for h, v in by_handle.items()}
    profiles = {h: profile(corpora[h]) for h in handles}

    matrix = []
    pairs = []
    for i, a in enumerate(handles):
        row = []
        for j, b in enumerate(handles):
            if j < i:
                row.append(matrix[j][i])
                continue
            if i == j:
                row.append(1.0)
                continue
            res = similarity(corpora[a], corpora[b])
            row.append(res["score"])
            pairs.append({"a": a, "b": b, **res})
        matrix.append(row)

    pairs.sort(key=lambda x: -x["score"])
    for p in pairs:
        p["recommended"] = p["score"] >= 0.85
    return {
        "handles": handles,
        "matrix": matrix,
        "pairs": pairs,
        "profiles": profiles,
        "post_counts": {h: len(v) for h, v in by_handle.items()},
        "library": "stylometry-python StyleAnalyzer" if library() else "built-in features only",
        "library_error": _LIB_ERR,
    }


def feature_diff(text_a: str, text_b: str) -> list:
    pa, pb = profile(text_a), profile(text_b)
    rows = []
    for key in ("words", "avg_sentence_len", "avg_word_len", "type_token_ratio",
                "hapax_ratio", "uppercase_pct", "digit_pct"):
        rows.append({"metric": key, "a": pa[key], "b": pb[key]})
    allp = sorted(set(pa["punct_per_1000w"]) | set(pb["punct_per_1000w"]))
    for p in allp:
        rows.append({"metric": f"punct '{p}' /1000w",
                     "a": pa["punct_per_1000w"].get(p, 0),
                     "b": pb["punct_per_1000w"].get(p, 0)})
    top_fw = list((Counter(pa["function_words"]) + Counter(pb["function_words"])).most_common(8))
    for w, _ in top_fw:
        rows.append({"metric": f"function word '{w}' /1000w",
                     "a": pa["function_words"].get(w, 0),
                     "b": pb["function_words"].get(w, 0)})
    return rows
