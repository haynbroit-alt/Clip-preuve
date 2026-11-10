"""Agent TRANSCRIPTEUR : ingestion (lien yt-dlp ou fichier), découpe en chunks de 10 min,
faster-whisper (timestamps par mot), ffmpeg silencedetect.
Artefacts : source.json, audio.wav, chunks/*.json, words.json, silences.json.
Cas limites : chunk anormalement troué (< 60 mots/min) -> repassé en beam 5 (mesuré : 276 -> 2033 mots sur un chunk Thinkerview) ;
vidéo > 3 h 05 refusée (ÉCHEC explicite) ; lien privé/géobloqué -> erreur yt-dlp remontée ;
chunk déjà transcrit -> réutilisé (reprise) ; aucun mot détecté -> ÉCHEC (musique seule, silence).
"""
import glob, json, os, re
from .common import jload, jsave, progress, sh, timed, tool, ytdlp

MAX_SEC = 3 * 3600 + 300
CHUNK = 600
MODEL = os.environ.get("CLIP_WHISPER", "small")
MODELS_DIR = os.environ.get("CLIP_WHISPER_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "models"))


def ingest(run, src):
    meta = jload(os.path.join(run, "source.json"))
    if meta:
        return meta
    wav = os.path.join(run, "audio.wav")
    if re.match(r"https?://", src):
        info = json.loads(sh([*ytdlp(), "-J", "--no-playlist", src]).stdout)
        dur = info.get("duration") or 0
        if dur > MAX_SEC:
            raise RuntimeError(f"ÉCHEC : source de {dur/3600:.2f} h > 3 h")
        sh([*ytdlp(), "-f", "bestaudio[ext=m4a]/bestaudio", "--no-playlist", "-o",
            os.path.join(run, "audio_src.%(ext)s"), src])
        a = glob.glob(os.path.join(run, "audio_src.*"))[0]
        meta = {"kind": "url", "src": src, "title": info.get("title"), "channel": info.get("channel"),
                "duration": dur, "audio": a}
    else:
        if not os.path.exists(src):
            raise RuntimeError("ÉCHEC : fichier introuvable")
        dur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).stdout.strip())
        if dur > MAX_SEC:
            raise RuntimeError(f"ÉCHEC : fichier de {dur/3600:.2f} h > 3 h")
        meta = {"kind": "file", "src": os.path.abspath(src), "title": os.path.basename(src), "channel": None,
                "duration": dur, "audio": os.path.abspath(src)}
    sh(["ffmpeg", "-y", "-v", "error", "-i", meta["audio"], "-vn", "-ac", "1", "-ar", "16000", wav])
    meta["duration"] = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav]).stdout.strip())
    jsave(os.path.join(run, "source.json"), meta)
    return meta


def transcribe(run, meta, lang="fr"):
    out = os.path.join(run, "words.json")
    if os.path.exists(out):
        return jload(out)
    from faster_whisper import WhisperModel
    model = WhisperModel(MODEL, device="cpu", compute_type="int8", download_root=MODELS_DIR,
                         cpu_threads=int(os.environ.get("CLIP_THREADS", "4")))
    cdir = os.path.join(run, "chunks"); os.makedirs(cdir, exist_ok=True)
    dur, words, n = meta["duration"], [], int(meta["duration"] // CHUNK) + 1
    for i in range(n):
        cj = os.path.join(cdir, f"{i:03d}.json")
        if not os.path.exists(cj):
            cw = os.path.join(cdir, f"{i:03d}.wav")
            sh(["ffmpeg", "-y", "-v", "error", "-ss", str(i * CHUNK), "-t", str(CHUNK), "-i",
                os.path.join(run, "audio.wav"), cw])
            cdur = min(CHUNK, dur - i * CHUNK)
            ws = []
            for beam in (1, 5):  # garde-fou : < 60 mots/min sur un chunk parlé = transcription trouée -> 2e passe beam 5
                segs, _ = model.transcribe(cw, language=lang, beam_size=beam, word_timestamps=True, vad_filter=True,
                                           condition_on_previous_text=False)
                w2 = [{"w": w.word.strip(), "s": round(w.start + i * CHUNK, 3), "e": round(w.end + i * CHUNK, 3)}
                      for s in segs for w in (s.words or []) if w.word.strip()]
                if len(w2) > len(ws): ws = w2
                if len(ws) >= 60 * cdur / 60 or cdur < 60: break
            jsave(cj, ws)
            os.remove(cw)
        words += jload(cj)
        progress(run, "transcription", 5 + int(45 * (i + 1) / n), f"chunk {i+1}/{n}")
    if not words:
        raise RuntimeError("ÉCHEC : aucun mot transcrit")
    jsave(out, words)
    with open(os.path.join(run, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(" ".join(w["w"] for w in words))
    return words


def silences(run):
    out = os.path.join(run, "silences.json")
    if os.path.exists(out):
        return jload(out)
    r = sh(["ffmpeg", "-v", "info", "-i", os.path.join(run, "audio.wav"), "-af",
            "silencedetect=noise=-32dB:d=0.25", "-f", "null", "-"])
    st, res = None, []
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m: st = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and st is not None:
            res.append([st, float(m.group(1))]); st = None
    jsave(out, res)
    return res


def run_agent(run, src):
    with timed(run, "ingestion"):
        progress(run, "ingestion", 2, src)
        meta = ingest(run, src)
    with timed(run, "transcription"):
        words = transcribe(run, meta)
    with timed(run, "silencedetect"):
        sil = silences(run)
    return meta, words, sil
