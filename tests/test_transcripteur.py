"""Transcription simulée : pas de téléchargement Whisper, refus au-delà de 3 h, silences."""

import json
import sys
import types

import pytest

from agents import transcripteur


class _Ret:
    def __init__(self, stdout="", stderr=""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = 0


def _faux_whisper(beams_out):
    """beams_out : liste de listes de (mot, début, fin), une par appel transcribe."""
    beams = []

    class Word:
        def __init__(self, word, start, end):
            self.word = word
            self.start = start
            self.end = end

    class Seg:
        def __init__(self, words):
            self.words = words

    class Model:
        def __init__(self, model, device, compute_type, download_root, cpu_threads):
            beams.append(
                {
                    "model": model,
                    "device": device,
                    "compute_type": compute_type,
                    "download_root": download_root,
                    "cpu_threads": cpu_threads,
                }
            )

        def transcribe(self, path, **kw):
            lot = beams_out[len([b for b in beams if "beam" in b])]
            # compte les appels transcribe séparément
            beams.append({"beam": kw["beam_size"]})
            words = [Word(w, s, e) for w, s, e in lot]
            return [Seg(words)], None

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = Model
    return mod, beams


def test_transcrit_avec_whisper_simule_et_repasse_en_beam_5(tmp_path, monkeypatch):
    mod, beams = _faux_whisper([[], [(" bonjour", 1.0, 1.4)]])
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)

    def fake_sh(cmd, **kw):
        if cmd[0] == "ffmpeg":
            with open(cmd[-1], "wb") as fh:
                fh.write(b"")
            return _Ret()
        raise AssertionError(cmd)

    monkeypatch.setattr(transcripteur, "sh", fake_sh)
    words = transcripteur.transcribe(str(tmp_path), {"duration": 120.0})
    assert words == [{"w": "bonjour", "s": 1.0, "e": 1.4}]
    assert [b["beam"] for b in beams if "beam" in b] == [1, 5]
    init = next(b for b in beams if "model" in b)
    assert init["model"] == "small"
    assert init["device"] == "cpu"
    assert init["compute_type"] == "int8"
    assert (tmp_path / "transcript.txt").read_text(encoding="utf-8") == "bonjour"
    assert not list((tmp_path / "chunks").glob("*.wav"))

    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert transcripteur.transcribe(str(tmp_path), {"duration": 120.0}) == words


def test_cache_words_json_ne_charge_pas_whisper(tmp_path, monkeypatch):
    attendu = [{"w": "salut", "s": 0.0, "e": 0.4}]
    (tmp_path / "words.json").write_text(json.dumps(attendu), encoding="utf-8")
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert transcripteur.transcribe(str(tmp_path), {"duration": 30}) == attendu


def test_aucun_mot_est_un_echec(tmp_path, monkeypatch):
    # 2e lot : la passe sans VAD (garde-fou) ne trouve rien non plus
    mod, beams = _faux_whisper([[], []])
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)

    def fake_sh(cmd, **kw):
        if cmd and cmd[0] == "ffmpeg":
            with open(cmd[-1], "wb") as fh:
                fh.write(b"")
        return _Ret()

    monkeypatch.setattr(transcripteur, "sh", fake_sh)
    with pytest.raises(RuntimeError, match="aucun mot"):
        transcripteur.transcribe(str(tmp_path), {"duration": 10.0})
    assert len([b for b in beams if "beam" in b]) == 2


def test_lien_ou_fichier_au_dela_de_3h_refuse(tmp_path, monkeypatch):
    vus = []

    def fake_sh(cmd, **kw):
        vus.append(cmd)
        if "-J" in cmd:
            return _Ret(stdout=json.dumps({"duration": 3 * 3600 + 301, "title": "long", "channel": "c"}))
        return _Ret(stdout=f"{3 * 3600 + 301}\n")

    monkeypatch.setattr(transcripteur, "sh", fake_sh)
    with pytest.raises(RuntimeError, match="3 h"):
        transcripteur.ingest(str(tmp_path), "https://example.com/watch?v=abc")
    assert len(vus) == 1
    assert "-J" in vus[0]

    with pytest.raises(RuntimeError, match="introuvable"):
        transcripteur.ingest(str(tmp_path), str(tmp_path / "absent.mp4"))

    src = tmp_path / "long.mp4"
    src.write_bytes(b"pas-une-video")
    with pytest.raises(RuntimeError, match="3 h"):
        transcripteur.ingest(str(tmp_path / "fichier"), str(src))


