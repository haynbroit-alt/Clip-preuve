"""Interface web : hôte local seulement, écritures cross-site refusées, upload plafonné, page échappée.
Aucun job réel : la file est remplacée, l'orchestrateur n'est jamais appelé."""

import os
import queue
import re

import pytest
from fastapi.testclient import TestClient

import app
import orchestrator

LOCAL = "http://127.0.0.1:8000"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "RUNS", str(tmp_path / "runs"))
    os.makedirs(orchestrator.RUNS)
    monkeypatch.setattr(app, "Q", queue.Queue())  # le worker reste bloqué sur l'ancienne file
    monkeypatch.setattr(app, "JOBS", {})
    return TestClient(app.app, base_url=LOCAL)


def _runs():
    return os.listdir(orchestrator.RUNS)


def test_lien_local_accepte_et_mis_en_file(client):
    r = client.post("/api/clip", data={"url": "https://www.youtube.com/watch?v=abc"})
    assert r.status_code == 200
    jid = r.json()["id"]
    assert app.Q.get_nowait() == (jid, "https://www.youtube.com/watch?v=abc", False)
    assert client.get(f"/api/job/{jid}").json()["progress"]["step"] == "en file"


@pytest.mark.parametrize(
    "entetes",
    [
        {"Origin": "https://site-malveillant.example"},
        {"Origin": "null"},
        {"Origin": "http://127.0.0.1:3000"},  # autre port = autre origine
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_ecriture_depuis_un_autre_site_refusee(client, entetes):
    r = client.post("/api/clip", data={"url": "https://exemple.org/v"}, headers=entetes)
    assert r.status_code == 403
    assert app.Q.empty()
    assert _runs() == []


def test_meme_origine_acceptee(client):
    r = client.post("/api/clip", data={"url": "https://exemple.org/v"}, headers={"Origin": LOCAL})
    assert r.status_code == 200


def test_regenerer_depuis_un_autre_site_refusee(client):
    jid = client.post("/api/clip", data={"url": "https://exemple.org/v"}).json()["id"]
    app.Q.get_nowait()
    r = client.post(f"/api/job/{jid}/regenerer", headers={"Origin": "https://site-malveillant.example"})
    assert r.status_code == 403
    assert app.Q.empty()


@pytest.mark.parametrize("hote", ["evil.example", "evil.example:8000", "192.168.1.10:8000"])
def test_hote_etranger_refuse_dns_rebinding(client, hote):
    assert client.get("/", headers={"Host": hote}).status_code == 403
    assert client.post("/api/clip", data={"url": "https://exemple.org/v"}, headers={"Host": hote}).status_code == 403


@pytest.mark.parametrize("hote", ["localhost:8000", "127.0.0.1", "[::1]:8000"])
def test_hotes_locaux_acceptes(client, hote):
    assert client.get("/", headers={"Host": hote}).status_code == 200


@pytest.mark.parametrize(
    "url",
    ["", "ftp://x/v", "file:///etc/passwd", "http://", "javascript:alert(1)", "https://a b", "https://x/" + "a" * 2100],
)
def test_lien_invalide_refuse_sans_creer_de_dossier(client, url):
    r = client.post("/api/clip", data={"url": url})
    assert r.status_code == 400
    assert _runs() == []
    assert app.Q.empty()


def test_upload_nom_de_fichier_sans_traversee(client):
    r = client.post("/api/clip", files={"fichier": ("../../evil.mp4", b"donnees", "video/mp4")})
    assert r.status_code == 200
    jid, src, _ = app.Q.get_nowait()
    assert os.path.dirname(src) == os.path.join(orchestrator.RUNS, "web_" + jid)
    assert os.path.basename(src) == "upload_evil.mp4"
    with open(src, "rb") as f:
        assert f.read() == b"donnees"


def test_upload_trop_gros_refuse_et_nettoye(client, monkeypatch):
    monkeypatch.setattr(app, "MAX_UPLOAD", 10)
    monkeypatch.setattr(app, "BLOC", 4)
    r = client.post("/api/clip", files={"fichier": ("gros.mp4", b"x" * 64, "video/mp4")})
    assert r.status_code == 413
    assert _runs() == []
    assert app.Q.empty()


def test_content_length_annonce_trop_grand_refuse_avant_lecture(client, monkeypatch):
    monkeypatch.setattr(app, "MAX_UPLOAD", 10)
    monkeypatch.setattr(app, "BLOC", 4)
    r = client.post("/api/clip", content=b"x" * 64, headers={"Content-Type": "multipart/form-data; boundary=b"})
    assert r.status_code == 413
    assert _runs() == []


def test_fichier_de_job_ne_sort_pas_du_dossier(client):
    jid = client.post("/api/clip", data={"url": "https://exemple.org/v"}).json()["id"]
    assert client.get(f"/api/job/{jid}/fichier/..%2F..%2Fapp.py").status_code == 404
    assert client.get(f"/api/job/{jid}/fichier/src.txt").status_code == 404  # extension non servie


def test_page_echappe_le_message_d_erreur_et_les_identifiants():
    """Régression XSS : p.msg (stderr de yt-dlp, qui contient l'URL saisie) était inséré tel quel."""
    with open(os.path.join(app.HERE, "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert "esc(p.msg)" in html
    assert not re.search(r"\+\s*p\.msg\s*\+", html)
    # esc() échappe aussi les guillemets (contexte attribut)
    assert "'\"':'&quot;'" in html and "\"'\":'&#39;'" in html
    # aucun ${id} ni ${c.clip.fichier} brut dans le HTML généré
    assert "${id}" not in html
    assert "${c.clip.fichier}" not in html


def test_page_affiche_la_phrase_cle_inconnue_et_l_avis_de_l_ia():
    with open(os.path.join(app.HERE, "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert "Phrase clé : INCONNU" in html
    assert "pourquoi_ce_moment_source" in html
    assert "relances_sans_vad" in html
    # la phrase clé n'est affichée que si elle existe (null = introuvable dans la transcription)
    assert "${c.phrase_cle?" in html
