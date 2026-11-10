"""Sans clip manuel, la comparaison reste INCONNU. Pas d'appel ffmpeg."""

import json

import compare


def test_sans_reference_le_verdict_est_inconnu(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    card = {
        "clip": {
            "fichier": "clip.mp4",
            "debut": "00:00:01.000",
            "fin": "00:00:20.000",
            "debut_s": 1,
            "fin_s": 20,
        },
        "statut": "PROUVÉ",
    }
    (run / "preuve.json").write_text(json.dumps(card), encoding="utf-8")
    res = compare.main([str(run)])
    assert res["verdict"] == "INCONNU"
    assert "impossible" in res["raison"]
    saved = json.loads((run / "compare.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "INCONNU"


def test_conversion_horodatage():
    assert compare.sec("00:01:30") == 90
    assert compare.sec("1:00:00") == 3600
