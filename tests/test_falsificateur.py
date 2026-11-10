"""Verdicts du Falsificateur, garde-fou lexical et boucle de bornes. LLM simulé."""

from agents import falsificateur as F

# Même piège que tests/trap_test.py : le clip s'arrête avant « c'est faux ».
PIEGE = [
    "Bonjour à tous et bienvenue dans ce nouvel épisode consacré à la course à pied pour les débutants.",
    "Aujourd'hui je reçois Claire, coach depuis quinze ans, qui a entraîné plus de deux mille coureurs amateurs.",
    "On va parler de l'échauffement, de la récupération et des blessures les plus fréquentes.",
    "Claire, quand vous voyez un débutant arriver au club, qu'est-ce que vous remarquez en premier ?",
    "Je remarque surtout qu'ils partent trop vite, ils veulent tout faire dès la première semaine.",
    "Et ils sont souvent mal équipés, avec des chaussures qui ne sont pas adaptées à leur foulée.",
    "Alors parlons de la préparation avant la course.",
    "L'erreur que tout le monde fait, c'est de faire de longs étirements statiques juste avant de courir.",
    "On voit ça dans tous les parcs le dimanche matin : les gens tirent sur leurs jambes pendant cinq minutes.",
    "Ils pensent que ça protège les muscles et que ça évite les blessures.",
    "Et franchement, ça paraît logique, on nous l'a appris à l'école pendant des années.",
    "Mais attention, c'est faux : les études montrent que l'étirement statique juste avant "
    "l'effort ne réduit pas les blessures et diminue même la force pendant une heure.",
    "Ce qu'il faut faire à la place, c'est un échauffement dynamique : dix minutes de footing "
    "lent, des montées de genoux et des talons-fesses.",
    "Les étirements, gardez-les pour plus tard dans la journée, quand le corps est froid et reposé.",
    "Passons maintenant à la récupération, qui est le deuxième grand sujet de ce matin.",
    "Le sommeil reste le meilleur outil de récupération, bien avant les compléments alimentaires.",
    "Dormir huit heures après une séance difficile change vraiment la progression sur trois mois.",
    "Enfin, buvez régulièrement pendant la journée, pas seulement pendant la course.",
]


def phrases_piege():
    t, sents = 0.0, []
    for x in PIEGE:
        d = max(4.0, len(x.split()) * 0.42)
        sents.append({"s": round(t, 2), "e": round(t + d, 2), "text": x, "q": x.endswith("?")})
        t += d + 0.6
    return sents


PROPRE = {
    "affirmation_du_clip": "il faut s'étirer avant de courir",
    "correction_apres": "aucune",
    "suite_necessaire": "aucune",
    "hors_contexte": {"verdict": "PROUVÉ", "preuve": "le clip se comprend seul"},
    "info_prealable": {"verdict": "PROUVÉ", "preuve": "pas besoin du début"},
}


def test_quote_exacte_conflit_quote_absente_inconnu_et_aucune_prouve():
    sents = [
        {"text": "alpha beta gamma delta epsilon", "s": 0, "e": 4},
        {"text": "la correction arrive vraiment maintenant ici", "s": 5, "e": 9},
    ]
    verdict, k = F.from_quote(sents[1]["text"], sents, [1], "correction")
    assert verdict["verdict"] == "CONFLIT"
    assert k == 1

    verdict, k = F.from_quote("cette phrase n'existe vraiment pas du tout", sents, [1], "correction")
    assert verdict["verdict"] == "INCONNU"
    assert k is None

    verdict, k = F.from_quote("aucune", sents, [1], "correction")
    assert verdict["verdict"] == "PROUVÉ"
    assert k is None

    verdict, k = F.from_quote("oui bien", sents, [1], "correction")
    assert verdict["verdict"] == "INCONNU"


def test_seuil_de_recouvrement_des_citations():
    sents = [{"text": "un deux trois quatre cinq", "s": 0, "e": 1}]
    assert F.locate("un deux trois quatre autre", sents, [0]) == 0
    assert F.locate("un deux trois autre chose", sents, [0]) is None


