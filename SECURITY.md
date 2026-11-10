# Security

Clip-preuve tourne en local. Il n'y a pas de compte ni de service exposé par défaut : l'interface écoute `127.0.0.1`.

## Secrets

- `OPENROUTER_API_KEY` se lit dans l'environnement. Elle n'est pas affichée, pas écrite dans `llm_calls.jsonl`, pas écrite dans le journal JSON.
- Ne commitez pas `.env`, de clé, de jeton, de poids (`.gguf`, `.tflite`), d'audio, ni de vidéo.
- `install.sh` télécharge llama.cpp et le modèle dans `llm/`, qui est ignoré par git.

## Signaler un problème

Ouvrez un rapport GitHub privé si le dépôt le permet, sinon une issue sans y coller de clé, de transcript privé, ni d'URL non publique. Décrivez la version (`git rev-parse --short HEAD`) et le job de CI s'il s'agit d'un correctif.

## Dépendances

Les versions sont épinglées dans `pyproject.toml` et `requirements.txt`. Dependabot ouvre des mises à jour groupées. Le modèle GGUF et le détecteur de visage sont des téléchargements d'exécution, pas des dépendances Python.
