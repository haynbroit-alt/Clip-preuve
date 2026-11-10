"""Branches pures : coût, journal, contrats, commandes, nom du modèle local."""

import io
import json

import pytest

from agents import common, llm
from agents.contracts import CritereLLM, NotesJuge, SortieFalsificateur, normaliser_critere
from agents.falsificateur import adjust


def test_normaliser_equivaut_a_l_ancien_critere():
    legacy_ok = normaliser_critere({"verdict": "PROUVÉ", "preuve": "texte"})
    assert legacy_ok == {"verdict": "PROUVÉ", "preuve": "texte"}
    assert normaliser_critere({"verdict": "PEUT-ETRE", "preuve": 12})["verdict"] == "INCONNU"
    assert normaliser_critere({"verdict": "PEUT-ETRE", "preuve": 12})["preuve"] == 12
    assert normaliser_critere({"verdict": 1, "preuve": "brut"}) == {"verdict": "INCONNU", "preuve": "brut"}
    assert normaliser_critere("pas un objet") == {"verdict": "INCONNU", "preuve": "réponse absente"}
    assert normaliser_critere({})["verdict"] == "INCONNU"


def test_sortie_falsificateur_stricte():
    SortieFalsificateur.model_validate(
        {
            "affirmation_du_clip": "x",
            "correction_apres": "aucune",
            "suite_necessaire": "aucune",
            "hors_contexte": {"verdict": "PROUVÉ", "preuve": "ok"},
            "info_prealable": {"verdict": "INCONNU", "preuve": ""},
        }
    )
    with pytest.raises(ValueError):
        SortieFalsificateur.model_validate({"champ_inconnu": 1})
    with pytest.raises(ValueError):
        CritereLLM.model_validate({"verdict": 1, "preuve": "x"})


def test_note_illisible():
    with pytest.raises(ValueError):
        NotesJuge.model_validate({"accroche_3s": "non"})


