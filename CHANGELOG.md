# Changelog

## 0.3.0 — 2026-11-10

Améliorations issues de la comparaison avec les outils de clips courts. Le calcul des verdicts du Falsificateur ne change pas.

- Verrou de livraison : un CONFLIT validé interdit l'export du fichier.
- Reprise par empreinte du média dans `runs/<hash>/`.
- Si le VAD efface la parole (0 segment ou plus de 80 %), nouvel essai sans VAD.
- `--align whisperx` optionnel, repli sur les timestamps faster-whisper.
- Cadrage du locuteur actif (tenue 1,5 s, écran partagé si alternance rapide).
- `--candidats N` exporte les suivants non certifiés, plus un EDL et un FCPXML.
- Harnais `tests/eval/` : part de clips coupés au milieu d'une idée, erreur de borne.

## 0.2.0 — 2026-11-10

Outillage d'un dépôt open source, sans changer la sélection ni le Falsificateur.

- README français, schéma des agents, licence MIT (Lhassan Charfa).
- pytest sans téléchargement de modèle : sélection, piège du Falsificateur, carte de preuve, coût.
- Contrats pydantic, schéma JSON de la carte (`schemas/preuve.schema.json`), instantanés.
- Journal JSON sur stderr. Ruff, mypy --strict, couverture de la logique hors entrées-sorties.
- CI en trois jobs (lint, typecheck, tests), actions épinglées, Dependabot, pre-commit.

## 0.1.0 — 2026-11-10

Import du pipeline v0 : six agents, orchestrateur, `./install.sh`, `./clip`, interface FastAPI.
