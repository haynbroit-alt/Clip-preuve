"""Un clip CONFLIT ne peut pas être exporté. Le verrou est dans le code, pas dans le prompt."""

from agents.livraison import exporter, livraison_autorisee


def _verdict(conflit: bool) -> dict:
    final = {
        nom: {"verdict": "PROUVÉ", "preuve": "ok", "source": "LLM"}
        for nom in ("hors_contexte", "info_prealable", "contredit_apres", "coupe_mi_idee")
    }
    if conflit:
        final["contredit_apres"] = {"verdict": "CONFLIT", "preuve": "corrigé après", "source": "garde-fou lexical"}
    return {"final": final, "statut": "INCONNU" if conflit else "PROUVÉ", "s": 1.0, "e": 20.0, "iteration": 1}


def test_conflit_n_est_pas_exporte(tmp_path):
    cible = tmp_path / "clip.mp4"
    appels = {"n": 0}

    def ecrire() -> str:
        appels["n"] += 1
        cible.write_bytes(b"mp4")
        return str(cible)

    try:
        exporter(_verdict(True), ecrire)
        raise AssertionError("la livraison aurait dû être refusée")
    except RuntimeError as exc:
        assert "CONFLIT" in str(exc)
    assert appels["n"] == 0
    assert not cible.exists()


def test_prouve_est_exporte(tmp_path):
    cible = tmp_path / "clip.mp4"

    def ecrire() -> str:
        cible.write_bytes(b"ok")
        return str(cible)

    assert exporter(_verdict(False), ecrire) == str(cible)
    assert cible.exists()
    assert livraison_autorisee(_verdict(False))
    assert not livraison_autorisee({"final": {}, "statut": "PROUVÉ", "s": 0, "e": 1})
