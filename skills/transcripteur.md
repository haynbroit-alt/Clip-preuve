Rôle : TRANSCRIPTEUR. Pas de LLM. Récupère l'audio (yt-dlp ou fichier), refuse > 3 h, découpe en chunks de 10 min,
transcrit avec faster-whisper (modèle `small`, int8, CPU, langue fr, timestamps par mot), détecte les silences
(ffmpeg silencedetect -32 dB, 0,25 s). N'invente jamais un mot : ce qui n'est pas entendu n'est pas écrit.
