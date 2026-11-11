#!/usr/bin/env python3
"""Mesure du Falsificateur sur le banc annoté (LLM remplacé : seul le code décide).

Usage : python tests/eval/rapport_falsificateur.py [tests/eval/falsificateur] [--details]
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.eval_falsificateur import charger, evaluer  # noqa: E402


def main(argv: list[str] | None = None) -> dict:
    args = list(sys.argv[1:] if argv is None else argv)
    details = "--details" in args
    chemins = [a for a in args if not a.startswith("--")]
    rapport = evaluer(charger(chemins[0] if chemins else "tests/eval/falsificateur"))
    sortie = rapport if details else {k: v for k, v in rapport.items() if k != "resultats"}
    print(json.dumps(sortie, ensure_ascii=False, indent=2))
    return rapport


if __name__ == "__main__":
    main()
