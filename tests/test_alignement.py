"""Sans whisperx, l'alignement demandé rend les timestamps faster-whisper."""

from agents.alignement import aligner


def test_mode_whisper_ne_change_rien():
    mots = [{"w": "bonjour", "s": 0.0, "e": 0.4}]
    assert aligner(mots, "audio.wav", mode="whisper") is mots


def test_whisperx_aligne_puis_replie_si_erreur(monkeypatch):
    import sys
    import types

    wx = types.ModuleType("whisperx")
    wx.load_audio = lambda path: [0.0]
    wx.load_align_model = lambda language_code, device: ("modele", {})

    def align(segments, model, meta, audio, device, return_char_alignments=False):
        return {"segments": [{"words": [{"word": " salut ", "start": 0.1, "end": 0.4}]}]}

    wx.align = align
    monkeypatch.setitem(sys.modules, "whisperx", wx)
    mots = aligner([{"w": "bonjour", "s": 0.0, "e": 1.0}], "audio.wav", mode="whisperx")
    assert mots == [{"w": "salut", "s": 0.1, "e": 0.4}]

    def boom(path):
        raise RuntimeError("modèle indisponible")

    wx.load_audio = boom
    assert aligner([{"w": "bonjour", "s": 0.0, "e": 1.0}], "audio.wav", mode="whisperx")[0]["w"] == "bonjour"


def test_whisperx_absent_replie(capsys, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "whisperx", None)
    mots = [{"w": "bonjour", "s": 0.0, "e": 0.4}]
    assert aligner(mots, "audio.wav", mode="whisperx") == mots
    assert "whisperx absent" in capsys.readouterr().err
