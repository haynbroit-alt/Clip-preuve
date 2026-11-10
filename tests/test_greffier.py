"""Carte de preuve : citations exactes, verdicts, coût par heure."""

import json

from agents import greffier

MOTS = ("Pourquoi cette histoire commence ici et pas ailleurs dans le récit complet aujourd'hui vraiment").split()


def _words(debut=10.0):
    words = [{"w": "avant", "s": debut - 1.0, "e": debut - 0.5}]
    t = debut
    for w in MOTS:
        words.append({"w": w, "s": round(t, 3), "e": round(t + 0.3, 3)})
        t += 0.4
    words.append({"w": "après", "s": round(t + 1.0, 3), "e": round(t + 1.4, 3)})
    return words


def _verdict(words, statut="PROUVÉ", avertissement=None, preuve="ok"):
    dedans = [w for w in words if w["w"] not in ("avant", "après")]
    final = {
        k: {"verdict": "PROUVÉ", "preuve": preuve, "source": "LLM"}
        for k in ["hors_contexte", "info_prealable", "contredit_apres", "coupe_mi_idee"]
    }
    return {
        "s": dedans[0]["s"],
        "e": dedans[-1]["e"],
        "final": final,
        "statut": statut,
        "avertissement": avertissement,
        "iteration": 2,
    }


def _cand(verdict, s=None, e=None):
    return {
        "id": "c1",
        "s": verdict["s"] if s is None else s,
        "e": verdict["e"] if e is None else e,
        "score": 8.2,
        "juge": {
            "raison": "la chute est nette",
            "phrase_cle": "une phrase proposée par le juge",
            "accroche_3s": 8,
            "autonomie": 7,
            "payoff": 9,
            "densite": 6,
            "citabilite": 8,
        },
    }


def test_citations_viennent_des_mots_pas_du_juge(tmp_path, monkeypatch):
    monkeypatch.setattr(greffier, "backend", lambda: ("local-llama.cpp", "mock.gguf"))
    words = _words()
    verdict = _verdict(words)
    cand = _cand(verdict)
    meta = {"title": "Titre", "channel": "Chaîne", "src": "https://example.com/v", "duration": 3600}
    card = greffier.run_agent(str(tmp_path), meta, words, verdict, cand, {"methode": "centre"}, "clip.mp4")
    assert card["citation_debut"].startswith("Pourquoi")
    assert card["citation_fin"].endswith("vraiment")
    assert "avant" not in card["citation_debut"].split()
    assert "après" not in card["citation_fin"].split()
    assert card["phrase_cle"] == "une phrase proposée par le juge"
    assert card["phrase_cle"] not in card["citation_debut"]
    assert len(card["citation_debut"].split()) == 12
    assert len(card["citation_fin"].split()) == 12
    assert card["clip"]["debut"].startswith("00:00:10")
    assert card["bornes_ajustees"] is False
    assert card["statut"] == "PROUVÉ"
    md = (tmp_path / "preuve.md").read_text(encoding="utf-8")
    assert "Hors contexte ?" in md
    assert "Besoin d'info avant ?" in md
    assert "Contredit juste après ?" in md
    assert "Coupé en pleine idée ?" in md
    assert "PROUVÉ" in md
    assert "une phrase proposée par le juge" in md
    assert "centre" in md


def test_avertissement_bornes_ajustees_et_barre_verticale(tmp_path, monkeypatch):
    monkeypatch.setattr(greffier, "backend", lambda: ("openrouter", "vendor/model:free"))
    words = _words()
    verdict = _verdict(words, statut="INCONNU", avertissement="À vérifier.", preuve="gauche|droite")
    cand = _cand(verdict, s=verdict["s"] - 5, e=verdict["e"] + 5)
    meta = {"title": "T", "channel": "C", "src": "fichier.mp4", "duration": 1800}
    card = greffier.run_agent(str(tmp_path), meta, words, verdict, cand, {"methode": "visage"}, "clip.mp4")
    assert card["bornes_ajustees"] is True
    md = (tmp_path / "preuve.md").read_text(encoding="utf-8")
    assert "À vérifier." in md
    assert "gauche/droite" in md
    assert "bornes ajustées" in md
    assert card["cout"]["note"] == ""


def test_cout_local_zero_et_seuil_dix_centimes(tmp_path, monkeypatch):
    monkeypatch.setattr(greffier, "backend", lambda: ("local-llama.cpp", "mock.gguf"))
    assert greffier.costs(str(tmp_path / "vide"), 1.0)["objectif_0_10_eur_h"] == "PROUVÉ"

    ligne = {"cost_eur": 0.05, "prompt_tokens": 100, "completion_tokens": 40, "seconds": 3.25}
    (tmp_path / "llm_calls.jsonl").write_text(
        json.dumps(ligne) + "\n" + json.dumps(dict(ligne, cost_eur=0.05, prompt_tokens=10)) + "\n",
        encoding="utf-8",
    )
    propre = greffier.costs(str(tmp_path), 2.0)
    assert propre["appels_llm"] == 2
    assert propre["tokens"] == 100 + 40 + 10 + 40
    assert propre["cout_eur"] == 0.1
    assert propre["cout_eur_par_heure"] == 0.05
    assert propre["objectif_0_10_eur_h"] == "PROUVÉ"
    assert "0 €" in propre["note"]

    (tmp_path / "llm_calls.jsonl").write_text(
        json.dumps({"cost_eur": 0.10, "prompt_tokens": 1, "completion_tokens": 1, "seconds": 1}) + "\n",
        encoding="utf-8",
    )
    limite = greffier.costs(str(tmp_path), 1.0)
    assert limite["objectif_0_10_eur_h"] == "ÉCHEC"
    assert limite["heures_source"] == 1.0
