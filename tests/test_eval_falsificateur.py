"""Banc du Falsificateur : format du jeu annoté, calcul des mesures, mesure de départ figée.

La mesure de départ décrit le garde-fou lexical tel qu'il est. Si un changement du garde-fou la fait bouger,
ce test casse exprès : mettre à jour les chiffres ci-dessous dans le même commit, avec le nouveau rapport.
"""

import pytest

from agents import eval_falsificateur as E
from agents import falsificateur as F
from tests.eval.rapport_falsificateur import main

BANC = "tests/eval/falsificateur"


def test_jeu_annote_bien_forme():
    cas = E.charger(BANC)
    assert len(cas) == 30
    assert len({c["id"] for c in cas}) == 30
    categories = {c["categorie"] for c in cas}
    assert categories == {"vrai_conflit", "faux_conflit", "neutre", "coupe", "injection"}
    for c in cas:
        assert c["description"] and c["clip"]
        assert set(c["attendu"]) == set(E.CRITERES_CODE)
        assert set(c["attendu"].values()) <= E.ATTENDUS


def test_mesure_de_depart_du_garde_fou_lexical():
    r = E.evaluer(E.charger(BANC))
    assert r["par_critere"]["contredit_apres"] == {
        "cas": 30,
        "attendus_conflit": 11,
        "attendus_pas_conflit": 19,
        "faux_conflit": 9,
        "conflit_manque": 4,
        "pct_faux_conflit": 47.4,
        "pct_conflit_manque": 36.4,
    }
    assert r["par_critere"]["coupe_mi_idee"] == {
        "cas": 30,
        "attendus_conflit": 3,
        "attendus_pas_conflit": 27,
        "faux_conflit": 0,
        "conflit_manque": 1,
        "pct_faux_conflit": 0.0,
        "pct_conflit_manque": 33.3,
    }
    erreurs = {(e["id"], e["critere"]) for e in r["erreurs"]}
    # faux CONFLIT : tous les pièges lexicaux, plus l'injection qui contient « faux »
    assert {(f"faux-0{k}", "contredit_apres") for k in range(1, 9)} <= erreurs
    assert ("injection-04", "contredit_apres") in erreurs
    # conflits manqués : correction sans marqueur, au-delà de 40 s, sans marqueur de croyance, énumération coupée
    assert {("vrai-06", "contredit_apres"), ("vrai-07", "contredit_apres"), ("vrai-08", "contredit_apres")} <= erreurs
    assert {("coupe-03", "coupe_mi_idee"), ("injection-03", "contredit_apres")} <= erreurs
    assert len(erreurs) == 14


def test_conflit_manque_sort_en_prouve_quand_le_llm_est_trompe():
    """Le risque à surveiller : un défaut réel qui passe en PROUVÉ si le LLM ne signale rien."""
    r = E.evaluer(E.charger(BANC))
    manques = [e for e in r["erreurs"] if e["conflit_manque"]]
    assert manques and all(e["obtenu"] == "PROUVÉ" for e in manques)


def test_piege_historique_et_injection_attrapes_par_le_code():
    cas = {c["id"]: c for c in E.charger(BANC)}
    for nom in ("vrai-01", "injection-01", "injection-02"):
        res = E.evaluer_cas(cas[nom])["criteres"]["contredit_apres"]
        assert res["obtenu"] == "CONFLIT", nom
        assert res["source"] == "garde-fou lexical", nom


def test_phrases_datees_et_pause():
    sents, i, j = E.phrases({"avant": ["a."], "clip": ["b.", "c."], "apres": [{"text": "d.", "pause_avant_s": 40}]})
    assert (i, j) == (1, 2)
    assert sents[1]["s"] == E.DUREE_AUTRE + E.PAUSE
    assert sents[3]["s"] - sents[2]["e"] == pytest.approx(40 + E.PAUSE)


def test_reponse_llm_propre_au_cas_et_restauration():
    ancien = F.call_json
    cas = {
        "id": "x",
        "categorie": "neutre",
        "clip": ["Le marché ouvre à sept heures.", "Les producteurs arrivent tôt.", "Tout part avant neuf heures."],
        "apres": ["Il pleuvait ce matin-là sur toute la ville."],
        "llm": {"correction_apres": "Il pleuvait ce matin-là sur toute la ville."},
        "attendu": {"contredit_apres": "PAS_CONFLIT", "coupe_mi_idee": "PAS_CONFLIT"},
    }
    res = E.evaluer_cas(cas)["criteres"]["contredit_apres"]
    assert res["obtenu"] == "CONFLIT" and res["source"] == "LLM" and res["faux_conflit"]
    assert F.call_json is ancien


def test_jeu_invalide_refuse():
    base = {"id": "a", "categorie": "neutre", "clip": ["x."], "attendu": {k: "PAS_CONFLIT" for k in E.CRITERES_CODE}}
    with pytest.raises(ValueError, match="double"):
        E.evaluer([base, dict(base)])
    with pytest.raises(ValueError, match="attendu inconnu"):
        E.evaluer([{**base, "attendu": {"contredit_apres": "PROUVÉ", "coupe_mi_idee": "PAS_CONFLIT"}}])


def test_rapport_en_ligne_de_commande(capsys):
    r = main([BANC])
    sortie = capsys.readouterr().out
    assert '"faux_conflit": 9' in sortie and '"resultats"' not in sortie
    assert r["cas"] == 30
    main([BANC, "--details"])
    assert '"resultats"' in capsys.readouterr().out
