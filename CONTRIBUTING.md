# Contribuer

Les modifications se font par pull request vers `main`. La CI lance trois jobs : Ruff, mypy --strict, pytest. Elle ne télécharge pas de modèle.

## English

Open a pull request against `main`. CI runs Ruff, mypy --strict, and pytest — no model download. Do not commit secrets, `.gguf` / `.tflite` weights, audio, or video files. Selection and Falsificateur behaviour is covered by unit tests: change it only with a failing test first.

## Mise en route

Pour lancer l'outil (modèle inclus, plusieurs gigaoctets) :

```bash
./install.sh
./clip "https://www.youtube.com/watch?v=..."
```

Pour développer, Python 3.10+ suffit :

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy --strict agents orchestrator.py
.venv/bin/pytest --cov=agents --cov=orchestrator --cov-fail-under=85
.venv/bin/pre-commit run --all-files
```

`requirements.txt` ne sert qu'à l'exécution (Whisper, FastAPI, mediapipe). Les tests simulent le LLM et Whisper.

## Ce qu'on ne change pas à la légère

Le chercheur, le juge et le Falsificateur décident du moment retenu et du statut PROUVÉ / INCONNU / CONFLIT. Un clip qui s'arrête avant la correction de l'orateur doit rester **CONFLIT**. Si vous touchez à cette logique, ajoutez ou adaptez un test dans `tests/test_chercheur.py`, `tests/test_juge.py` ou `tests/test_falsificateur.py` qui échoue avant le correctif.

`python tests/trap_test.py` parle au LLM local. Il n'est pas lancé par pytest.

## Fichiers à ne pas committer

- secrets (`.env`, clés, jetons)
- poids (`.gguf`, `.tflite`) et les dossiers `models/`, `llm/`
- audio, et toute vidéo
- les dossiers `runs/` et `tests/trap_run/`

Les images de démo déjà dans `docs/` (GIF et PNG, sous 5 Mo) restent dans le dépôt.

## Style

Le pipeline v0 est compact. Le code nouveau (tests, outillage) passe `ruff check` avec la configuration de `pyproject.toml`. Pas de formatage massif des agents sans raison.
