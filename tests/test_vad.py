"""VAD qui efface la parole : on reprend les mots obtenus sans filtre."""

import json
import sys

from agents.vad import choisir_mots, vad_ecrase
from tests.test_transcripteur import _faux_whisper, _Ret


def test_zero_segment_ou_parole_effacee():
    assert vad_ecrase(10.0, [], 0) is True
    assert vad_ecrase(10.0, [{"s": 0.0, "e": 1.0}], 1) is True  # 10 % < 20 %
    assert vad_ecrase(10.0, [{"s": 0.0, "e": 3.0}], 1) is False
    mots, retry = choisir_mots(10.0, [], 0, [{"w": "voix", "s": 0.0, "e": 4.0}])
    assert retry is True
    assert mots[0]["w"] == "voix"
    garde, retry = choisir_mots(10.0, [{"w": "ok", "s": 0.0, "e": 5.0}], 2, [])
    assert retry is False
    assert garde[0]["w"] == "ok"
    garde, retry = choisir_mots(10.0, [{"w": "a", "s": 0.0, "e": 1.0}], 0, [])
    assert retry is True and garde[0]["w"] == "a"


def test_transcription_retente_sans_vad(tmp_path, monkeypatch, capsys):
    from agents import transcripteur

    mod, beams = _faux_whisper([[], [(" voix", 0.2, 0.8)]])
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)

    def fake_sh(cmd, **kw):
        if cmd and cmd[0] == "ffmpeg":
            with open(cmd[-1], "wb") as handle:
                handle.write(b"")
        return _Ret()

    monkeypatch.setattr(transcripteur, "sh", fake_sh)
    mots = transcripteur.transcribe(str(tmp_path), {"duration": 10.0})
    assert mots == [{"w": "voix", "s": 0.2, "e": 0.8}]
    assert [b["beam"] for b in beams if "beam" in b] == [1, 1]
    assert "VAD retiré" in capsys.readouterr().err
    assert json.loads((tmp_path / "words.json").read_text(encoding="utf-8"))[0]["w"] == "voix"
