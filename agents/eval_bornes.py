"""Mesure les clips coupés au milieu d'une idée annotée à la main.

Un clip est « mi-idée » si son début ou sa fin tombe à l'intérieur d'une idée,
à plus de `tolerance_s` de la borne correspondante. L'erreur de borne est la
somme des écarts avec l'idée qui recouvre le mieux le clip.
"""

from __future__ import annotations

import json
import os
from typing import Any


def _recouvrement(clip: dict[str, Any], idee: dict[str, Any]) -> float:
    fin = min(float(clip["fin_s"]), float(idee["fin_s"]))
    debut = max(float(clip["debut_s"]), float(idee["debut_s"]))
    return max(0.0, fin - debut)


def idee_principale(clip: dict[str, Any], idees: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not idees:
        return None

    def cle(idee: dict[str, Any]) -> tuple[float, float]:
        ecart = abs(float(clip["debut_s"]) - float(idee["debut_s"]))
        return (_recouvrement(clip, idee), -ecart)

    return max(idees, key=cle)


def coupe_mi_idee(clip: dict[str, Any], idees: list[dict[str, Any]], tolerance_s: float = 0.4) -> bool:
    for idee in idees:
        debut, fin = float(idee["debut_s"]), float(idee["fin_s"])
        c0, c1 = float(clip["debut_s"]), float(clip["fin_s"])
        if debut + tolerance_s < c0 < fin - tolerance_s:
            return True
        if debut + tolerance_s < c1 < fin - tolerance_s:
            return True
    return False


def erreur_bornes(clip: dict[str, Any], idees: list[dict[str, Any]]) -> float:
    idee = idee_principale(clip, idees)
    if idee is None:
        return 0.0
    return abs(float(clip["debut_s"]) - float(idee["debut_s"])) + abs(float(clip["fin_s"]) - float(idee["fin_s"]))


def evaluer(document: dict[str, Any], tolerance_s: float = 0.4) -> dict[str, Any]:
    idees = list(document.get("idees") or [])
    clips = list(document.get("clips") or [])
    details = []
    for clip in clips:
        details.append(
            {
                "fichier": clip.get("fichier"),
                "mi_idee": coupe_mi_idee(clip, idees, tolerance_s),
                "erreur_bornes_s": round(erreur_bornes(clip, idees), 3),
            }
        )
    n = len(details)
    k = sum(1 for d in details if d["mi_idee"])
    erreur = sum(float(d["erreur_bornes_s"]) for d in details) / n if n else 0.0
    return {
        "video": document.get("video"),
        "clips": n,
        "coupes_mi_idee": k,
        "pct_coupes_mi_idee": round(100.0 * k / n, 3) if n else 0.0,
        "erreur_bornes_s": round(erreur, 3),
        "details": details,
    }


def evaluer_dossier(dossier: str, tolerance_s: float = 0.4) -> dict[str, Any]:
    rapports = []
    for nom in sorted(os.listdir(dossier)):
        if nom.endswith(".json"):
            with open(os.path.join(dossier, nom), encoding="utf-8") as handle:
                rapports.append(evaluer(json.load(handle), tolerance_s))
    n = sum(int(r["clips"]) for r in rapports)
    k = sum(int(r["coupes_mi_idee"]) for r in rapports)
    erreur = sum(float(r["erreur_bornes_s"]) * int(r["clips"]) for r in rapports) / n if n else 0.0
    return {
        "videos": len(rapports),
        "clips": n,
        "coupes_mi_idee": k,
        "pct_coupes_mi_idee": round(100.0 * k / n, 3) if n else 0.0,
        "erreur_bornes_s": round(erreur, 3),
        "rapports": rapports,
    }
