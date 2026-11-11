"""Score du juge : mélange LLM (80 %) et pré-tri (20 %), cache, candidats ignorés."""

import pytest

from agents import juge


def _appel(reponses):
    appels = []

    def _call(run, role, system, user, schema, max_tokens=400):
        appels.append({"role": role, "system": system, "user": user})
        if isinstance(reponses, Exception):
            raise reponses
        for marque, payload in reponses:
            if marque in user:
                return payload
        raise AssertionError(user)

    return _call, appels


DIX = {
    "accroche_3s": 10,
    "autonomie": 10,
    "payoff": 10,
    "densite": 10,
    "citabilite": 10,
    "raison": "fort",
    "phrase_cle": "phrase haute",
}
ZERO = {
    "accroche_3s": 0,
    "autonomie": 0,
    "payoff": 0,
    "densite": 0,
    "citabilite": 0,
    "raison": "faible",
    "phrase_cle": "phrase basse",
}


def test_score_pondere_et_classement(tmp_path, monkeypatch):
    call, appels = _appel([("HAUT", DIX), ("BAS", ZERO)])
    monkeypatch.setattr(juge, "call_json", call)
    words = [
        {"w": "hors", "s": 9.0, "e": 9.2},
        {"w": "Pourquoi", "s": 10.0, "e": 10.4},
        {"w": "maintenant", "s": 11.0, "e": 11.5},
        {"w": "plus", "s": 14.0, "e": 14.4},
    ]
    cands = [
        {"id": "bas", "s": 40.0, "e": 70.0, "text": "PASSAGE_BAS", "pre": 1.0},
        {"id": "haut", "s": 10.0, "e": 40.0, "text": "PASSAGE_HAUT", "pre": 4.0},
    ]
    ranked = juge.run_agent(str(tmp_path), words, cands)
    assert [c["id"] for c in ranked] == ["haut", "bas"]
    assert ranked[0]["juge"]["llm_score"] == 10
    assert ranked[1]["juge"]["llm_score"] == 0
    assert ranked[0]["score"] == 10
    assert ranked[1]["score"] == 0
    assert "JUGE" in appels[0]["system"]
    assert "Pourquoi maintenant" in appels[1]["user"]
    assert "hors" not in appels[1]["user"].split("DURÉE")[0]


def test_notes_hors_bornes_sont_ramenees_entre_0_et_10(tmp_path, monkeypatch):
    payload = {
        "accroche_3s": 15,
        "autonomie": -3,
        "payoff": 0,
        "densite": 0,
        "citabilite": 0,
        "raison": "r",
        "phrase_cle": "p",
    }
    monkeypatch.setattr(juge, "call_json", lambda *a, **k: payload)
    cands = [{"id": "c1", "s": 0.0, "e": 30.0, "text": "passage", "pre": 2.0}]
    ranked = juge.run_agent(str(tmp_path), [], cands)
    assert ranked[0]["juge"]["llm_score"] == 2.32
    assert ranked[0]["score"] == 1.86


def test_cache_evite_un_second_appel(tmp_path, monkeypatch):
    call, appels = _appel([("passage", DIX)])
    monkeypatch.setattr(juge, "call_json", call)
    cands = [{"id": "c1", "s": 1.0, "e": 25.0, "text": "passage", "pre": 3.0}]
    juge.run_agent(str(tmp_path), [], [dict(cands[0])])
    juge.run_agent(str(tmp_path), [], [dict(cands[0])])
    assert len(appels) == 1


def test_candidat_en_echec_est_ignore_puis_tous_echouent(tmp_path, monkeypatch):
    def call(run, role, system, user, schema, max_tokens=400):
        if "CASSE" in user:
            raise RuntimeError("ÉCHEC appel LLM")
        return DIX

    monkeypatch.setattr(juge, "call_json", call)
    cands = [
        {"id": "casse", "s": 0.0, "e": 20.0, "text": "CASSE", "pre": 9.0},
        {"id": "ok", "s": 30.0, "e": 60.0, "text": "OK", "pre": 1.0},
    ]
    (tmp_path / "a").mkdir()
    ranked = juge.run_agent(str(tmp_path / "a"), [], cands)
    assert [c["id"] for c in ranked] == ["ok"]

    monkeypatch.setattr(juge, "call_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    (tmp_path / "b").mkdir()
    with pytest.raises(RuntimeError, match="aucun candidat"):
        juge.run_agent(
            str(tmp_path / "b"),
            [],
            [{"id": "c1", "s": 0.0, "e": 20.0, "text": "x", "pre": 1.0}],
        )


@pytest.mark.parametrize("note", ["8/10", "7.5", None, [8], {"n": 8}])
def test_note_mal_formee_ignore_le_candidat_sans_faire_echouer_le_run(tmp_path, monkeypatch, note):
    """Régression : une note non entière (OpenRouter sans schéma) levait ValidationError/TypeError
    et faisait échouer tout le run."""

    def call(run, role, system, user, schema, max_tokens=400):
        if "MAL_FORME" in user:
            return {**DIX, "accroche_3s": note}
        return DIX

    monkeypatch.setattr(juge, "call_json", call)
    cands = [
        {"id": "mal", "s": 0.0, "e": 20.0, "text": "MAL_FORME", "pre": 9.0},
        {"id": "ok", "s": 30.0, "e": 60.0, "text": "OK", "pre": 1.0},
    ]
    ranked = juge.run_agent(str(tmp_path), [], cands)
    assert [c["id"] for c in ranked] == ["ok"]
    assert cands[0]["juge"]["llm_score"] is None
    assert cands[0]["juge"]["erreur"].split(" : ")[0] in ("ValidationError", "TypeError")


def test_toutes_les_notes_mal_formees_donnent_un_echec_explicite(tmp_path, monkeypatch):
    monkeypatch.setattr(juge, "call_json", lambda *a, **k: {**DIX, "payoff": "huit"})
    with pytest.raises(RuntimeError, match="aucun candidat"):
        juge.run_agent(str(tmp_path), [], [{"id": "c1", "s": 0.0, "e": 20.0, "text": "x", "pre": 1.0}])
