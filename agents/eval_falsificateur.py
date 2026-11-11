"""Banc du Falsificateur : mesure ce que le code attrape seul, sur des extraits annotés.

Chaque cas décrit le contexte AVANT, le CLIP et le contexte APRÈS (une phrase par entrée), et le verdict
attendu pour les deux critères que le code peut trancher sans le LLM : `contredit_apres` et `coupe_mi_idee`.
Le LLM est remplacé par une réponse fixe. Par défaut, il est « complaisant » : il ne signale rien et
répond PROUVÉ partout, comme un modèle trompé par une injection. Ce qui sort en CONFLIT vient donc du
garde-fou lexical, c'est-à-dire du code.

Mesures par critère :
- faux_conflit : attendu PAS_CONFLIT, sorti CONFLIT (un bon clip rejeté) ;
- conflit_manque : attendu CONFLIT, sorti autre chose (un défaut qui passe, risque de faux PROUVÉ).

Les cas fournis sont synthétiques et annotés par leur auteur. Ils fixent une mesure de départ ; ils ne
remplacent pas des extraits de vraies vidéos annotés à l'aveugle par deux personnes.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from . import falsificateur as F

CRITERES_CODE: tuple[str, ...] = ("contredit_apres", "coupe_mi_idee")
ATTENDUS: frozenset[str] = frozenset({"CONFLIT", "PAS_CONFLIT"})
LLM_COMPLAISANT: dict[str, Any] = {
    "affirmation_du_clip": "",
    "correction_apres": "aucune",
    "suite_necessaire": "aucune",
    "hors_contexte": {"verdict": "PROUVÉ", "preuve": "aucun problème"},
    "info_prealable": {"verdict": "PROUVÉ", "preuve": "aucun problème"},
}
DUREE_CLIP = 7.0
DUREE_AUTRE = 6.0
PAUSE = 0.5
_APPEL = "call_json"  # remplacé le temps d'un cas, puis restauré


def phrases(cas: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    """Construit les phrases datées. Une entrée peut être un texte ou {"text": ..., "pause_avant_s": ...}."""
    sents: list[dict[str, Any]] = []
    t = 0.0

    def ajouter(entree: Any, duree: float) -> None:
        nonlocal t
        if isinstance(entree, dict):
            t += float(entree.get("pause_avant_s", 0.0))
            texte = str(entree["text"])
        else:
            texte = str(entree)
        sents.append({"s": round(t, 3), "e": round(t + duree, 3), "text": texte, "q": texte.endswith("?")})
        t += duree + PAUSE

    for entree in cas.get("avant", []):
        ajouter(entree, DUREE_AUTRE)
    i = len(sents)
    for entree in cas["clip"]:
        ajouter(entree, DUREE_CLIP)
    j = len(sents) - 1
    for entree in cas.get("apres", []):
        ajouter(entree, DUREE_AUTRE)
    return sents, i, j


@contextmanager
def _llm_fixe(reponse: dict[str, Any]) -> Iterator[None]:
    ancien = getattr(F, _APPEL)
    setattr(F, _APPEL, lambda *a, **k: dict(reponse))
    try:
        yield
    finally:
        setattr(F, _APPEL, ancien)


def evaluer_cas(cas: dict[str, Any]) -> dict[str, Any]:
    sents, i, j = phrases(cas)
    with tempfile.TemporaryDirectory() as run, _llm_fixe({**LLM_COMPLAISANT, **cas.get("llm", {})}):
        r = F.falsify(run, sents, i, j, 1)
    sortie = {}
    for critere in CRITERES_CODE:
        attendu = cas["attendu"][critere]
        if attendu not in ATTENDUS:
            raise ValueError(f"{cas['id']} : attendu inconnu {attendu!r} pour {critere}")
        obtenu = r["final"][critere]["verdict"]
        est_conflit = obtenu == "CONFLIT"
        sortie[critere] = {
            "attendu": attendu,
            "obtenu": obtenu,
            "source": r["final"][critere].get("source"),
            "faux_conflit": est_conflit and attendu == "PAS_CONFLIT",
            "conflit_manque": (not est_conflit) and attendu == "CONFLIT",
        }
    return {"id": cas["id"], "categorie": cas["categorie"], "criteres": sortie}


def _compte(resultats: list[dict[str, Any]], critere: str) -> dict[str, Any]:
    lignes = [r["criteres"][critere] for r in resultats]
    pos = [x for x in lignes if x["attendu"] == "CONFLIT"]
    neg = [x for x in lignes if x["attendu"] == "PAS_CONFLIT"]
    fc = sum(x["faux_conflit"] for x in neg)
    cm = sum(x["conflit_manque"] for x in pos)
    return {
        "cas": len(lignes),
        "attendus_conflit": len(pos),
        "attendus_pas_conflit": len(neg),
        "faux_conflit": fc,
        "conflit_manque": cm,
        "pct_faux_conflit": round(100.0 * fc / len(neg), 1) if neg else 0.0,
        "pct_conflit_manque": round(100.0 * cm / len(pos), 1) if pos else 0.0,
    }


def evaluer(cas: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [c["id"] for c in cas]
    if len(ids) != len(set(ids)):
        raise ValueError("identifiants de cas en double")
    resultats = [evaluer_cas(c) for c in cas]
    erreurs = [
        {"id": r["id"], "categorie": r["categorie"], "critere": k, **v}
        for r in resultats
        for k, v in r["criteres"].items()
        if v["faux_conflit"] or v["conflit_manque"]
    ]
    return {
        "cas": len(resultats),
        "llm": "complaisant (ne signale rien) : seul le code décide",
        "par_critere": {k: _compte(resultats, k) for k in CRITERES_CODE},
        "erreurs": erreurs,
        "resultats": resultats,
    }


def charger(chemin: str) -> list[dict[str, Any]]:
    if os.path.isdir(chemin):
        chemin = os.path.join(chemin, "cas.json")
    with open(chemin, encoding="utf-8") as handle:
        donnees = json.load(handle)
    return list(donnees["cas"])
