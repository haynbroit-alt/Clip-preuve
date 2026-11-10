"""L'orchestrateur enchaîne les agents et conserve l'erreur. Tout est simulé."""

import json
import os

import pytest

import orchestrator

FINAL = {
    "hors_contexte": {"verdict": "PROUVÉ", "preuve": "ok", "source": "LLM"},
    "info_prealable": {"verdict": "PROUVÉ", "preuve": "ok", "source": "LLM"},
    "contredit_apres": {"verdict": "PROUVÉ", "preuve": "ok", "source": "LLM"},
    "coupe_mi_idee": {"verdict": "PROUVÉ", "preuve": "ok", "source": "LLM"},
}


def _monde():
    meta = {"title": "T", "channel": "C", "src": "https://example.com/v", "duration": 3600}
    words = [{"w": "Bonjour", "s": 1.5, "e": 2.0}, {"w": "tout", "s": 27.0, "e": 27.4}]
    sents = [{"s": 0, "e": 30, "text": "Bonjour tout.", "q": False}]
    cand = {
        "id": "c1",
        "i": 0,
        "j": 0,
        "s": 0.0,
        "e": 30.0,
        "score": 8.0,
        "pre": 1.0,
        "juge": {
            "raison": "accroche claire",
            "phrase_cle": "Bonjour",
            "accroche_3s": 6,
            "autonomie": 6,
            "payoff": 6,
            "densite": 6,
            "citabilite": 6,
        },
    }
    verdict = {
        "s": 1.5,
        "e": 28.0,
        "i": 0,
        "j": 0,
        "final": FINAL,
        "statut": "PROUVÉ",
        "avertissement": None,
        "iteration": 1,
    }
    return meta, words, sents, cand, verdict


def test_bornes_du_falsificateur_vont_au_monteur_puis_a_la_carte(tmp_path, monkeypatch):
    meta, words, sents, cand, verdict = _monde()
    seen = {}

    monkeypatch.setattr(orchestrator.transcripteur, "run_agent", lambda run, src, align="whisper": (meta, words, []))

    def chercheur(run, words, sil, top=6, exclude=()):
        seen["exclude"] = list(exclude)
        return sents, [cand]

    monkeypatch.setattr(orchestrator.chercheur, "run_agent", chercheur)
    monkeypatch.setattr(orchestrator.juge, "run_agent", lambda run, words, cands: [cand])
    monkeypatch.setattr(
        orchestrator.falsificateur, "run_agent", lambda run, sents, ranked, max_it=3: (verdict, cand, [verdict])
    )

    def monteur(run, meta, words, s, e, name="clip.mp4"):
        seen["monteur"] = (s, e, name)
        return os.path.join(run, name), {"methode": "centre (test)"}

    monkeypatch.setattr(orchestrator.monteur, "run_agent", monteur)
    run = tmp_path / "run"
    _path, card = orchestrator.main("https://example.com/v", str(run))
    assert seen["monteur"] == (1.5, 28.0, "clip.mp4")
    assert seen["exclude"] == []
    assert card["statut"] == "PROUVÉ"
    assert card["clip"]["debut_s"] == 1.5
    assert card["clip"]["fin_s"] == 28.0
    assert card["citation_debut"] == "Bonjour tout"

    def monteur2(run, meta, words, s, e, name="clip.mp4"):
        seen["monteur2"] = name
        return os.path.join(run, name), {"methode": "centre (test)"}

    monkeypatch.setattr(orchestrator.monteur, "run_agent", monteur2)
    orchestrator.main("https://example.com/v", str(run), regen=True)
    assert seen["exclude"] == [(1.5, 28.0)]
    assert seen["monteur2"] == "clip_2.mp4"
    assert json.loads((run / "preuve.json").read_text(encoding="utf-8"))["clip"]["fichier"] == "clip_2.mp4"


def test_conflit_n_appelle_pas_le_monteur(tmp_path, monkeypatch):
    meta, words, sents, cand, verdict = _monde()
    verdict = {
        **verdict,
        "statut": "INCONNU",
        "final": {**FINAL, "contredit_apres": {"verdict": "CONFLIT", "preuve": "corrigé", "source": "garde-fou"}},
    }
    monkeypatch.setattr(orchestrator.transcripteur, "run_agent", lambda run, src, align="whisper": (meta, words, []))
    monkeypatch.setattr(orchestrator.chercheur, "run_agent", lambda *a, **k: (sents, [cand]))
    monkeypatch.setattr(orchestrator.juge, "run_agent", lambda *a, **k: [cand])
    monkeypatch.setattr(orchestrator.falsificateur, "run_agent", lambda *a, **k: (verdict, cand, [verdict]))
    appels = {"n": 0}

    def monteur(*a, **k):
        appels["n"] += 1
        raise AssertionError("le monteur ne doit pas tourner")

    monkeypatch.setattr(orchestrator.monteur, "run_agent", monteur)
    with pytest.raises(RuntimeError, match="CONFLIT"):
        orchestrator.main("https://example.com/v", str(tmp_path / "run"))
    assert appels["n"] == 0
    assert not (tmp_path / "run" / "clip.mp4").exists()


def test_candidat_suivant_non_certifie(tmp_path, monkeypatch):
    meta, words, sents, cand, verdict = _monde()
    autre = {
        **cand,
        "id": "c2",
        "s": 40.0,
        "e": 70.0,
        "juge": {**cand["juge"], "raison": "second"},
    }
    monkeypatch.setattr(orchestrator.transcripteur, "run_agent", lambda run, src, align="whisper": (meta, words, []))
    monkeypatch.setattr(orchestrator.chercheur, "run_agent", lambda *a, **k: (sents, [cand, autre]))
    monkeypatch.setattr(orchestrator.juge, "run_agent", lambda *a, **k: [cand, autre])
    monkeypatch.setattr(orchestrator.falsificateur, "run_agent", lambda *a, **k: (verdict, cand, [verdict]))
    monkeypatch.setattr(
        orchestrator.falsificateur,
        "falsify",
        lambda *a, **k: {"final": dict(FINAL), "s": 40.0, "e": 55.0, "i": 0, "j": 0},
    )

    def monteur(run, meta, words, s, e, name="clip.mp4"):
        return os.path.join(run, name), {"methode": "centre (test)"}

    monkeypatch.setattr(orchestrator.monteur, "run_agent", monteur)
    run = tmp_path / "run"
    _path, card = orchestrator.main("https://example.com/v", str(run), candidats=1)
    assert card["certifie"] is True
    extra = json.loads((run / "preuve_c2.json").read_text(encoding="utf-8"))
    assert extra["certifie"] is False
    assert extra["candidat"] == "c2"
    assert "00:00:40:00" in (run / "clip.edl").read_text(encoding="utf-8")
    assert "fcpxml" in (run / "clip.fcpxml").read_text(encoding="utf-8")
    assert json.loads((run / "preuve.json").read_text(encoding="utf-8"))["certifie"] is True


def test_echec_ecrit_dans_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(
        orchestrator.transcripteur,
        "run_agent",
        lambda run, src, align="whisper": (_ for _ in ()).throw(RuntimeError("boom sélection")),
    )
    run = tmp_path / "run"
    with pytest.raises(RuntimeError, match="boom sélection"):
        orchestrator.main("https://example.com/v", str(run))
    progress = json.loads((run / "progress.json").read_text(encoding="utf-8"))
    assert progress["step"] == "ÉCHEC"
    assert "boom sélection" in progress["msg"]
    assert (run / "src.txt").read_text(encoding="utf-8") == "https://example.com/v"
