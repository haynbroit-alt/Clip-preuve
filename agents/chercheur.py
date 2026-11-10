"""Agent CHERCHEUR DE CANDIDATS : phrases, sujets, fenêtres 20-90 s, pré-tri gratuit.

Artefacts : sentences.json, topics.json, candidates.json (top N, sans chevauchement).
Cas limites : sans ponctuation, phrases coupées sur pauses > 0,7 s ; source < 20 s -> 0 candidat ;
monologue sans silence -> fin de phrase acceptée (end_on_silence=false).
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from collections.abc import Sequence
from typing import Any, cast

from .common import jload, jsave

STOP = set(
    """le la les un une des de du d l et à a au aux en dans que qui quoi ce cet cette ces se sa son ses
il elle ils elles on je j tu nous vous me m te t lui leur leurs y est c ça ca pas ne n plus pour par sur avec
mais ou donc or ni car si bien très tout tous toute toutes être avoir fait faire été suis es sont ai as avons avez ont
était oui non euh ben bah alors voilà quand comme aussi même encore là ici moi toi mon ma mes ton ta tes notre votre
qu s y'a ya cest jai""".split()
)
HOOK = [
    "pourquoi",
    "comment",
    "secret",
    "erreur",
    "personne",
    "jamais",
    "tout le monde",
    "problème",
    "imaginez",
    "la vérité",
    "le pire",
    "le plus",
    "vous savez",
    "voilà ce",
    "la question",
    "on croit",
    "ce que",
]
BAD_START = {
    "et",
    "mais",
    "donc",
    "alors",
    "parce",
    "du",
    "puis",
    "ou",
    "car",
    "enfin",
    "après",
    "bon",
    "euh",
    "il",
    "elle",
    "ils",
    "elles",
    "ça",
    "ca",
    "lui",
    "eux",
    "ce",
    "cela",
    "ceci",
}
BAD_END = {"et", "mais", "donc", "parce", "que", "qui", "de", "le", "la", "les", "un", "une", "des", "à", "pour"}
_AUCUNE_BORNE: tuple[tuple[float, float], ...] = ()


def toks(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", t.lower()) if w not in STOP and len(w) > 2]


def sentences(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i + 1]["s"] - w["e"] if i + 1 < len(words) else 9
        if re.search(r"[.?!…]$", w["w"]) or gap > 0.7 or len(cur) > 60:
            out.append(
                {
                    "s": cur[0]["s"],
                    "e": cur[-1]["e"],
                    "text": " ".join(x["w"] for x in cur),
                    "wi": [i - len(cur) + 1, i],
                    "q": w["w"].endswith("?"),
                }
            )
            cur = []
    return out


def topics(sents: list[dict[str, Any]], block: float = 45.0) -> list[int]:
    blocks: list[list[int]] = []
    cur: list[int] = []
    for k, s in enumerate(sents):
        cur.append(k)
        if s["e"] - sents[cur[0]]["s"] >= block:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    vec = [Counter(t for k in b for t in toks(sents[k]["text"])) for b in blocks]

    def cos(a: Counter[str], b: Counter[str]) -> float:
        n = sum(a[x] * b[x] for x in a)
        d = math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))
        return n / d if d else 0

    sims = [cos(vec[i], vec[i + 1]) for i in range(len(vec) - 1)]
    if not sims:
        return [0] * len(sents)
    mu = sum(sims) / len(sims)
    sd = math.sqrt(sum((x - mu) ** 2 for x in sims) / len(sims))
    cuts = {
        i + 1
        for i, x in enumerate(sims)
        if x < mu - 0.5 * sd and (i == 0 or x <= sims[i - 1]) and (i == len(sims) - 1 or x <= sims[i + 1])
    }
    tid = 0
    lab: list[int] = []
    for bi, b in enumerate(blocks):
        if bi in cuts:
            tid += 1
        lab += [tid] * len(b)
    return lab


def silence_after(t: float, sil: Sequence[Sequence[float]], tol: float = 0.45) -> bool:
    for a, b in sil:
        if a - tol <= t <= b and b - a >= 0.25:
            return True
    return False


def prescore(c: dict[str, Any], sents: list[dict[str, Any]]) -> float:
    txt = cast(str, c["text"]).lower()
    dur = cast(float, c["e"]) - cast(float, c["s"])
    first3 = " ".join(s["text"] for s in sents[c["i"] : c["j"] + 1])[:60].lower()
    sc = 0.0
    accroche = bool(sents[c["i"]]["q"])
    chute = bool(sents[c["j"]]["q"])
    sc += 2.0 * any(h in first3 for h in HOOK) + 1.0 * accroche
    sc += 1.0 * bool(re.search(r"\d", first3))
    fw = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", sents[c["i"]]["text"].lower())[:1]
    sc -= 2.5 * (bool(fw) and fw[0] in BAD_START)
    lw = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", sents[c["j"]]["text"].lower())[-1:]
    sc -= 2.0 * (bool(lw) and lw[0] in BAD_END) + 1.5 * chute
    sc += 1.5 * bool(c["end_on_silence"]) + 0.5 * bool(c["start_after_silence"])
    sc += min(3.0, len(set(toks(txt))) / max(dur, 1) * 2.0)  # densité d'idées
    sc -= abs(dur - 45) / 30.0
    sc -= 2.0 * len(re.findall(r"\b(euh|hum|bah)\b", txt)) / max(1, len(txt.split())) * 20
    return round(sc, 3)


def run_agent(
    run: str,
    words: list[dict[str, Any]],
    sil: Sequence[Sequence[float]],
    top: int = 6,
    exclude: Sequence[Sequence[float]] = _AUCUNE_BORNE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sents = jload(os.path.join(run, "sentences.json")) or sentences(words)
    jsave(os.path.join(run, "sentences.json"), sents)
    lab = topics(sents)
    jsave(os.path.join(run, "topics.json"), lab)
    cands: list[dict[str, Any]] = []
    for i, si in enumerate(sents):
        for j in range(i, len(sents)):
            dur = sents[j]["e"] - si["s"]
            if dur > 90:
                break
            if dur < 20 or lab[j] != lab[i]:
                continue
            c = {
                "i": i,
                "j": j,
                "s": si["s"],
                "e": sents[j]["e"],
                "topic": lab[i],
                "end_on_silence": silence_after(sents[j]["e"], sil),
                "start_after_silence": silence_after(si["s"] - 0.3, sil),
                "text": " ".join(s["text"] for s in sents[i : j + 1]),
            }
            c["pre"] = prescore(c, sents)
            cands.append(c)
    cands.sort(key=lambda c: -c["pre"])
    chosen: list[dict[str, Any]] = []
    for c in cands:
        if any(not (c["e"] <= x[0] or c["s"] >= x[1]) for x in exclude):
            continue
        if all(c["e"] <= d["s"] or c["s"] >= d["e"] for d in chosen):
            chosen.append(c)
        if len(chosen) >= top:
            break
    for k, c in enumerate(chosen):
        c["id"] = f"c{k + 1}"
    jsave(os.path.join(run, "candidates.json"), {"total_windows": len(cands), "top": chosen})
    if not chosen:
        raise RuntimeError("ÉCHEC : aucun passage de 20-90 s exploitable")
    return sents, chosen
