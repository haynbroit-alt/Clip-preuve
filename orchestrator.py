#!/usr/bin/env python3
"""ORCHESTRATEUR : enchaîne les agents transcripteur -> chercheur -> juge -> falsificateur -> monteur -> greffier.
Usage : python orchestrator.py <lien|fichier> [--run DOSSIER] [--regenerer]
--regenerer : réutilise transcription/silences (gratuit), exclut les clips déjà livrés, refait juge+falsificateur+rendu.
Cas limites : erreur d'un agent -> progress.json passe en ÉCHEC avec le message ; artefacts conservés pour reprise.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import traceback
from typing import Any

from agents import chercheur, falsificateur, greffier, juge, monteur, transcripteur
from agents.common import jload, jsave, progress, timed
from agents.log import logger

RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")


def run_id(src: str) -> str:
    return hashlib.sha1(src.encode()).hexdigest()[:10]


def main(src: str, run: str | None = None, regen: bool = False) -> tuple[str, dict[str, Any]]:
    run = run or os.path.join(RUNS, run_id(src))
    os.makedirs(run, exist_ok=True)
    with open(os.path.join(run, "src.txt"), "w") as f:
        f.write(src)
    try:
        meta, words, sil = transcripteur.run_agent(run, src)
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
            clip, crop = monteur.run_agent(run, meta, words, verdict["s"], verdict["e"], name)
        card = greffier.run_agent(run, meta, words, verdict, cand, crop, clip)
        if n > 1:
            os.replace(os.path.join(run, "preuve.json"), os.path.join(run, f"preuve_{n}.json"))
            os.replace(os.path.join(run, "preuve.md"), os.path.join(run, f"preuve_{n}.md"))
            jsave(os.path.join(run, "preuve.json"), card)
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
    a = ap.parse_args()
    r, c = main(a.src, a.run, a.regenerer)
    print(
        f"\nCLIP : {os.path.join(r, c['clip']['fichier'])}\n"
        f"PREUVE : {os.path.join(r, 'preuve.md')}\nSTATUT : {c['statut']}"
    )