def test_silences_parses_puis_reutilises(tmp_path, monkeypatch):
    stderr = "silence_start: 1.25\nsilence_end: 1.80\nbruit\nsilence_start: 8.0\n"
    monkeypatch.setattr(transcripteur, "sh", lambda cmd, **kw: _Ret(stderr=stderr))
    assert transcripteur.silences(str(tmp_path)) == [[1.25, 1.8]]
    monkeypatch.setattr(transcripteur, "sh", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ffmpeg")))
    assert transcripteur.silences(str(tmp_path)) == [[1.25, 1.8]]


def _seg_whisper(mots, no_speech, logprob):
    class Word:
        def __init__(self, word, start, end):
            self.word, self.start, self.end = word, start, end

    class Seg:
        pass

    seg = Seg()
    seg.words = [Word(w, a, b) for w, a, b in mots]
    seg.no_speech_prob = no_speech
    seg.avg_logprob = logprob
    return seg


def test_vad_qui_efface_tout_declenche_une_passe_sans_vad_filtree(tmp_path, monkeypatch):
    """Régression (AI-Youtube-Shorts-Generator n°56) : musique sur la voix -> VAD efface tout -> ÉCHEC."""
    appels = []
    sur = _seg_whisper([(" bonjour", 1.0, 1.4), (" à", 1.5, 1.6), (" tous", 1.7, 2.0)], 0.1, -0.3)
    halluciné = _seg_whisper([(" Sous-titres", 5.0, 5.5), (" réalisés", 5.6, 6.0)], 0.9, -0.2)
    incertain = _seg_whisper([(" blabla", 8.0, 8.4)], 0.2, -1.6)

    class Model:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, path, **kw):
            appels.append((kw["beam_size"], kw["vad_filter"]))
            if kw["vad_filter"]:
                return [], None
            return [sur, halluciné, incertain], None

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = Model
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)

    def fake_sh(cmd, **kw):
        if cmd and cmd[0] == "ffmpeg":
            with open(cmd[-1], "wb") as fh:
                fh.write(b"")
        return _Ret()

    monkeypatch.setattr(transcripteur, "sh", fake_sh)
    words = transcripteur.transcribe(str(tmp_path), {"duration": 120.0})
    assert appels == [(1, True), (5, True), (5, False)]
    assert [w["w"] for w in words] == ["bonjour", "à", "tous"]  # ni hallucination ni segment incertain
    relances = json.loads((tmp_path / "vad_relances.json").read_text(encoding="utf-8"))
    assert relances == [{"chunk": 0, "debut_s": 0, "mots": 3}]


def test_pas_de_passe_sans_vad_quand_la_parole_est_trouvee(tmp_path, monkeypatch):
    mod, beams = _faux_whisper([[(" salut", 0.5, 0.9)]])
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)

    def fake_sh(cmd, **kw):
        if cmd and cmd[0] == "ffmpeg":
            with open(cmd[-1], "wb") as fh:
                fh.write(b"")
        return _Ret()

    monkeypatch.setattr(transcripteur, "sh", fake_sh)
    assert transcripteur.transcribe(str(tmp_path), {"duration": 10.0}) == [{"w": "salut", "s": 0.5, "e": 0.9}]
    assert len([b for b in beams if "beam" in b]) == 1
    assert not (tmp_path / "vad_relances.json").exists()


def test_segment_sur_exige_les_deux_indicateurs():
    assert transcripteur.segment_sur(_seg_whisper([], 0.1, -0.5))
    assert not transcripteur.segment_sur(_seg_whisper([], 0.7, -0.5))
    assert not transcripteur.segment_sur(_seg_whisper([], 0.1, -1.5))
    assert not transcripteur.segment_sur(object())  # indicateurs absents : refusé
