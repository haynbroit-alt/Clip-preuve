"""Instantanés : carte de preuve contre le schéma JSON, agrégation du Falsificateur."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from agents import falsificateur as F
from agents import greffier

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "preuve.schema.json").read_text(encoding="utf-8"))
VALIDATEUR = Draft202012Validator(SCHEMA)


def _mots():
    mots = ("Pourquoi cette histoire commence ici et pas ailleurs dans le récit complet aujourd'hui vraiment").split()
    words = []
    t = 10.0
    for mot in mots:
        words.append({"w": mot, "s": round(t, 3), "e": round(t + 0.3, 3)})
        t += 0.4
    return words


def test_carte_de_preuve_egale_au_golden_et_au_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(greffier, "backend", lambda: ("local-llama.cpp", "mock.gguf"))
    words = _mots()
    debut, fin = words[0]["s"], words[-1]["e"]
    final = {
        cle: {"verdict": "PROUVÉ", "preuve": "le clip tient", "source": "LLM"}
        for cle in ("hors_contexte", "info_prealable", "contredit_apres", "coupe_mi_idee")
    }
    verdict = {
        "s": debut,
        "e": fin,
        "final": final,
        "statut": "PROUVÉ",
        "avertissement": None,
        "iteration": 1,
    }
    cand = {
        "id": "c1",
        "s": debut,
        "e": fin,
        "score": 8.2,
        "juge": {
            "raison": "la chute est nette",
            "phrase_cle": "cette histoire",
            "accroche_3s": 8,
            "autonomie": 7,
            "payoff": 9,
            "densite": 6,
            "citabilite": 8,
        },
    }
    (tmp_path / "llm_calls.jsonl").write_text(
        json.dumps({"cost_eur": 0.0, "prompt_tokens": 10, "completion_tokens": 4, "seconds": 1.5}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "timings.json").write_text(json.dumps({"juge": 1.25}), encoding="utf-8")
    meta = {
        "title": "Titre fixe",
        "channel": "Chaîne",
        "src": "https://example.com/v",
        "duration": 3600.0,
    }
    card = greffier.run_agent(
        str(tmp_path),
        meta,
        words,
        verdict,
        cand,
        {"methode": "centre (test)"},
        str(tmp_path / "clip.mp4"),
    )
    attendu = json.loads((ROOT / "tests" / "golden" / "preuve.json").read_text(encoding="utf-8"))
    assert card == attendu
    assert list(VALIDATEUR.iter_errors(card)) == []
    exemple = json.loads((ROOT / "docs" / "exemple_preuve.json").read_text(encoding="utf-8"))
    assert list(VALIDATEUR.iter_errors(exemple)) == []


def test_schema_refuse_une_carte_sans_statut():
    card = json.loads((ROOT / "tests" / "golden" / "preuve.json").read_text(encoding="utf-8"))
    del card["statut"]
    assert list(VALIDATEUR.iter_errors(card))


def test_agregation_du_piege_egale_au_golden(tmp_path, monkeypatch):
    from tests.test_falsificateur import PROPRE, phrases_piege

    monkeypatch.setattr(F, "call_json", lambda *a, **k: dict(PROPRE))
    r = F.falsify(str(tmp_path), phrases_piege(), 7, 10, 1)
    extrait = {
        "i": r["i"],
        "j": r["j"],
        "llm_derive": r["llm_derive"],
        "final": r["final"],
        "garde_fou_contredit": r["garde_fou"]["contredit_apres"]["verdict"],
        "k": r["garde_fou"]["contredit_apres"]["k"],
    }
    attendu = json.loads((ROOT / "tests" / "golden" / "falsificateur_piege.json").read_text(encoding="utf-8"))
    assert extrait == attendu
    assert extrait["final"]["contredit_apres"]["verdict"] == "CONFLIT"
    assert extrait["final"]["contredit_apres"]["source"] == "garde-fou lexical"
    assert extrait["llm_derive"]["contredit_apres"] == "PROUVÉ"
