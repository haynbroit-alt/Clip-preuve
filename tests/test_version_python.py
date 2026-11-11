"""Régression : le README et pyproject annonçaient Python 3.10+, alors que yt-dlp épinglé exige 3.11
et que la CI ne testait que 3.12. La version minimale annoncée doit être celle que la CI teste."""

import os
import re
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lire(nom):
    with open(os.path.join(ROOT, nom), encoding="utf-8") as f:
        return f.read()


def _minimum():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        spec = tomllib.load(f)["project"]["requires-python"]
    m = re.fullmatch(r">=\s*3\.(\d+)", spec)
    assert m, spec
    return f"3.{m.group(1)}"


def test_version_minimale_testee_par_la_ci():
    ci = _lire(".github/workflows/ci.yml")
    matrice = re.search(r"python-version: \[([^\]]+)\]", ci)
    assert matrice, "la CI de tests doit avoir une matrice de versions"
    assert f'"{_minimum()}"' in matrice.group(1)


def test_documentation_et_installation_annoncent_le_meme_minimum():
    mini = _minimum()
    assert f"Python {mini}+" in _lire("README.md")
    assert f"Python {mini}+" in _lire("CONTRIBUTING.md")
    majeur, mineur = mini.split(".")
    assert f"sys.version_info < ({majeur}, {mineur})" in _lire("install.sh")
    assert "3.10+" not in _lire("README.md") + _lire("CONTRIBUTING.md")


def test_interpreteur_courant_respecte_le_minimum():
    assert sys.version_info[:2] >= tuple(int(x) for x in _minimum().split("."))
