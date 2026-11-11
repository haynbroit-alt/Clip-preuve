#!/usr/bin/env python3
"""Calcule le taux de clips coupés au milieu d'une idée et l'erreur de borne.

Usage : python tests/eval/rapport.py tests/eval/exemples
Chaque JSON décrit une vidéo annotée : idees[{debut_s, fin_s}] et clips[{debut_s, fin_s}].
"""

from __future__ import annotations

import json
import sys

from agents.eval_bornes import evaluer_dossier


def main(argv: list[str] | None = None) -> dict:
    args = list(sys.argv[1:] if argv is None else argv)
    dossier = args[0] if args else "tests/eval/exemples"
    rapport = evaluer_dossier(dossier)
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    return rapport


if __name__ == "__main__":
    main()