def test_clip_avant_la_correction_est_conflit_meme_si_le_llm_dit_aucune(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "call_json", lambda *a, **k: dict(PROPRE))
    sents = phrases_piege()
    r = F.falsify(str(tmp_path), sents, 7, 10, 1)
    assert r["llm_derive"]["contredit_apres"] == "PROUVÉ"
    assert r["garde_fou"]["contredit_apres"]["verdict"] == "CONFLIT"
    assert r["garde_fou"]["contredit_apres"]["k"] == 11
    assert r["final"]["contredit_apres"]["verdict"] == "CONFLIT"
    assert r["final"]["contredit_apres"]["source"] == "garde-fou lexical"
    assert "FALSIFICATEUR" in F.skill("falsificateur")


def test_llm_qui_cite_la_correction_donne_conflit(tmp_path, monkeypatch):
    sents = phrases_piege()
    payload = dict(PROPRE, correction_apres=sents[11]["text"])
    monkeypatch.setattr(F, "call_json", lambda *a, **k: payload)
    r = F.falsify(str(tmp_path), sents, 7, 10, 1)
    assert r["k_correction"] == 11
    assert r["llm_derive"]["contredit_apres"] == "CONFLIT"
    assert r["final"]["contredit_apres"]["verdict"] == "CONFLIT"
    assert r["final"]["contredit_apres"]["source"] == "LLM"


def test_clip_qui_inclut_la_correction_n_est_pas_contredit_par_le_garde_fou(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "call_json", lambda *a, **k: dict(PROPRE))
    sents = phrases_piege()
    r = F.falsify(str(tmp_path), sents, 7, 12, 1)
    assert "contredit_apres" not in r["garde_fou"]
    assert r["final"]["contredit_apres"]["verdict"] == "PROUVÉ"


def test_correction_avant_le_clip_ou_apres_40s_ne_declenche_pas_le_garde_fou():
    avant = [
        {"s": 0, "e": 8, "text": "Mais attention, c'est faux : ceci est dit avant le clip choisi."},
        {"s": 20, "e": 50, "text": "L'erreur que tout le monde fait, c'est de partir trop vite."},
        {"s": 51, "e": 60, "text": "La suite change de sujet sans rien renverser du tout."},
    ]
    before, after = F.ctx(avant, 1, 1)
    assert 0 in before and 0 not in after
    assert "contredit_apres" not in F.guard(avant, 1, 1, after)

    tard = [
        {"s": 0, "e": 30, "text": "L'erreur que tout le monde fait, c'est de partir trop vite."},
        {"s": 80, "e": 90, "text": "C'est faux, mais cette phrase arrive bien trop tard."},
    ]
    _before, after = F.ctx(tard, 0, 0)
    assert after == [1]
    assert "contredit_apres" not in F.guard(tard, 0, 0, after)


def test_fin_de_phrase_coupee_est_conflit():
    sents = [
        {"s": 0, "e": 10, "text": "Le sujet commence ici calmement."},
        {"s": 11, "e": 20, "text": "On continue encore un moment pour"},
    ]
    assert F.guard(sents, 0, 1, [])["coupe_mi_idee"]["verdict"] == "CONFLIT"
    sents[1] = {"s": 11, "e": 20, "text": "On s'arrête au milieu,"}
    assert F.guard(sents, 0, 1, [])["coupe_mi_idee"]["verdict"] == "CONFLIT"


def test_llm_indisponible_ne_prouve_rien_sauf_le_piege_lexical(tmp_path, monkeypatch):
    def down(*a, **k):
        raise RuntimeError("serveur éteint")

    monkeypatch.setattr(F, "call_json", down)
    r = F.falsify(str(tmp_path), phrases_piege(), 7, 10, 1)
    assert r["llm_derive"]["contredit_apres"] == "INCONNU"
    assert r["final"]["contredit_apres"]["verdict"] == "CONFLIT"
    assert r["final"]["hors_contexte"]["verdict"] == "INCONNU"
    assert r["final"]["info_prealable"]["verdict"] == "INCONNU"
    assert all(v["verdict"] != "PROUVÉ" or k == "coupe_mi_idee" for k, v in r["final"].items())


def test_verdict_illisible_devient_inconnu(tmp_path, monkeypatch):
    payload = dict(
        PROPRE,
        hors_contexte={"verdict": "PEUT-ETRE", "preuve": "flou"},
        info_prealable="pas un objet",
    )
    monkeypatch.setattr(F, "call_json", lambda *a, **k: payload)
    neutres = [
        {"s": 0, "e": 12, "text": "Le mécanisme décrit ici reste autonome et complet."},
        {"s": 12, "e": 24, "text": "La conclusion tient sans information extérieure."},
    ]
    r = F.falsify(str(tmp_path), neutres, 0, 1, 1)
    assert r["final"]["hors_contexte"]["verdict"] == "INCONNU"
    assert r["final"]["info_prealable"]["verdict"] == "INCONNU"


