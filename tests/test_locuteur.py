"""Décision de cadrage sur des pistes synthétiques, sans MediaPipe."""

from agents.locuteur import decider, ecart_levres, fenetres_activite, integrer, ouverture_landmarks


def _piste(face: str, t0: float, t1: float, ouvert: float, pas: float = 0.2) -> list[dict]:
    pistes = []
    t = t0
    while t <= t1:
        pistes.append({"t": t, "face": face, "ouverture": ouvert if int(t / pas) % 2 == 0 else ouvert + 0.3})
        t += pas
    return pistes


def test_distance_des_levres():
    assert ecart_levres((0.0, 0.0), (0.0, 0.4)) == 0.4
    points = [(0.0, 0.0)] * 15
    points[13] = (0.0, 0.1)
    points[14] = (0.0, 0.5)
    assert abs(ouverture_landmarks(points) - 0.4) < 1e-9


def test_hors_parole_le_mouvement_ne_compte_pas():
    pistes = _piste("A", 0.0, 1.0, 0.2)
    fenetres = fenetres_activite(pistes, [])
    assert fenetres
    assert all(score == 0.0 for _, scores in fenetres for score in scores.values())


def test_changement_apres_tenue_d_une_seconde_et_demie():
    pistes = _piste("A", 0.0, 1.4, 0.2) + _piste("B", 1.6, 4.0, 0.5)
    parole = [(0.0, 4.2)]
    plans = decider(fenetres_activite(pistes, parole), tenue=1.5)
    visages = [p["faces"][0] for p in plans if p["mode"] == "single" and p["faces"]]
    assert visages[0] == "A"
    assert "B" in visages
    bascule = next(p["t"] for p in plans if p["faces"] == ["B"])
    assert bascule >= 1.6 + 1.5 - 0.05


def test_alternance_rapide_passe_en_ecran_partage():
    pistes = []
    for i in range(8):
        face = "A" if i % 2 == 0 else "B"
        pistes += _piste(face, i * 0.4, i * 0.4 + 0.35, 0.4)
    plans = decider(fenetres_activite(pistes, [(0.0, 4.0)]), tenue=1.5)
    assert any(p["mode"] == "split" and p["faces"] == ["A", "B"] for p in plans)
    crop = integrer({"methode": "centre"}, pistes, [(0.0, 4.0)])
    assert crop["methode"] == "split-screen locuteurs actifs"


def test_integrer_sans_piste_laisse_le_cadrage():
    crop = {"methode": "centre"}
    assert integrer(crop, [], [])["methode"] == "centre"