def test_commande_en_echec_et_outils(tmp_path, monkeypatch):
    def faux_run(cmd, capture_output, text, **kw):
        class R:
            returncode = 1
            stderr = "panne ffmpeg"
            stdout = ""

        return R()

    monkeypatch.setattr(common.subprocess, "run", faux_run)
    with pytest.raises(RuntimeError, match="panne ffmpeg"):
        common.sh(["ffmpeg", "-version"])

    def ok_run(cmd, capture_output, text, **kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = "ok"

        return R()

    monkeypatch.setattr(common.subprocess, "run", ok_run)
    assert common.sh(["ffmpeg", "-version"]).stdout == "ok"

    monkeypatch.setattr(common, "VENV_BIN", str(tmp_path))
    (tmp_path / "yt-dlp").write_text("", encoding="utf-8")
    assert common.tool("yt-dlp") == str(tmp_path / "yt-dlp")
    assert common.tool("absent-outil") == "absent-outil"
    monkeypatch.setattr(common.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    assert common.ytdlp()[-2:] == ["--js-runtimes", "node"]
    monkeypatch.setattr(common.shutil, "which", lambda name: None)
    assert "--js-runtimes" not in common.ytdlp()
    assert common.hms(-3) == "00:00:00.000"


def test_minuterie_conserve_la_premiere_mesure_courte(tmp_path, monkeypatch):
    valeurs = iter([0.0, 0.01, 5.0, 5.05, 10.0, 12.0])
    monkeypatch.setattr(common.time, "monotonic", lambda: next(valeurs))
    with common.timed(str(tmp_path), "etape"):
        pass
    with common.timed(str(tmp_path), "etape"):
        pass
    assert json.loads((tmp_path / "timings.json").read_text(encoding="utf-8"))["etape"] == 0.01
    with common.timed(str(tmp_path), "etape"):
        pass
    assert json.loads((tmp_path / "timings.json").read_text(encoding="utf-8"))["etape"] == 2.0


def test_backend_local_lit_le_modele_puis_inconnu(monkeypatch):
    monkeypatch.setattr(llm, "OR_KEY", None)
    monkeypatch.setattr(llm, "_LOCAL_NAME", None)

    def ouvrir(url, timeout=5):
        return io.BytesIO(json.dumps({"data": [{"id": "/models/Qwen-test.gguf"}]}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", ouvrir)
    assert llm.backend() == ("local-llama.cpp", "Qwen-test.gguf")
    monkeypatch.setattr(llm, "_LOCAL_NAME", None)

    def panne(url, timeout=5):
        raise TimeoutError("eteint")

    monkeypatch.setattr(llm.urllib.request, "urlopen", panne)
    assert llm.backend() == ("local-llama.cpp", "inconnu")


def test_progress_ecrit_un_journal_json(tmp_path, capsys):
    common.progress(str(tmp_path), "juge", 12, "candidat")
    capture = capsys.readouterr()
    assert "[ 12%] juge candidat" in capture.out
    ligne = capture.err.strip().splitlines()[-1]
    payload = json.loads(ligne)
    assert payload["msg"] == "progress"
    assert payload["step"] == "juge"
    assert payload["pct"] == 12
    assert payload["detail"] == "candidat"
    assert "sk-" not in capture.err


def test_cout_sans_duree_de_source(tmp_path, monkeypatch):
    from agents import greffier

    monkeypatch.setattr(greffier, "backend", lambda: ("local-llama.cpp", "mock.gguf"))
    cout = greffier.costs(str(tmp_path), 0)
    assert cout["cout_eur_par_heure"] == 0
    assert cout["objectif_0_10_eur_h"] == "PROUVÉ"


def test_adjust_bornes_historiques():
    sents = [{"s": i * 10.0, "e": i * 10.0 + 8.0, "text": "Phrase autonome et complète."} for i in range(8)]
    base = {
        "contredit_apres": {"verdict": "PROUVÉ"},
        "coupe_mi_idee": {"verdict": "PROUVÉ"},
        "hors_contexte": {"verdict": "PROUVÉ"},
        "info_prealable": {"verdict": "PROUVÉ"},
    }
    suite = dict(base, contredit_apres={"verdict": "CONFLIT"})
    assert adjust(
        sents,
        {
            "i": 0,
            "j": 1,
            "final": suite,
            "k_correction": None,
            "k_suite": None,
            "garde_fou": {},
            "after": [2, 3],
        },
    ) == (0, 2)
    assert (
        adjust(
            sents,
            {
                "i": 0,
                "j": 1,
                "final": suite,
                "k_correction": None,
                "k_suite": None,
                "garde_fou": {},
                "after": [],
            },
        )
        is None
    )
    court = [{"s": 0.0, "e": 5.0, "text": "Trop court."}]
    assert (
        adjust(
            court,
            {
                "i": 0,
                "j": 0,
                "final": suite,
                "k_correction": 0,
                "k_suite": None,
                "garde_fou": {},
                "after": [0],
            },
        )
        is None
    )
    arriere = dict(base, hors_contexte={"verdict": "CONFLIT"})
    assert adjust(
        sents,
        {"i": 2, "j": 3, "final": arriere, "garde_fou": {}, "after": [], "k_correction": None, "k_suite": None},
    ) == (1, 3)
    serres = [{"s": i * 5.0, "e": i * 5.0 + 4.0, "text": "Phrase courte autonome."} for i in range(6)]
    assert adjust(
        serres,
        {"i": 3, "j": 4, "final": arriere, "garde_fou": {}, "after": [], "k_correction": None, "k_suite": None},
    ) == (1, 4)
    longs = [{"s": i * 40.0, "e": i * 40.0 + 30.0, "text": "Phrase longue et autonome."} for i in range(5)]
    resserre = adjust(
        longs,
        {
            "i": 0,
            "j": 1,
            "final": suite,
            "k_correction": 4,
            "k_suite": None,
            "garde_fou": {},
            "after": [4],
        },
    )
    assert resserre is not None
    assert resserre[0] > 0
    assert longs[resserre[1]]["e"] - longs[resserre[0]]["s"] <= 90


def test_run_id_est_stable():
    import orchestrator

    assert orchestrator.run_id("https://example.com/v") == orchestrator.run_id("https://example.com/v")
    assert len(orchestrator.run_id("abc")) == 10


def test_top_un_s_arrete_au_premier_candidat(tmp_path):
    from agents import chercheur

    mots = []
    for k in range(4):
        debut = k * 40.0
        parts = "Pourquoi cette explication autonome tient vraiment jusqu'au bout.".split()
        pas = 30.0 / len(parts)
        for i, p in enumerate(parts):
            mot = p if i < len(parts) - 1 else p
            mots.append(
                {
                    "w": mot,
                    "s": round(debut + i * pas, 3),
                    "e": round(debut + (i + 1) * pas, 3),
                }
            )
    _, chosen = chercheur.run_agent(str(tmp_path), mots, [], top=1)
    assert len(chosen) == 1
