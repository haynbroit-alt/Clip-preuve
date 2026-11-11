#!/usr/bin/env python3
"""INTERFACE : FastAPI + une seule page (index.html). Pas de compte. Un job à la fois (file d'attente simple).
POST /api/clip (lien ou fichier) -> id ; GET /api/job/{id} -> progression + carte ;
POST /api/job/{id}/regenerer (gratuit).
Sécurité : hôte local seulement, écritures cross-site refusées, upload plafonné (CLIP_MAX_UPLOAD_MO).
Cas limites : fichier > 3 h refusé par le transcripteur (ÉCHEC affiché) ; 2e demande pendant un job -> mise en file.
"""

import os
import queue
import shutil
import threading
import uuid
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

import orchestrator
from agents.common import jload

HERE = os.path.dirname(os.path.abspath(__file__))
app, Q, JOBS = FastAPI(title="Clip+Preuve"), queue.Queue(), {}

# Sécurité (serveur local) :
# - Host limité à la machine (contre le DNS rebinding) ; CLIP_HOSTS ajoute des noms séparés par des virgules.
# - Requête d'écriture venue d'un autre site (Origin / Sec-Fetch-Site) refusée : une page web visitée
#   ne peut pas lancer de job.
# - Upload limité à CLIP_MAX_UPLOAD_MO (8 Go par défaut, ~3 h de vidéo) ; Content-Length obligatoire.
_EN_PLUS = os.environ.get("CLIP_HOSTS", "").split(",")
HOTES = {"127.0.0.1", "localhost", "::1"} | {h.strip().lower() for h in _EN_PLUS if h.strip()}
MAX_UPLOAD = int(os.environ.get("CLIP_MAX_UPLOAD_MO", "8192")) * 1024 * 1024
MAX_URL = 2048
BLOC = 1024 * 1024


def _hote(netloc: str) -> str:
    """Nom d'hôte sans port, sans crochets IPv6, en minuscules."""
    return (urlsplit("//" + netloc).hostname or "").lower()


@app.middleware("http")
async def garde(request: Request, suite):
    host = request.headers.get("host", "")
    if _hote(host) not in HOTES:
        return JSONResponse({"detail": "hôte refusé"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("sec-fetch-site", "") == "cross-site":
            return JSONResponse({"detail": "requête d'un autre site refusée"}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None and urlsplit(origin).netloc.lower() != host.lower():
            return JSONResponse({"detail": "origine refusée"}, status_code=403)
        if request.url.path == "/api/clip":
            taille = request.headers.get("content-length")
            if taille is None or not taille.isdigit():
                return JSONResponse({"detail": "Content-Length obligatoire"}, status_code=411)
            if int(taille) > MAX_UPLOAD + BLOC:  # marge pour les en-têtes multipart
                return JSONResponse({"detail": "fichier trop gros"}, status_code=413)
    return await suite(request)


def lien_valide(url: str) -> bool:
    if not url or len(url) > MAX_URL or any(c.isspace() or ord(c) < 32 for c in url):
        return False
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def worker():
    while True:
        jid, src, regen = Q.get()
        try:
            orchestrator.main(src, JOBS[jid], regen)
        except Exception:
            pass  # l'erreur est écrite dans progress.json par l'orchestrateur


threading.Thread(target=worker, daemon=True).start()
# les runs déjà sur disque (CLI ou sessions précédentes) restent consultables : /?id=<nom du dossier>
if os.path.isdir(orchestrator.RUNS):
    for d in os.listdir(orchestrator.RUNS):
        if os.path.isdir(os.path.join(orchestrator.RUNS, d)):
            JOBS[d.removeprefix("web_")] = os.path.join(orchestrator.RUNS, d)


@app.get("/", response_class=HTMLResponse)
def index():
    return open(os.path.join(HERE, "index.html"), encoding="utf-8").read()


@app.post("/api/clip")
def clip(url: str = Form(""), fichier: UploadFile | None = File(None)):  # noqa: B008
    # `def` (pas `async`) : la copie du fichier tourne dans un thread, le polling reste servi.
    nom = os.path.basename((fichier.filename or "").replace("\\", "/")) if fichier else ""
    if not nom and not lien_valide(url.strip()):
        raise HTTPException(400, "Donnez un lien http(s) ou un fichier")
    jid = uuid.uuid4().hex[:10]
    run = os.path.join(orchestrator.RUNS, "web_" + jid)
    os.makedirs(run)
    if nom and fichier:
        src = os.path.join(run, "upload_" + nom)
        ecrit = 0
        with open(src, "wb") as sortie:
            while bloc := fichier.file.read(BLOC):
                ecrit += len(bloc)
                if ecrit > MAX_UPLOAD:
                    break
                sortie.write(bloc)
        if ecrit > MAX_UPLOAD:
            shutil.rmtree(run, ignore_errors=True)
            raise HTTPException(413, "fichier trop gros")
    else:
        src = url.strip()
    JOBS[jid] = run
    open(os.path.join(run, "src.txt"), "w").write(src)
    Q.put((jid, src, False))
    return {"id": jid}


@app.post("/api/job/{jid}/regenerer")
def regen(jid: str):
    run = JOBS.get(jid)
    if not run:
        raise HTTPException(404)
    from agents.common import jsave

    jsave(os.path.join(run, "progress.json"), {"step": "en file", "pct": 0, "msg": "régénération"})
    Q.put((jid, open(os.path.join(run, "src.txt")).read(), True))
    return {"ok": True}


@app.get("/api/job/{jid}")
def job(jid: str):
    run = JOBS.get(jid)
    if not run:
        raise HTTPException(404)
    p = jload(os.path.join(run, "progress.json"), {"step": "en file", "pct": 0, "msg": ""})
    card = jload(os.path.join(run, "preuve.json")) if p.get("step") == "terminé" else None
    return {"progress": p, "carte": card}


@app.get("/api/job/{jid}/fichier/{name}")
def fichier(jid: str, name: str):
    run = JOBS.get(jid)
    path = os.path.join(run or "", os.path.basename(name))
    if not run or not os.path.exists(path) or not name.endswith((".mp4", ".json", ".md")):
        raise HTTPException(404)
    return FileResponse(path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
