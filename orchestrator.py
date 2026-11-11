#!/usr/bin/env python3
"""ORCHESTRATEUR : enchaîne les agents transcripteur -> chercheur -> juge -> falsificateur -> monteur -> greffier.
Usage : python orchestrator.py <lien|fichier> [--run DOSSIER] [--regenerer]
--regenerer : réutilise transcription/silences (gratuit), exclut les clips déjà livrés, refait juge+falsificateur+rendu.
Chaque clip garde sa carte (preuve_<n>.json/.md) ; preuve.json/.md = la dernière.
Cas limites : erreur d'un agent -> progress.json passe en ÉCHEC avec le message ; artefacts conservés pour reprise.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import traceback
from typing import Any, cast

from agents import chercheur, falsificateur, greffier, integrite, juge, monteur, transcripteur
from agents.common import jload, jsave, progress, timed
from agents.edl import edl, fcpxml
from agents.livraison import CRITERES, exporter, livraison_autorisee
from agents.log import logger
from agents.reprise import dossier_pour

RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")


def run_id(src: str) -> str:
    return hashlib.sha1(src.encode()).hexdigest()[:10]


def numero_clip(fichier: str) -> int | None:
    """clip.mp4 -> 1, clip_3.mp4 -> 3, autre nom -> None."""
    if fichier == "clip.mp4":
        return 1
    m = re.fullmatch(r"clip_(\d+)\.mp4", fichier)
    return int(m.group(1)) if m else None


def archiver_derniere_carte(run: str) -> None:
    """Avant que le Greffier n'écrase preuve.json / preuve.md, les copier sous preuve_<n>.*
    (n = numéro du clip qu'elles décrivent). Une copie déjà présente n'est jamais écrasée."""
    card = jload(os.path.join(run, "preuve.json"))
    if not isinstance(card, dict):
        return
    n = numero_clip(str(card.get("clip", {}).get("fichier", "")))
    if n is None:
        return
    for ext in ("json", "md"):
        src, dst = os.path.join(run, f"preuve.{ext}"), os.path.join(run, f"preuve_{n}.{ext}")
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)


def _statut_hors_boucle(final: dict[str, Any]) -> tuple[str, str | None]:
    verdicts = [final[nom]["verdict"] for nom in CRITERES if nom in final]
    if any(v == "CONFLIT" for v in verdicts):
        return "INCONNU", None
    if verdicts and all(v == "PROUVÉ" for v in verdicts):
        return "PROUVÉ", None
    return "INCONNU", "Aucun CONFLIT trouvé, mais au moins un critère non prouvé (INCONNU)."


def _ecrire_montage(
    run: str,
    meta: dict[str, Any],
    words: list[dict[str, Any]],
    verdict: dict[str, Any],
    nom: str,
) -> tuple[str, dict[str, Any]]:
    def ecrire() -> tuple[str, dict[str, Any]]:
        return monteur.run_agent(run, meta, words, verdict["s"], verdict["e"], nom)

    return cast(tuple[str, dict[str, Any]], exporter(verdict, ecrire))


def _candidats(
    run: str,
    meta: dict[str, Any],
    words: list[dict[str, Any]],
    sents: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    choisi: str,
    n: int,
) -> list[dict[str, Any]]:
    if n <= 0:
        return []
    cartes: list[dict[str, Any]] = []
    for cand in ranked:
        if cand["id"] == choisi or len(cartes) >= n:
            continue
        brut = falsificateur.falsify(run, sents, int(cand["i"]), int(cand["j"]), 1)
        statut, avertissement = _statut_hors_boucle(brut["final"])
        verdict = {
            **brut,
            "statut": statut,
            "avertissement": avertissement,
            "iteration": 1,
        }
        if not livraison_autorisee(verdict):
            logger().info("candidat non livré", extra={"candidat": cand["id"], "raison": "CONFLIT"})
            continue
        nom = f"candidat_{cand['id']}.mp4"
        _clip, crop = _ecrire_montage(run, meta, words, verdict, nom)
        card = greffier.run_agent(run, meta, words, verdict, cand, crop, _clip, certifie=False)
        card = integrite.sceller(run, card, f"preuve_{cand['id']}")
        cartes.append(card)
    return cartes


def _timeline(run: str, meta: dict[str, Any], cartes: list[dict[str, Any]]) -> None:
    clips = [
        {
            "debut_s": c["clip"]["debut_s"],
            "fin_s": c["clip"]["fin_s"],
            "nom": c["clip"]["fichier"],
            "src": meta.get("src", ""),
        }
        for c in cartes
    ]
    with open(os.path.join(run, "clip.edl"), "w", encoding="utf-8") as handle:
        handle.write(edl(clips))
    with open(os.path.join(run, "clip.fcpxml"), "w", encoding="utf-8") as handle:
        handle.write(fcpxml(clips))


def main(
    src: str,
    run: str | None = None,
    regen: bool = False,
    align: str = "whisper",
    candidats: int = 0,
) -> tuple[str, dict[str, Any]]:
    run = run or dossier_pour(RUNS, src)
    os.makedirs(run, exist_ok=True)
    with open(os.path.join(run, "src.txt"), "w") as f:
        f.write(src)
    try:
        meta, words, sil = transcripteur.run_agent(run, src, align=align)
        hist = jload(os.path.join(run, "livres.json"), [])
        n = len(hist) + 1 if regen else 1
        if not regen:
            hist = []
        with timed(run, "chercheur"):
            progress(run, "chercheur", 52, "candidats")
            sents, cands = chercheur.run_agent(run, words, sil, exclude=[(h[0], h[1]) for h in hist])
        with timed(run, "juge"):
            ranked = juge.run_agent(run, words, cands)
        with timed(run, "falsificateur"):
            verdict, cand, _ = falsificateur.run_agent(run, sents, ranked)
        name = "clip.mp4" if n == 1 else f"clip_{n}.mp4"
        with timed(run, "monteur"):
            clip, crop = _ecrire_montage(run, meta, words, verdict, name)
        if n > 1:
            archiver_derniere_carte(run)
        card = greffier.run_agent(run, meta, words, verdict, cand, crop, clip, certifie=True)
        card = integrite.sceller(run, card)
        md_path = os.path.join(run, "preuve.md")
        with open(md_path, encoding="utf-8") as handle:
            md_certifie = handle.read()
        extras = _candidats(run, meta, words, sents, ranked, cand["id"], candidats)
        jsave(os.path.join(run, "preuve.json"), card)
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(md_certifie)
        _timeline(run, meta, [card, *extras])
        if n > 1:
            # preuve.json / preuve.md = dernière carte ; preuve_<n>.* = sa copie numérotée
            for ext in ("json", "md"):
                shutil.copyfile(os.path.join(run, f"preuve.{ext}"), os.path.join(run, f"preuve_{n}.{ext}"))
        hist.append([verdict["s"], verdict["e"], name])
        jsave(os.path.join(run, "livres.json"), hist)
        progress(run, "terminé", 100, f"{name} — statut {card['statut']}")
        return run, card
    except Exception as e:
        jsave(
            os.path.join(run, "progress.json"),
            {"step": "ÉCHEC", "pct": 100, "msg": str(e), "trace": traceback.format_exc()[-2000:]},
        )
        logger().exception("échec du run", extra={"run": run})
        raise


if __name__ == "__main__":  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--run")
    ap.add_argument("--regenerer", action="store_true")
    ap.add_argument("--align", choices=["whisper", "whisperx"], default="whisper")
    ap.add_argument("--candidats", type=int, default=0)
    a = ap.parse_args()
    r, c = main(a.src, a.run, a.regenerer, a.align, a.candidats)
    print(
        f"\nCLIP : {os.path.join(r, c['clip']['fichier'])}\n"
        f"PREUVE : {os.path.join(r, 'preuve.md')}\nSTATUT : {c['statut']}"
    )
