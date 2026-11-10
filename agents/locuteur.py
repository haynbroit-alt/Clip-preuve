"""Locuteur actif : la bouche qui bouge pendant la parole, avec hystérésis.

Fenêtres de 0,4 s. On ne change de visage qu'après 1,5 s du même gagnant.
Si deux visages alternent plus vite que cette tenue, le plan passe en écran partagé.
Les points de test sont synthétiques : le maillage MediaPipe n'est appelé que s'il est là.
"""

from __future__ import annotations

import math
from typing import Any

FENETRE = 0.4
TENUE = 1.5
# Face Mesh : lèvre supérieure interne 13, lèvre inférieure interne 14.
LEVRE_HAUT = 13
LEVRE_BAS = 14


def ecart_levres(haut: tuple[float, float], bas: tuple[float, float]) -> float:
    return math.hypot(bas[0] - haut[0], bas[1] - haut[1])


def ouverture_landmarks(points: list[tuple[float, float]]) -> float:
    return ecart_levres(points[LEVRE_HAUT], points[LEVRE_BAS])


def _parle(t0: float, t1: float, parole: list[tuple[float, float]]) -> bool:
    for a, b in parole:
        if min(t1, b) - max(t0, a) > 0:
            return True
    return False


def fenetres_activite(
    pistes: list[dict[str, Any]],
    parole: list[tuple[float, float]],
    fenetre: float = FENETRE,
) -> list[tuple[float, dict[str, float]]]:
    """Mouvement des lèvres par visage, annulé hors des plages de parole."""
    if fenetre <= 0 or not pistes:
        return []
    groupes: dict[int, dict[str, list[float]]] = {}
    for echantillon in pistes:
        t = float(echantillon["t"])
        indice = int(t // fenetre)
        visage = str(echantillon["face"])
        groupes.setdefault(indice, {}).setdefault(visage, []).append(float(echantillon["ouverture"]))
    resultat: list[tuple[float, dict[str, float]]] = []
    for indice in sorted(groupes):
        t0 = indice * fenetre
        scores: dict[str, float] = {}
        if _parle(t0, t0 + fenetre, parole):
            for visage, valeurs in groupes[indice].items():
                scores[visage] = sum(abs(valeurs[k + 1] - valeurs[k]) for k in range(len(valeurs) - 1))
        else:
            scores = {visage: 0.0 for visage in groupes[indice]}
        resultat.append((t0, scores))
    return resultat


def _gagnant(scores: dict[str, float]) -> str | None:
    if not scores or max(scores.values()) <= 0:
        return None
    return max(scores, key=lambda nom: (scores[nom], nom))


def decider(
    fenetres: list[tuple[float, dict[str, float]]],
    tenue: float = TENUE,
) -> list[dict[str, Any]]:
    """Une décision par fenêtre : single (un visage) ou split (deux visages)."""
    if not fenetres:
        return []
    bruts: list[str | None] = [_gagnant(scores) for _, scores in fenetres]
    actuel: str | None = next((g for g in bruts if g), None)
    en_attente: str | None = None
    depuis = fenetres[0][0]
    plans: list[dict[str, Any]] = []
    for (t, _scores), gagnant in zip(fenetres, bruts, strict=True):
        if gagnant is None:
            pass
        elif gagnant == actuel:
            en_attente = None
        elif en_attente != gagnant:
            en_attente = gagnant
            depuis = t
        elif t - depuis >= tenue:
            actuel = gagnant
            en_attente = None
        plans.append({"t": t, "mode": "single", "faces": [actuel] if actuel else []})
    return _ecran_partage(plans, bruts, tenue)


def _ecran_partage(
    plans: list[dict[str, Any]],
    bruts: list[str | None],
    tenue: float,
) -> list[dict[str, Any]]:
    """Deux visages qui s'échangent avant la tenue passent en split sur cette plage."""
    for i, brut in enumerate(bruts):
        if brut is None:
            continue
        autres = {bruts[j] for j in range(len(bruts)) if abs(plans[j]["t"] - plans[i]["t"]) <= tenue}
        autres.discard(None)
        if len(autres) >= 2:
            faces = sorted(str(v) for v in autres)
            # L'alternance rapide : au moins trois changements de gagnant dans la fenêtre.
            suite = [bruts[j] for j in range(len(bruts)) if abs(plans[j]["t"] - plans[i]["t"]) <= tenue]
            changements = sum(a != b for a, b in zip(suite, suite[1:], strict=False) if a and b)
            if changements >= 2:
                plans[i] = {"t": plans[i]["t"], "mode": "split", "faces": faces}
    return plans


def integrer(
    crop: dict[str, Any],
    pistes: list[dict[str, Any]],
    parole: list[tuple[float, float]],
) -> dict[str, Any]:
    """Ajoute le plan locuteur au recadrage. Sans pistes, le cadrage existant reste."""
    resume = decrire(decider(fenetres_activite(pistes, parole)))
    if resume["plans"]:
        crop["methode"] = resume["methode"]
        crop["plans_locuteur"] = resume["plans"]
        if resume.get("visage"):
            crop["locuteur_actif"] = resume["visage"]
    return crop


def decrire(plans: list[dict[str, Any]]) -> dict[str, Any]:
    """Résumé consommable par le monteur, sans appeler ffmpeg."""
    if not plans:
        return {"methode": "inchange", "plans": []}
    if any(p["mode"] == "split" for p in plans):
        return {"methode": "split-screen locuteurs actifs", "plans": plans}
    visage = plans[-1]["faces"][-1] if plans[-1]["faces"] else None
    return {"methode": "locuteur actif", "visage": visage, "plans": plans}
