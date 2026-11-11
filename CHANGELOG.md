# Changelog

## Manifeste d'intégrité et banc du Falsificateur

- Chaque carte (certifiée ou candidate) est scellée : SHA-256 de l'audio transcrit, de la transcription, du clip
  livré, des prompts `skills/juge.md` et `skills/falsificateur.md`, commit du code, puis empreinte de la carte.
  `python -m agents.integrite runs/<id>` signale tout fichier ou toute carte modifiés depuis. Cela prouve
  l'absence de modification, pas la justesse du verdict.
- Banc du Falsificateur (`tests/eval/falsificateur/cas.json`, 30 extraits synthétiques, dont 5 injections de
  consigne) : LLM remplacé par une réponse complaisante, on mesure ce que le code attrape seul. Départ :
  « contredit juste après » 9 faux CONFLIT sur 19 et 4 CONFLIT manqués sur 11 ; « coupé en pleine idée »
  1 manqué sur 3. Chiffres figés dans `tests/test_eval_falsificateur.py`. Voir `docs/banc_falsificateur.md`.

## Réparation de la fusion PR #3 / PR #4

- `main` était cassé (8 tests en échec, ruff et mypy en erreur) : la fusion de `main` dans la PR #3 avait
  gardé l'orchestrateur de la PR #4, sans le verrou de livraison sur CONFLIT, les candidats non certifiés,
  `--align` ni l'export EDL / FCPXML. Orchestrateur de la PR #3 rétabli, avec l'archivage `preuve_<n>.*`.
- Une seule relance sans VAD (décision `agents/vad.py`) au lieu de deux ; la passe sans VAD ne garde que les
  segments jugés parlés et sûrs (`segment_sur`), contre les hallucinations de Whisper sur la musique.

## Non publié

Correctifs de fiabilité et de sécurité, sans changer la sélection, le Falsificateur ni les six agents.

- Régénérer ne détruit plus de carte : chaque clip garde `preuve_<n>.json` / `preuve_<n>.md`,
  `preuve.json` / `preuve.md` restent la dernière carte.
- Juge : une note non entière (`"8/10"`, `null`…) écarte le candidat au lieu de faire échouer le run.
- Python 3.11 minimum annoncé (yt-dlp épinglé l'exige) ; `install.sh` le vérifie ; CI de tests sur 3.11 et 3.12.
- Interface : message d'erreur et identifiants échappés (XSS) ; hôte local seulement (DNS rebinding) ;
  requêtes d'écriture venues d'un autre site refusées ; upload plafonné (`CLIP_MAX_UPLOAD_MO`, 8 Go) ;
  lien http(s) validé avant de créer le dossier du job. Tests de `app.py` ajoutés.
- Phrase clé vérifiée par le Greffier dans la transcription du clip final : retrouvée -> mots exacts de la
  transcription et minutage ; sinon `null` et « Phrase clé : INCONNU » sous le statut (le statut global, qui porte
  sur les 4 tests du Falsificateur, ne change pas). Texte du juge conservé dans `phrase_cle_verification.texte_juge`.
- « Pourquoi ce moment » étiqueté « avis du juge (IA), non vérifié » (et « donné sur les bornes initiales »
  quand le Falsificateur a déplacé les bornes).
- Transcripteur : si un morceau reste vide après 2 passes (musique sur la voix), 3e passe sans VAD qui ne garde
  que les segments jugés parlés et sûrs ; la relance est écrite dans `vad_relances.json` et sur la carte.

## 0.2.0 — 2026-11-10

Outillage d'un dépôt open source, sans changer la sélection ni le Falsificateur.

- README français, schéma des agents, licence MIT (Lhassan Charfa).
- pytest sans téléchargement de modèle : sélection, piège du Falsificateur, carte de preuve, coût.
- Contrats pydantic, schéma JSON de la carte (`schemas/preuve.schema.json`), instantanés.
- Journal JSON sur stderr. Ruff, mypy --strict, couverture de la logique hors entrées-sorties.
- CI en trois jobs (lint, typecheck, tests), actions épinglées, Dependabot, pre-commit.

## 0.1.0 — 2026-11-10

Import du pipeline v0 : six agents, orchestrateur, `./install.sh`, `./clip`, interface FastAPI.
