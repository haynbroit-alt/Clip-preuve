"""Cache de transcription par empreinte du média. Un run interrompu reprend le même dossier."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from .common import jload, jsave


def empreinte(path: str) -> str:
    """SHA-256 du fichier, tronqué à 16 caractères hexadécimaux."""
    hachage = hashlib.sha256()
    with open(path, "rb") as handle:
        for bloc in iter(lambda: handle.read(1024 * 1024), b""):
            hachage.update(bloc)
    return hachage.hexdigest()[:16]


def _dossier(runs: str, digest: str) -> str:
    path = os.path.join(runs, digest)
    os.makedirs(path, exist_ok=True)
    return path


def chercher_media(runs: str, digest: str) -> str | None:
    """Retourne un run déjà amorcé dont reprise.json porte cette empreinte audio."""
    if not os.path.isdir(runs):
        return None
    for nom in os.listdir(runs):
        marqueur = os.path.join(runs, nom, "reprise.json")
        etat = jload(marqueur, {})
        if isinstance(etat, dict) and etat.get("media_sha256") == digest:
            if os.path.exists(os.path.join(runs, nom, "words.json")):
                return os.path.join(runs, nom)
    return None


def dossier_pour(runs: str, src: str) -> str:
    """Dossier stable : empreinte du fichier, ou SHA-256 de l'URL si le média n'est pas local."""
    if os.path.isfile(src):
        digest = empreinte(src)
        connu = chercher_media(runs, digest)
        if connu:
            return connu
        return _dossier(runs, digest)
    digest = hashlib.sha256(src.encode()).hexdigest()[:16]
    return _dossier(runs, digest)


def lire(run: str) -> dict[str, Any]:
    etat = jload(os.path.join(run, "reprise.json"), {"etapes": []})
    if not isinstance(etat, dict):
        return {"etapes": []}
    etat.setdefault("etapes", [])
    return etat


def noter(run: str, etape: str, media_sha256: str | None = None) -> dict[str, Any]:
    etat = lire(run)
    etapes = etat["etapes"]
    if isinstance(etapes, list) and etape not in etapes:
        etapes.append(etape)
    if media_sha256:
        etat["media_sha256"] = media_sha256
    jsave(os.path.join(run, "reprise.json"), etat)
    return etat


def transcription_en_cache(run: str) -> bool:
    return os.path.exists(os.path.join(run, "words.json"))
