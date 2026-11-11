"""Deux exemples synthétiques, sans média protégé."""

from pathlib import Path

from agents.eval_bornes import evaluer_dossier
from tests.eval.rapport import main

EXEMPLES = Path(__file__).resolve().parents[0] / "eval" / "exemples"


def test_exemples_synthetiques():
    rapport = evaluer_dossier(str(EXEMPLES))
    assert rapport["clips"] == 2
    assert rapport["coupes_mi_idee"] == 1
    assert rapport["pct_coupes_mi_idee"] == 50.0
    par_video = {r["video"]: r for r in rapport["rapports"]}
    assert par_video["synthetique-borne-juste"]["erreur_bornes_s"] == 0.0
    assert par_video["synthetique-coupe-mi-idee"]["erreur_bornes_s"] == 10.0
    assert par_video["synthetique-coupe-mi-idee"]["details"][0]["mi_idee"] is True


def test_script_imprime_le_pourcentage(capsys):
    main([str(EXEMPLES)])
    assert "pct_coupes_mi_idee" in capsys.readouterr().out
