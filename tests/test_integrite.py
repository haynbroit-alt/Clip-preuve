"""Manifeste d'intégrité : empreintes des fichiers, des prompts, du code, et de la carte elle-même."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from agents import integrite

ROOT = Path(__file__).resolve().parents[1]
VALIDATEUR = Draft202012Validator(json.loads((ROOT / "schemas" / "preuve.schema.json").read_text(encoding="utf-8")))


def _run(tmp_path):
    (tmp_path / "audio.wav").write_bytes(b"RIFF-audio")
    (tmp_path / "words.json").write_text('[{"w": "bonjour", "s": 0, "e": 0.4}]', encoding="utf-8")
    (tmp_path / "clip.mp4").write_bytes(b"video-livree")
    card = json.loads((ROOT / "tests" / "golden" / "preuve.json").read_text(encoding="utf-8"))
    (tmp_path / "preuve.json").write_text(json.dumps(card), encoding="utf-8")
    (tmp_path / "preuve.md").write_text("# Carte de preuve\n", encoding="utf-8")
    return card


def test_scellement_puis_verification_sans_ecart(tmp_path):
    card = integrite.sceller(str(tmp_path), _run(tmp_path))
    f = card["integrite"]["fichiers"]
    assert f["clip"] == integrite.sha256_fichier(str(tmp_path / "clip.mp4"))
    assert f["prompt_falsificateur"] == integrite.sha256_fichier(str(ROOT / "skills" / "falsificateur.md"))
    assert set(f) == {"audio", "transcription", "clip", "prompt_juge", "prompt_falsificateur"}
    assert len(card["integrite"]["code"]["commit"]) == 40  # les tests tournent dans le dépôt git
    assert integrite.verifier(str(tmp_path)) == []
    assert integrite.main([str(tmp_path)]) == 0
    assert list(VALIDATEUR.iter_errors(card)) == []
    md = (tmp_path / "preuve.md").read_text(encoding="utf-8")
    assert f"sha256:{card['integrite']['empreinte_carte']}" in md


def test_clip_remplace_apres_coup_est_detecte(tmp_path, capsys):
    integrite.sceller(str(tmp_path), _run(tmp_path))
    (tmp_path / "clip.mp4").write_bytes(b"autre-video")
    ecarts = integrite.verifier(str(tmp_path))
    assert len(ecarts) == 1 and ecarts[0].startswith("clip :")
    assert integrite.main([str(tmp_path)]) == 1
    assert "ÉCART" in capsys.readouterr().out


def test_citation_reecrite_a_la_main_est_detectee(tmp_path):
    integrite.sceller(str(tmp_path), _run(tmp_path))
    carte = json.loads((tmp_path / "preuve.json").read_text(encoding="utf-8"))
    assert carte["citation_debut"] != "Cette méthode permet de gagner 500 € par jour"
    carte["citation_debut"] = "Cette méthode permet de gagner 500 € par jour"  # citation inventée glissée à la main
    (tmp_path / "preuve.json").write_text(json.dumps(carte), encoding="utf-8")
    assert integrite.verifier(str(tmp_path)) == ["la carte a été modifiée après scellement"]


def test_transcription_ou_prompt_modifie_est_detecte(tmp_path, monkeypatch):
    integrite.sceller(str(tmp_path), _run(tmp_path))
    (tmp_path / "words.json").write_text("[]", encoding="utf-8")
    assert any(e.startswith("transcription :") for e in integrite.verifier(str(tmp_path)))


def test_fichier_absent_est_note_null_et_reste_coherent(tmp_path):
    card = _run(tmp_path)
    (tmp_path / "audio.wav").unlink()
    card = integrite.sceller(str(tmp_path), card)
    assert card["integrite"]["fichiers"]["audio"] is None
    assert integrite.verifier(str(tmp_path)) == []
    assert list(VALIDATEUR.iter_errors(card)) == []


def test_empreinte_carte_ignore_l_ordre_des_cles():
    a = {"b": 1, "a": {"y": 2, "x": 3}, "integrite": {"empreinte_carte": "z"}}
    b = {"a": {"x": 3, "y": 2}, "integrite": {"empreinte_carte": "autre"}, "b": 1}
    assert integrite.empreinte_carte(a) == integrite.empreinte_carte(b)


def test_carte_non_scellee_et_usage(tmp_path, capsys):
    assert integrite.verifier(str(tmp_path)) == ["carte absente ou non scellée"]
    assert integrite.main([]) == 2
    assert "usage" in capsys.readouterr().out


def test_hors_depot_git_le_commit_est_inconnu(tmp_path, monkeypatch):
    monkeypatch.setattr(integrite, "ROOT", str(tmp_path))
    assert integrite.version_code() == {"commit": None, "modifie": None}
