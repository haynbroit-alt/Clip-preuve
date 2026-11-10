"""Alignement forcé optionnel. Par défaut, les timestamps de faster-whisper restent en place.

`--align whisperx` charge wav2vec2 français si le paquet est installé. Sinon, repli
sans erreur : les mots déjà datés sont rendus tels quels.
"""

from __future__ import annotations

from typing import Any

from .log import logger

MODELE_FR = "WAV2VEC2_ASR_LARGE_LV60K_960H"


def aligner(
    mots: list[dict[str, Any]],
    audio: str,
    langue: str = "fr",
    mode: str = "whisper",
) -> list[dict[str, Any]]:
    if mode != "whisperx" or not mots:
        return mots
    try:
        import whisperx
    except ImportError:
        logger().warning("whisperx absent, timestamps faster-whisper conservés")
        return mots
    try:
        charge = whisperx.load_audio(audio)
        modele, meta = whisperx.load_align_model(language_code=langue, device="cpu")
        segments = [
            {
                "text": " ".join(str(m["w"]) for m in mots),
                "start": float(mots[0]["s"]),
                "end": float(mots[-1]["e"]),
            }
        ]
        aligne = whisperx.align(segments, modele, meta, charge, "cpu", return_char_alignments=False)
        rendu: list[dict[str, Any]] = []
        for seg in aligne.get("segments") or []:
            for w in seg.get("words") or []:
                if w.get("word") and "start" in w and "end" in w:
                    rendu.append(
                        {
                            "w": str(w["word"]).strip(),
                            "s": round(float(w["start"]), 3),
                            "e": round(float(w["end"]), 3),
                        }
                    )
        return rendu or mots
    except Exception as exc:
        logger().warning("alignement whisperx échoué", extra={"erreur": str(exc)[:160]})
        return mots
