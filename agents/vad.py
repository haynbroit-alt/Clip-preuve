"""Décision VAD : si le filtre efface la parole, on recommence sans lui.

Un segment vide ou une parole couvrant moins de 20 % du chunk (plus de 80 % retiré)
est le cas « musique seule » qui a déjà effacé une voix.
"""

from __future__ import annotations

from typing import Any

SEUIL_PAROLE = 0.2


def duree_parole(mots: list[dict[str, Any]]) -> float:
    total = 0.0
    for mot in mots:
        total += max(0.0, float(mot["e"]) - float(mot["s"]))
    return total


def vad_ecrase(duree: float, mots: list[dict[str, Any]], n_segments: int) -> bool:
    """Vrai quand il faut relancer la transcription sans VAD."""
    if n_segments <= 0 or not mots:
        return True
    if duree <= 0:
        return False
    return duree_parole(mots) < SEUIL_PAROLE * duree


def choisir_mots(
    duree: float,
    mots_vad: list[dict[str, Any]],
    n_segments: int,
    mots_sans_vad: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Retourne les mots retenus et un booléen « essai sans VAD utilisé »."""
    if not vad_ecrase(duree, mots_vad, n_segments):
        return mots_vad, False
    if len(mots_sans_vad) >= len(mots_vad):
        return mots_sans_vad, True
    return mots_vad, True
