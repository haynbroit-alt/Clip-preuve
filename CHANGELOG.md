# Changelog

## 0.2.0 — 2026-11-10

Outillage d'un dépôt open source, sans changer la sélection ni le Falsificateur.

- README français, schéma des agents, licence MIT (Lhassan Charfa).
- pytest sans téléchargement de modèle : sélection, piège du Falsificateur, carte de preuve, coût.
- Contrats pydantic, schéma JSON de la carte (`schemas/preuve.schema.json`), instantanés.
- Journal JSON sur stderr. Ruff, mypy --strict, couverture de la logique hors entrées-sorties.
- CI en trois jobs (lint, typecheck, tests), actions épinglées, Dependabot, pre-commit.

## 0.1.0 — 2026-11-10

Import du pipeline v0 : six agents, orchestrateur, `./install.sh`, `./clip`, interface FastAPI.
