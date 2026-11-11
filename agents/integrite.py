"""Manifeste d'intégrité de la carte de preuve.

Ce que la carte enregistre : l'empreinte SHA-256 de l'audio transcrit, de la transcription, du clip livré
et des prompts utilisés (skills/juge.md, skills/falsificateur.md), le commit du code, puis l'empreinte de
la carte elle-même.

Ce que cela prouve : qu'un fichier n'a pas changé depuis la création de la carte. Ce que cela ne prouve
pas : que le verdict est juste, ni que la carte n'a pas été réécrite par quelqu'un qui peut aussi
recalculer l'empreinte. Pour cela, l'empreinte de la carte doit être publiée ailleurs (description de la
vidéo, par exemple).

Vérifier un run : python -m agents.integrite runs/<id>   (code de sortie 1 si un écart est trouvé)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import Any

from .common import ROOT, jload, jsave

PROMPTS: tuple[str, ...] = ("juge", "falsificateur")
_BLOC = 1024 * 1024


def sha256_fichier(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    hachage = hashlib.sha256()
    with open(path, "rb") as handle:
        for bloc in iter(lambda: handle.read(_BLOC), b""):
            hachage.update(bloc)
    return hachage.hexdigest()


def version_code() -> dict[str, Any]:
    """Commit git du code et présence de modifications non commitées. Inconnu hors dépôt git."""
    try:
        commit = subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        etat = subprocess.run(
            ["git", "-C", ROOT, "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "modifie": None}
    return {"commit": commit or None, "modifie": bool(etat.strip())}


def _fichiers(run: str, clip: str) -> dict[str, str]:
    chemins = {
        "audio": os.path.join(run, "audio.wav"),
        "transcription": os.path.join(run, "words.json"),
        "clip": os.path.join(run, os.path.basename(clip)),
    }
    for nom in PROMPTS:
        chemins[f"prompt_{nom}"] = os.path.join(ROOT, "skills", nom + ".md")
    return chemins


def empreinte_carte(card: dict[str, Any]) -> str:
    """SHA-256 du JSON canonique de la carte, sans le champ integrite.empreinte_carte lui-même."""
    copie = json.loads(json.dumps(card, ensure_ascii=False))
    integ = copie.get("integrite")
    if isinstance(integ, dict):
        integ.pop("empreinte_carte", None)
    canon = json.dumps(copie, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def sceller(run: str, card: dict[str, Any], nom_carte: str = "preuve") -> dict[str, Any]:
    """Ajoute le manifeste à la carte, réécrit <nom_carte>.json et ajoute une ligne à <nom_carte>.md."""
    fichiers = {k: sha256_fichier(p) for k, p in _fichiers(run, card["clip"]["fichier"]).items()}
    card["integrite"] = {"algorithme": "sha256", "fichiers": fichiers, "code": version_code()}
    card["integrite"]["empreinte_carte"] = empreinte_carte(card)
    jsave(os.path.join(run, nom_carte + ".json"), card)
    md = os.path.join(run, nom_carte + ".md")
    if os.path.exists(md):
        with open(md, "a", encoding="utf-8") as handle:
            handle.write(
                f"**Intégrité** : empreinte de la carte sha256:{card['integrite']['empreinte_carte']} "
                f"(vérifier : `python -m agents.integrite {run}`)\n"
            )
    return card


def verifier(run: str, nom_carte: str = "preuve") -> list[str]:
    """Écarts entre la carte et les fichiers du run. Liste vide = rien n'a changé depuis le scellement."""
    card = jload(os.path.join(run, nom_carte + ".json"))
    if not isinstance(card, dict) or not isinstance(card.get("integrite"), dict):
        return ["carte absente ou non scellée"]
    integ = card["integrite"]
    ecarts = []
    if integ.get("empreinte_carte") != empreinte_carte(card):
        ecarts.append("la carte a été modifiée après scellement")
    attendus = integ.get("fichiers") or {}
    for nom, chemin in _fichiers(run, card["clip"]["fichier"]).items():
        if nom not in attendus:
            continue
        actuel = sha256_fichier(chemin)
        if actuel != attendus[nom]:
            ecarts.append(f"{nom} : empreinte {str(actuel)[:12]} au lieu de {str(attendus[nom])[:12]}")
    return ecarts


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage : python -m agents.integrite runs/<id> [nom_carte]")
        return 2
    ecarts = verifier(args[0], args[1] if len(args) > 1 else "preuve")
    if ecarts:
        print("ÉCART :\n- " + "\n- ".join(ecarts))
        return 1
    print("OK : carte et fichiers identiques au scellement")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
