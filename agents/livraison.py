"""Verrou de livraison. Aucun fichier n'est écrit si le verdict validé contient un CONFLIT.

Le Falsificateur n'est pas modifié : ce module lit seulement son résultat déjà calculé.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .log import logger

CRITERES: tuple[str, ...] = ("hors_contexte", "info_prealable", "contredit_apres", "coupe_mi_idee")


class CritereLivre(BaseModel):
    """Critère tel que le Falsificateur l'a déjà tranché. CONFLIT n'est pas réécrit."""

    model_config = ConfigDict(extra="allow")
    verdict: str
    preuve: Any = ""


class VerdictLivre(BaseModel):
    model_config = ConfigDict(extra="allow")
    final: dict[str, CritereLivre]
    statut: str
    s: float
    e: float
    avertissement: str | None = None
    iteration: int = Field(default=1)


def valider_verdict(verdict: dict[str, Any]) -> VerdictLivre:
    """Lève ValidationError si la forme n'est pas celle d'un verdict de Falsificateur."""
    return VerdictLivre.model_validate(verdict)


def livraison_autorisee(verdict: dict[str, Any]) -> bool:
    """Vrai seulement si les quatre critères sont présents et qu'aucun n'est CONFLIT."""
    try:
        modele = valider_verdict(verdict)
    except ValidationError:
        return False
    if modele.statut not in {"PROUVÉ", "INCONNU"}:
        return False
    for nom in CRITERES:
        critere = modele.final.get(nom)
        if critere is None or critere.verdict not in {"PROUVÉ", "INCONNU"}:
            return False
    return True


def exiger_livraison(verdict: dict[str, Any]) -> VerdictLivre:
    if not livraison_autorisee(verdict):
        logger().warning("livraison refusée", extra={"raison": "CONFLIT"})
        raise RuntimeError("ÉCHEC : livraison refusée, le Falsificateur contient un CONFLIT")
    return valider_verdict(verdict)


def exporter(verdict: dict[str, Any], ecrire: Callable[[], Any]) -> Any:
    """N'appelle `ecrire` que si le verdict validé autorise la livraison."""
    exiger_livraison(verdict)
    return ecrire()
