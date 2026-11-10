# PLAN v0 — Clip + Preuve (hypothèses notées, aucune question)
1. Hyp. LLM : aucune clé OpenRouter/Cloudflare trouvée sur la box → LLM local Qwen2.5-3B-Instruct Q4 (llama.cpp, CPU, 0 €). Clé OPENROUTER_API_KEY lue si présente un jour.
2. Pipeline `pipeline.py` : ingest (yt-dlp audio / fichier, chunks 10 min) → faster-whisper small (mots) → silencedetect → phrases + segmentation par sujet → candidats 20-90 s.
3. Pré-tri heuristique (gratuit) → top 6 notés par LLM en JSON strict (accroche 3 s, autonomie, payoff, densité, citabilité).
4. Falsificateur = appel LLM séparé, ±60 s, 4 critères PROUVÉ/INCONNU/CONFLIT + garde-fou lexical ; CONFLIT → bornes ajustées ou candidat suivant, 3 itérations max, sinon INCONNU + avertissement.
5. Rendu : seulement la section vidéo utile (yt-dlp --download-sections), 9:16 1080x1920, visage mediapipe (repli centre), sous-titres mot par mot, loudnorm, fondus 80 ms.
6. Sortie par run : clip.mp4, preuve.json, preuve.md, llm_calls.jsonl (coût), timings.json — interface `app.py` + `index.html` (FastAPI seul).
7. Tests : `tests/trap_test.py` (piège « l'erreur que tout le monde fait »), `compare.py` (référence manuelle = INCONNU si absente).
8. Prospects (vidéos test) : podcast GDIY https://www.youtube.com/watch?v=iJWFW45Eplg (2 h 59) · interview Thinkerview https://www.youtube.com/watch?v=0QSlS8ifBbo (2 h 23) · conférence Le Précepteur https://www.youtube.com/watch?v=yK3Ei_FJ8hY (39 min).
9. Coupe si manque de temps : fonctions (suivi visage dynamique, multi-locuteurs), jamais le cœur clip+preuve.
