"""Agent JUGE (scoring LLM, JSON strict) : 5 notes 0-10 + raison + phrase clé.

Artefact : scores.json. Score final = moyenne pondérée LLM (80 %) + pré-tri normalisé (20 %).
Cas limites : JSON invalide ou note non entière -> candidat ignoré (pas d'ÉCHEC du run) ; tous ignorés -> ÉCHEC.
"""

from __future__ import annotations

import os
from typing import Any

from .common import jload, jsave, progress, skill
from .contracts import notes_juge
from .llm import call_json

KEYS = ["accroche_3s", "autonomie", "payoff", "densite", "citabilite"]
W = {"accroche_3s": 1.3, "autonomie": 1.3, "payoff": 1.2, "densite": 0.8, "citabilite": 1.0}
SCHEMA = {
    "type": "object",
    "properties": {
        **{k: {"type": "integer", "minimum": 0, "maximum": 10} for k in KEYS},
        "raison": {"type": "string", "maxLength": 300},
        "phrase_cle": {"type": "string", "maxLength": 220},
    },
    "required": KEYS + ["raison", "phrase_cle"],
}


def first_secs(words: list[dict[str, Any]], s: float, sec: float = 3.0) -> str:
    return " ".join(w["w"] for w in words if s - 0.05 <= w["s"] < s + sec)


def run_agent(run: str, words: list[dict[str, Any]], cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = os.path.join(run, "scores.json")
    cache = jload(path, {})
    sys_p = skill("juge")
    for k, c in enumerate(cands):
        key = f"{c['s']:.2f}-{c['e']:.2f}"
        if key not in cache:
            progress(run, "juge", 55 + int(15 * k / len(cands)), f"candidat {k + 1}/{len(cands)}")
            user = (
                f"3 PREMIÈRES SECONDES : «{first_secs(words, c['s'])}»\n"
                f"DURÉE : {c['e'] - c['s']:.0f} s\nPASSAGE COMPLET :\n«{c['text']}»"
            )
            try:
                r = call_json(run, "juge", sys_p, user, SCHEMA, max_tokens=300)
                notes = notes_juge(r)
                llm = sum(W[x] * max(0, min(10, getattr(notes, x))) for x in KEYS) / sum(W.values())
                cache[key] = {**r, "llm_score": round(llm, 2)}
            except (RuntimeError, ValueError, TypeError) as e:
                # RuntimeError : LLM injoignable ; ValueError/TypeError : note non entière ("8/10", null…)
                cache[key] = {"erreur": f"{type(e).__name__} : {e}"[:300], "llm_score": None}
            jsave(path, cache)
        c["juge"] = cache[key]
    ok = [c for c in cands if c["juge"].get("llm_score") is not None]
    if not ok:
        raise RuntimeError("ÉCHEC : le juge LLM n'a noté aucun candidat")
    pmin = min(c["pre"] for c in ok)
    pmax = max(c["pre"] for c in ok)
    for c in ok:
        c["score"] = round(0.8 * c["juge"]["llm_score"] + 0.2 * (10 * (c["pre"] - pmin) / ((pmax - pmin) or 1)), 2)
    ok.sort(key=lambda c: -c["score"])
    return ok