def test_boucle_etend_le_clip_jusqu_a_inclure_la_correction(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "call_json", lambda *a, **k: dict(PROPRE))
    sents = phrases_piege()
    ranked = [{"id": "c1", "i": 7, "j": 10, "score": 9.0}]
    verdict, cand, log = F.run_agent(str(tmp_path), sents, ranked)
    assert log[0]["final"]["contredit_apres"]["verdict"] == "CONFLIT"
    assert log[0]["final"]["contredit_apres"]["source"] == "garde-fou lexical"
    assert "7..12" in log[0]["action"]
    assert verdict["i"] == 7
    assert verdict["j"] == 12
    assert verdict["j"] >= 11
    assert verdict["final"]["contredit_apres"]["verdict"] != "CONFLIT"
    assert verdict["statut"] == "PROUVÉ"
    assert cand["id"] == "c1"
    assert (tmp_path / "falsification.json").exists()


def test_trois_iterations_sans_issue_rendent_inconnu(tmp_path, monkeypatch):
    payload = dict(
        PROPRE,
        hors_contexte={"verdict": "CONFLIT", "preuve": "le clip déplace le propos"},
    )
    monkeypatch.setattr(F, "call_json", lambda *a, **k: payload)
    sents = [
        {"s": 0, "e": 12, "text": "Le mécanisme décrit ici reste autonome et complet."},
        {"s": 12, "e": 24, "text": "Les mesures confirment le résultat annoncé plus haut."},
        {"s": 24, "e": 36, "text": "La conclusion tient sans information extérieure."},
    ]
    ranked = [{"id": "c1", "i": 0, "j": 2, "score": 8.0}]
    verdict, _cand, log = F.run_agent(str(tmp_path), sents, ranked)
    assert len(log) == 1
    assert verdict["statut"] == "INCONNU"
    assert "AVERTISSEMENT" in verdict["avertissement"]
    assert "CONFLIT" in verdict["avertissement"]
    assert verdict["final"]["hors_contexte"]["verdict"] == "CONFLIT"


def test_candidat_suivant_si_le_premier_reste_en_conflit(tmp_path, monkeypatch):
    def call(run, role, system, user, schema, max_tokens=400):
        conflit = "MARQUEUR_CONFLIT" in user
        return dict(
            PROPRE,
            hors_contexte={
                "verdict": "CONFLIT" if conflit else "PROUVÉ",
                "preuve": "contrôle",
            },
        )

    monkeypatch.setattr(F, "call_json", call)
    sents = [
        {"s": 0, "e": 10, "text": "MARQUEUR_CONFLIT le premier passage se termine proprement."},
        {"s": 10, "e": 20, "text": "Il ajoute encore une phrase de conclusion autonome."},
        {"s": 100, "e": 112, "text": "Le second passage commence sur un sujet différent."},
        {"s": 112, "e": 130, "text": "Il se termine sur une chute parfaitement compréhensible."},
    ]
    ranked = [
        {"id": "c1", "i": 0, "j": 1, "score": 9.0},
        {"id": "c2", "i": 2, "j": 3, "score": 7.0},
    ]
    verdict, cand, log = F.run_agent(str(tmp_path), sents, ranked)
    assert log[0]["action"].startswith("candidat suivant")
    assert verdict["statut"] == "PROUVÉ"
    assert cand["id"] == "c2"
    assert verdict["final"]["hors_contexte"]["verdict"] == "PROUVÉ"


def test_adjust_refuse_une_extension_trop_courte_ou_impossible():
    sents = [
        {"s": 0, "e": 5, "text": "Début autonome du propos complet."},
        {"s": 5, "e": 10, "text": "Suite encore très courte ici."},
    ]
    r = {
        "i": 0,
        "j": 1,
        "after": [],
        "k_correction": None,
        "k_suite": None,
        "garde_fou": {},
        "final": {
            "contredit_apres": {"verdict": "PROUVÉ"},
            "coupe_mi_idee": {"verdict": "PROUVÉ"},
            "hors_contexte": {"verdict": "CONFLIT"},
            "info_prealable": {"verdict": "PROUVÉ"},
        },
    }
    assert F.adjust(sents, r) is None
