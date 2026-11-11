"""Agent TRANSCRIPTEUR : ingestion (lien yt-dlp ou fichier), découpe en chunks de 10 min,
faster-whisper (timestamps par mot), ffmpeg silencedetect.
Artefacts : source.json, audio.wav, chunks/*.json, words.json, silences.json.
Cas limites : chunk anormalement troué (< 60 mots/min) -> repassé en beam 5
(mesuré : 276 -> 2033 mots sur un chunk Thinkerview) ;
vidéo > 3 h 05 refusée (ÉCHEC explicite) ; lien privé/géobloqué -> erreur yt-dlp remontée ;
VAD qui efface la parole (agents/vad.py) -> essai sans VAD, segments sûrs seulement (segment_sur),
noté dans vad_relances.json et sur la carte ;
chunk déjà transcrit -> réutilisé (reprise) ; aucun mot détecté -> ÉCHEC (musique seule, silence).
"""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, cast

from .alignement import aligner
from .common import jload, jsave, progress, sh, timed, ytdlp
from .log import logger
from .reprise import empreinte, noter
from .vad import choisir_mots, vad_ecrase

MAX_SEC = 3 * 3600 + 300
CHUNK = 600
MODEL = os.environ.get("CLIP_WHISPER", "small")
NO_SPEECH_MAX = 0.6  # passe sans VAD : segment gardé seulement s'il est probablement parlé…
LOGPROB_MIN = -1.0  # … et transcrit avec assurance
MODELS_DIR = os.environ.get("CLIP_WHISPER_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "models"))


def segment_sur(seg: Any) -> bool:
    """Passe sans VAD : un segment n'est gardé que s'il est probablement parlé et transcrit avec assurance."""
    return bool(getattr(seg, "no_speech_prob", 1.0) < NO_SPEECH_MAX and getattr(seg, "avg_logprob", -9.0) > LOGPROB_MIN)


def ingest(run: str, src: str) -> dict[str, Any]:
    meta = cast(dict[str, Any] | None, jload(os.path.join(run, "source.json")))
    if meta:
        return meta
    wav = os.path.join(run, "audio.wav")
    if re.match(r"https?://", src):
        info = json.loads(sh([*ytdlp(), "-J", "--no-playlist", src]).stdout)
        dur = info.get("duration") or 0
        if dur > MAX_SEC:
            raise RuntimeError(f"ÉCHEC : source de {dur / 3600:.2f} h > 3 h")
        sh(
            [
                *ytdlp(),
                "-f",
                "bestaudio[ext=m4a]/bestaudio",
                "--no-playlist",
                "-o",
                os.path.join(run, "audio_src.%(ext)s"),
                src,
            ]
        )
        a = glob.glob(os.path.join(run, "audio_src.*"))[0]
        meta = {
            "kind": "url",
            "src": src,
            "title": info.get("title"),
            "channel": info.get("channel"),
            "duration": dur,
            "audio": a,
        }
    else:
        if not os.path.exists(src):
            raise RuntimeError("ÉCHEC : fichier introuvable")
        dur = float(
            sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).stdout.strip()
        )
        if dur > MAX_SEC:
            raise RuntimeError(f"ÉCHEC : fichier de {dur / 3600:.2f} h > 3 h")
        meta = {
            "kind": "file",
            "src": os.path.abspath(src),
            "title": os.path.basename(src),
            "channel": None,
            "duration": dur,
            "audio": os.path.abspath(src),
        }
    sh(["ffmpeg", "-y", "-v", "error", "-i", meta["audio"], "-vn", "-ac", "1", "-ar", "16000", wav])
    meta["duration"] = float(
        sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav]).stdout.strip()
    )
    jsave(os.path.join(run, "source.json"), meta)
    noter(run, "ingestion", empreinte(wav))
    return meta


def _decoder(
    model: Any, chemin: str, lang: str, beam: int, offset: float, vad: bool
) -> tuple[list[dict[str, Any]], int]:
    """Sans VAD, seuls les segments `segment_sur` sont gardés : Whisper hallucine sur la musique."""
    segs, _info = model.transcribe(
        chemin,
        language=lang,
        beam_size=beam,
        word_timestamps=True,
        vad_filter=vad,
        condition_on_previous_text=False,
    )
    segs = list(segs)
    mots: list[dict[str, Any]] = []
    for seg in segs:
        if not vad and not segment_sur(seg):
            continue
        for w in seg.words or []:
            if w.word.strip():
                mots.append({"w": w.word.strip(), "s": round(w.start + offset, 3), "e": round(w.end + offset, 3)})
    return mots, len(segs)


