"""Même octets, même dossier. Une transcription déjà écrite est reprise."""

from agents import reprise


def test_empreinte_stable_et_dossier_partage(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "sous" / "b.wav"
    b.parent.mkdir()
    a.write_bytes(b"RIFF-audio-identique")
    b.write_bytes(b"RIFF-audio-identique")
    assert reprise.empreinte(str(a)) == reprise.empreinte(str(b))
    runs = tmp_path / "runs"
    un = reprise.dossier_pour(str(runs), str(a))
    deux = reprise.dossier_pour(str(runs), str(b))
    assert un == deux
    reprise.noter(un, "transcription", reprise.empreinte(str(a)))
    reprise.noter(un, "transcription")
    assert reprise.lire(un)["etapes"] == ["transcription"]
    (runs / reprise.empreinte(str(a)) / "words.json").write_text("[]", encoding="utf-8")
    assert reprise.transcription_en_cache(un)


def test_reprise_illisible_repart_de_zero(tmp_path):
    run = tmp_path / "runs" / "x"
    run.mkdir(parents=True)
    (run / "reprise.json").write_text("[]", encoding="utf-8")
    assert reprise.lire(str(run))["etapes"] == []


def test_url_a_un_dossier_stable(tmp_path):
    runs = tmp_path / "runs"
    url = "https://example.com/watch?v=abc"
    assert reprise.dossier_pour(str(runs), url) == reprise.dossier_pour(str(runs), url)
