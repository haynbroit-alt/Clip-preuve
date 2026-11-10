# Clip+Preuve 🎬✅

**Un lien → UN clip vertical (20-90 s) → avec sa preuve.**
Pas 20 clips moyens : le meilleur moment, et un « Falsificateur » qui essaie de le casser avant de vous le donner.
Si aucun moment ne tient, l'outil **le dit** au lieu de faire semblant.

![démo](docs/demo.gif)

## Utilisation (2 commandes)

```bash
./install.sh                                        # une seule fois (Linux, ffmpeg + node conseillés)
./clip "https://www.youtube.com/watch?v=..."        # → runs/<id>/clip.mp4 + preuve.md
```

Interface web : `./clip --ui` puis ouvrez http://127.0.0.1:8000 — un champ, un bouton, une barre de progression,
la vidéo, « Pourquoi ce moment », et **Régénérer** (gratuit : la transcription est réutilisée).

![interface](docs/interface.png)

**0 € :** tout tourne en local sur le CPU (faster-whisper + Qwen2.5-7B via llama.cpp). Aucune clé, aucun compte.
Optionnel : `export OPENROUTER_API_KEY=...` pour utiliser un modèle `:free` d'OpenRouter à la place.

## La carte de preuve

Chaque clip sort avec `preuve.json` + `preuve.md` : timestamps, citation exacte de début et de fin,
raison du choix, notes du juge, et verdict du Falsificateur sur 4 tests (**PROUVÉ / INCONNU / CONFLIT**) :
hors contexte ? besoin d'une info donnée avant ? contredit juste après ? coupé en pleine idée ?
Les citations de « correction » doivent exister mot pour mot dans les 60 s qui suivent, sinon le verdict reste INCONNU.

Exemple réel : [docs/exemple_preuve.md](docs/exemple_preuve.md) · test piège : [docs/test_piege_resultat.json](docs/test_piege_resultat.json)

## Sous le capot : 6 agents + 1 orchestrateur

| Agent | Fichier | Skill (prompt / rôle) |
|---|---|---|
| Transcripteur | `agents/transcripteur.py` | `skills/transcripteur.md` |
| Chercheur de candidats | `agents/chercheur.py` | `skills/chercheur.md` |
| Juge (LLM, JSON strict) | `agents/juge.py` | `skills/juge.md` |
| Falsificateur (LLM séparé) | `agents/falsificateur.py` | `skills/falsificateur.md` |
| Monteur (9:16, visage, sous-titres) | `agents/monteur.py` | `skills/monteur.md` |
| Greffier (carte de preuve, coût) | `agents/greffier.py` | `skills/greffier.md` |

`orchestrator.py` les enchaîne. Chaque étape écrit ses artefacts dans `runs/<id>/` (words.json, candidates.json,
scores.json, falsification.json, llm_calls.jsonl avec le coût de chaque appel, timings.json).

Tests : `python tests/trap_test.py` (piège « l'erreur que tout le monde fait… ») · `python compare.py runs/<id> --manuel clip_humain.mp4`.

## Limites connues (v0, honnête)

- CPU seulement : une vidéo de 3 h prend environ 30-40 min (transcription + LLM). Mesures dans `timings.json`.
- Le LLM local (7B) se trompe parfois ; le Falsificateur est volontairement sévère et un garde-fou lexical le complète.
- Recadrage : un seul cadrage fixe par clip (visage dominant), pas de suivi dynamique.

Licence MIT.