def transcribe(run: str, meta: dict[str, Any], lang: str = "fr", align: str = "whisper") -> list[dict[str, Any]]:
    out = os.path.join(run, "words.json")
    aligne = os.path.join(run, "words_whisperx.json")
    if align == "whisperx" and os.path.exists(aligne):
        noter(run, "alignement")
        return cast(list[dict[str, Any]], jload(aligne))
    if os.path.exists(out) and align != "whisperx":
        logger().info("reprise", extra={"etape": "transcription", "run": run})
        noter(run, "transcription")
        return cast(list[dict[str, Any]], jload(out))
    if os.path.exists(out) and align == "whisperx":
        mots = cast(list[dict[str, Any]], jload(out))
        mots = aligner(mots, os.path.join(run, "audio.wav"), lang, align)
        jsave(aligne, mots)
        noter(run, "alignement")
        return mots
    from faster_whisper import WhisperModel

    model = WhisperModel(
        MODEL,
        device="cpu",
        compute_type="int8",
        download_root=MODELS_DIR,
        cpu_threads=int(os.environ.get("CLIP_THREADS", "4")),
    )
    cdir = os.path.join(run, "chunks")
    os.makedirs(cdir, exist_ok=True)
    dur, words, n = meta["duration"], [], int(meta["duration"] // CHUNK) + 1
    for i in range(n):
        cj = os.path.join(cdir, f"{i:03d}.json")
        if not os.path.exists(cj):
            cw = os.path.join(cdir, f"{i:03d}.wav")
            sh(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    str(i * CHUNK),
                    "-t",
                    str(CHUNK),
                    "-i",
                    os.path.join(run, "audio.wav"),
                    cw,
                ]
            )
            cdur = min(CHUNK, dur - i * CHUNK)
            ws: list[dict[str, Any]] = []
            sans_vad = False
            for beam in (1, 5):  # garde-fou : < 60 mots/min -> 2e passe beam 5
                brut, nseg = _decoder(model, cw, lang, beam, i * CHUNK, True)
                if vad_ecrase(cdur, brut, nseg):
                    secours, n2 = _decoder(model, cw, lang, beam, i * CHUNK, False)
                    w2, _sans = choisir_mots(cdur, brut, nseg, secours)
                    vient_sans_vad = bool(secours) and w2 is secours
                    logger().warning(
                        "VAD retiré, nouvel essai sans filtre",
                        extra={"chunk": i, "segments": nseg, "segments_sans": n2},
                    )
                else:
                    w2, vient_sans_vad = brut, False
                if len(w2) > len(ws):
                    ws, sans_vad = w2, vient_sans_vad
                if len(ws) >= 60 * cdur / 60 or cdur < 60:
                    break
            if sans_vad and ws:
                # passe sans VAD retenue (segments sûrs seulement) : notée sur la carte
                relances = cast(list[dict[str, Any]], jload(os.path.join(run, "vad_relances.json"), []))
                relances.append({"chunk": i, "debut_s": i * CHUNK, "mots": len(ws)})
                jsave(os.path.join(run, "vad_relances.json"), relances)
            jsave(cj, ws)
            os.remove(cw)
        words += jload(cj)
        progress(run, "transcription", 5 + int(45 * (i + 1) / n), f"chunk {i + 1}/{n}")
    if not words:
        raise RuntimeError("ÉCHEC : aucun mot transcrit")
    if align == "whisperx":
        words = aligner(words, os.path.join(run, "audio.wav"), lang, align)
        jsave(aligne, words)
        noter(run, "alignement")
    jsave(out, words)
    with open(os.path.join(run, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(" ".join(w["w"] for w in words))
    noter(run, "transcription")
    return words


def silences(run: str) -> list[list[float]]:
    out = os.path.join(run, "silences.json")
    if os.path.exists(out):
        return cast(list[list[float]], jload(out))
    r = sh(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            os.path.join(run, "audio.wav"),
            "-af",
            "silencedetect=noise=-32dB:d=0.25",
            "-f",
            "null",
            "-",
        ]
    )
    st, res = None, []
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m:
            st = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and st is not None:
            res.append([st, float(m.group(1))])
            st = None
    jsave(out, res)
    return res


def run_agent(
    run: str, src: str, align: str = "whisper"
) -> tuple[dict[str, Any], list[dict[str, Any]], list[list[float]]]:
    with timed(run, "ingestion"):
        progress(run, "ingestion", 2, src)
        meta = ingest(run, src)
    with timed(run, "transcription"):
        words = transcribe(run, meta, align=align)
    with timed(run, "silencedetect"):
        sil = silences(run)
    return meta, words, sil
