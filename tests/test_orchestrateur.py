"""L'orchestrateur enchaîne les agents et conserve l'erreur. Tout est simulé."""

import json
import os

import pytest

import orchestrator
from agents import integrite

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
    # carte certifiée et candidat scellés : rien n'a bougé depuis le scellement
    assert integrite.verifier(str(run)) == []
    assert integrite.verifier(str(run), "preuve_c2") == []


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


def _brancher(monkeypatch, verdicts):
    meta, words, sents, cand, _ = _monde()
    suite = iter(verdicts)
    monkeypatch.setattr(orchestrator.transcripteur, "run_agent", lambda run, src, align="whisper": (meta, words, []))
    monkeypatch.setattr(orchestrator.chercheur, "run_agent", lambda run, w, sil, top=6, exclude=(): (sents, [cand]))
    monkeypatch.setattr(orchestrator.juge, "run_agent", lambda run, w, cands: [cand])

    def falsif(run, sents, ranked, max_it=3):
        v = next(suite)
        return v, cand, [v]

    monkeypatch.setattr(orchestrator.falsificateur, "run_agent", falsif)
    monkeypatch.setattr(
        orchestrator.monteur,
        "run_agent",
        lambda run, meta, words, s, e, name="clip.mp4": (os.path.join(run, name), {"methode": "test"}),
    )


def test_regenerer_conserve_chaque_carte(tmp_path, monkeypatch):
    """Régression : la régénération écrasait la carte 1 et faisait disparaître preuve.md."""
    _, _, _, _, verdict = _monde()
    bornes = [(1.5, 28.0), (2.0, 27.0), (3.0, 26.0)]
    _brancher(monkeypatch, [dict(verdict, s=s, e=e) for s, e in bornes])
    run = tmp_path / "run"
    orchestrator.main("https://example.com/v", str(run))
    carte1_json = (run / "preuve.json").read_bytes()
    carte1_md = (run / "preuve.md").read_bytes()
    orchestrator.main("https://example.com/v", str(run), regen=True)
    carte2_json = (run / "preuve.json").read_bytes()
    orchestrator.main("https://example.com/v", str(run), regen=True)

    def carte(nom):
        return json.loads((run / nom).read_text(encoding="utf-8"))

    # chaque clip garde sa carte, octet pour octet
    assert (run / "preuve_1.json").read_bytes() == carte1_json
    assert (run / "preuve_1.md").read_bytes() == carte1_md
    assert (run / "preuve_2.json").read_bytes() == carte2_json
    for n, (s, e) in enumerate(bornes, start=1):
        c = carte(f"preuve_{n}.json")
        assert c["clip"]["fichier"] == ("clip.mp4" if n == 1 else f"clip_{n}.mp4")
        assert (c["clip"]["debut_s"], c["clip"]["fin_s"]) == (s, e)
        assert (run / f"preuve_{n}.md").exists()
    # preuve.json / preuve.md = la dernière carte (ce que lit l'interface et ce qu'affiche la CLI)
    assert carte("preuve.json") == carte("preuve_3.json")
    assert (run / "preuve.md").read_bytes() == (run / "preuve_3.md").read_bytes()
    # les cartes archivées restent vérifiables après les régénérations
    for nom in ("preuve", "preuve_1", "preuve_2", "preuve_3"):
        assert integrite.verifier(str(run), nom) == [], nom


def test_archivage_ne_reecrit_jamais_une_copie_existante(tmp_path):
    run = tmp_path
    (run / "preuve.json").write_text(json.dumps({"clip": {"fichier": "clip_2.mp4"}}), encoding="utf-8")
    (run / "preuve.md").write_text("nouvelle", encoding="utf-8")
    (run / "preuve_2.md").write_text("ancienne", encoding="utf-8")
    orchestrator.archiver_derniere_carte(str(run))
    assert (run / "preuve_2.md").read_text(encoding="utf-8") == "ancienne"
    assert (run / "preuve_2.json").exists()
    assert orchestrator.numero_clip("clip.mp4") == 1
    assert orchestrator.numero_clip("clip_12.mp4") == 12
    assert orchestrator.numero_clip("autre.mp4") is None
    orchestrator.archiver_derniere_carte(str(tmp_path / "vide"))  # pas de carte : rien à faire
