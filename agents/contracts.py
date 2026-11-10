"""Contrats pydantic des sorties LLM.

La validation est stricte sur la forme (verdict textuel, notes entières) sans changer
le résultat historique : un verdict hors PROUVÉ/INCONNU/CONFLIT devient INCONNU, une
note hors 0-10 est ramenée seulement dans le score, et le dict brut reste stocké.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

VERDICTS: frozenset[str] = frozenset({"PROUVÉ", "INCONNU", "CONFLIT"})
RANG: dict[str, int] = {"PROUVÉ": 0, "INCONNU": 1, "CONFLIT": 2}
CLES_JUGE: tuple[str, ...] = (
    "accroche_3s",
    "autonomie",
    "payoff",
    "densite",
    "citabilite",
)


class CritereLLM(BaseModel):
    """Un test du Falsificateur tel que le modèle le renvoie."""

    model_config = ConfigDict(extra="ignore")
    verdict: str
    preuve: Any = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def verdict_texte(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("verdict non textuel")
        return value

    @field_validator("verdict")
    @classmethod
    def verdict_connu(cls, value: str) -> str:
        if value not in VERDICTS:
            return "INCONNU"
        return value


class SortieFalsificateur(BaseModel):
    """Objet JSON complet attendu de l'appel Falsificateur."""

    model_config = ConfigDict(extra="forbid")
    affirmation_du_clip: str = ""
    correction_apres: str = ""
    suite_necessaire: str = ""
    hors_contexte: CritereLLM | None = None
    info_prealable: CritereLLM | None = None


class NotesJuge(BaseModel):
    """Cinq notes. `int()` est le même cast que le score historique."""

    model_config = ConfigDict(extra="ignore")
    accroche_3s: int = 0
    autonomie: int = 0
    payoff: int = 0
    densite: int = 0
    citabilite: int = 0

    @field_validator(*CLES_JUGE, mode="before")
    @classmethod
    def entier(cls, value: Any) -> int:
        return int(value)


def normaliser_critere(raw: object) -> dict[str, Any]:
    """Même table de vérité que l'ancien dict inline du Falsificateur.

    Non-dict -> INCONNU / « réponse absente ».
    Dict -> verdict ramené à INCONNU s'il n'est pas du vocabulaire, preuve brute conservée.
    """
    if not isinstance(raw, dict):
        return {"verdict": "INCONNU", "preuve": "réponse absente"}
    try:
        modele = CritereLLM.model_validate({"verdict": raw.get("verdict", ""), "preuve": raw.get("preuve", "")})
    except ValueError:
        verdict = raw.get("verdict")
        if verdict not in VERDICTS:
            verdict = "INCONNU"
        return {"verdict": verdict, "preuve": raw.get("preuve", "")}
    return {"verdict": modele.verdict, "preuve": raw.get("preuve", "")}


def notes_juge(raw: dict[str, Any]) -> NotesJuge:
    """Valide les cinq notes. Lève si une valeur n'est pas convertible par int()."""
    return NotesJuge.model_validate({cle: raw.get(cle, 0) for cle in CLES_JUGE})
