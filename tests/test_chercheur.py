"""Sélection des candidats : fenêtres 20-90 s, sujets, silences, pré-tri. Aucun LLM."""

import pytest

from agents import chercheur


def mots(texte, debut, fin):
    parts = texte.split()
    pas = (fin - debut) / len(parts)
    return [{"w": p, "s": round(debut + i * pas, 3), "e": round(debut + (i + 1) * pas, 3)} for i, p in enumerate(parts)]


def test_phrases_ponctuation_pause_et_question():
    words = [
        {"w": "Pourquoi", "s": 0.0, "e": 0.3},
        {"w": "ça", "s": 0.4, "e": 0.6},
        {"w": "marche?", "s": 0.7, "e": 0.9},
        {"w": "Suite", "s": 2.0, "e": 2.2},
        {"w": "ici.", "s": 2.3, "e": 2.6},
    ]
    sents = chercheur.sentences(words)
    assert len(sents) == 2
    assert sents[0]["q"] is True
    assert sents[0]["text"] == "Pourquoi ça marche?"
    assert sents[1]["q"] is False

    words = [
        {"w": "mot", "s": 0.0, "e": 0.2},
        {"w": "seul", "s": 0.3, "e": 0.5},
        {"w": "autre", "s": 1.5, "e": 1.8},
    ]
    sents = chercheur.sentences(words)
    assert [s["text"] for s in sents] == ["mot seul", "autre"]


def test_silence_apres_une_pause_assez_longue():
    assert chercheur.silence_after(10.0, [[9.8, 11.0]]) is True
    assert chercheur.silence_after(10.0, [[9.0, 9.2]]) is False
    assert chercheur.silence_after(10.0, [[10.5, 11.0]]) is False


def test_prescore_prefere_une_accroche_a_un_mauvais_debut():
    bon = [
        {"s": 0, "e": 30, "text": "Pourquoi personne ne le dit ?", "q": True},
        {"s": 30, "e": 50, "text": "La suite explique le mécanisme clairement.", "q": False},
    ]
    mauvais = [
        {"s": 0, "e": 30, "text": "Et donc voilà la suite du propos.", "q": False},
        {"s": 30, "e": 50, "text": "On continue encore un peu ici.", "q": False},
    ]

    def cand(sents):
        return {
            "i": 0,
            "j": 1,
            "s": 0,
            "e": 50,
            "text": " ".join(s["text"] for s in sents),
            "end_on_silence": True,
            "start_after_silence": True,
        }

    assert chercheur.prescore(cand(bon), bon) > chercheur.prescore(cand(mauvais), mauvais)


def test_sujets_separes_quand_le_lexique_change():
    cuisine = "Chocolat pâtisserie ganache praliné caramel fondant."
    astro = "Planète galaxie orbite satellite télescope nébuleuse."
    sents = []
    for k in range(9):
        sents.append(
            {
                "s": k * 15.0,
                "e": (k + 1) * 15.0,
                "text": cuisine if k < 3 else astro,
                "q": False,
            }
        )
    lab = chercheur.topics(sents)
    assert lab[:3] == [0, 0, 0]
    assert lab[3:] == [1] * 6


def test_fenetres_respectent_duree_sujet_et_non_chevauchement(tmp_path):
    cuisine = "Chocolat pâtisserie ganache praliné caramel fondant."
    astro = "Planète galaxie orbite satellite télescope nébuleuse."
    words = []
    for k in range(9):
        words += mots(cuisine if k < 3 else astro, k * 15.0, (k + 1) * 15.0)
    sents, chosen = chercheur.run_agent(str(tmp_path), words, [])
    assert len(sents) == 9
    assert chosen
    assert [c["id"] for c in chosen] == [f"c{i}" for i in range(1, len(chosen) + 1)]
    assert all(20 <= c["e"] - c["s"] <= 90 for c in chosen)
    for i in range(len(chosen) - 1):
        a, b = chosen[i], chosen[i + 1]
        assert a["e"] <= b["s"] or b["e"] <= a["s"]
    assert all(not (c["i"] < 3 <= c["j"]) for c in chosen)
    assert any(c["j"] < 3 for c in chosen)
    assert any(c["i"] >= 3 for c in chosen)
    assert not (tmp_path / "llm_calls.jsonl").exists()


def test_exclusion_retire_le_passage_deja_livre(tmp_path):
    words = mots(
        "Pourquoi personne ne dit jamais la vérité sur ce point précis aujourd'hui ?",
        0,
        30,
    )
    words += mots(
        "Comment le mécanisme change vraiment le résultat pour tout le groupe présent ?",
        120,
        150,
    )
    sil = [[30.0, 30.6], [150.0, 150.6]]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, chosen = chercheur.run_agent(str(tmp_path / "a"), words, sil)
    assert len(chosen) >= 2
    top = chosen[0]
    _, reste = chercheur.run_agent(str(tmp_path / "b"), words, sil, exclude=[(top["s"], top["e"])])
    assert reste
    assert all(c["e"] <= top["s"] or c["s"] >= top["e"] for c in reste)


def test_source_trop_courte_echoue(tmp_path):
    words = [{"w": "Bonjour.", "s": 0.0, "e": 1.0}]
    with pytest.raises(RuntimeError, match="20-90"):
        chercheur.run_agent(str(tmp_path), words, [])


def test_monologue_sans_silence_reste_candidat(tmp_path):
    words = mots(
        "Voici une explication autonome qui tient toute seule du début jusqu'à la fin.",
        0,
        35,
    )
    _, chosen = chercheur.run_agent(str(tmp_path), words, [])
    assert chosen
    assert all(c["end_on_silence"] is False for c in chosen)
