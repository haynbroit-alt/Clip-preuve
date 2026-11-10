#!/usr/bin/env python3
"""INTERFACE : FastAPI + une seule page (index.html). Pas de compte. Un job à la fois (file d'attente simple).
POST /api/clip (lien ou fichier) -> id ; GET /api/job/{id} -> progression + carte ; POST /api/job/{id}/regenerer (gratuit).
Cas limites : fichier > 3 h refusé par le transcripteur (ÉCHEC affiché) ; 2e demande pendant un job -> mise en file.
"""
import os, queue, shutil, threading, uuid
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
import orchestrator
from agents.common import jload

HERE = os.path.dirname(os.path.abspath(__file__))
app, Q, JOBS = FastAPI(title="Clip+Preuve"), queue.Queue(), {}


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
async def clip(url: str = Form(""), fichier: UploadFile | None = File(None)):
    jid = uuid.uuid4().hex[:10]; run = os.path.join(orchestrator.RUNS, "web_" + jid); os.makedirs(run)
    if fichier and fichier.filename:
        src = os.path.join(run, "upload_" + os.path.basename(fichier.filename))
        with open(src, "wb") as f: shutil.copyfileobj(fichier.file, f)
    elif url.strip().startswith("http"):
        src = url.strip()
    else:
        raise HTTPException(400, "Donnez un lien ou un fichier")
    JOBS[jid] = run
    open(os.path.join(run, "src.txt"), "w").write(src)
    Q.put((jid, src, False))
    return {"id": jid}


@app.post("/api/job/{jid}/regenerer")
def regen(jid: str):
    run = JOBS.get(jid)
    if not run: raise HTTPException(404)
    from agents.common import jsave
    jsave(os.path.join(run, "progress.json"), {"step": "en file", "pct": 0, "msg": "régénération"})
    Q.put((jid, open(os.path.join(run, "src.txt")).read(), True))
    return {"ok": True}


@app.get("/api/job/{jid}")
def job(jid: str):
    run = JOBS.get(jid)
    if not run: raise HTTPException(404)
    p = jload(os.path.join(run, "progress.json"), {"step": "en file", "pct": 0, "msg": ""})
    card = jload(os.path.join(run, "preuve.json")) if p.get("step") == "terminé" else None
    return {"progress": p, "carte": card}


@app.get("/api/job/{jid}/fichier/{name}")
def fichier(jid: str, name: str):
    run = JOBS.get(jid)
    path = os.path.join(run or "", os.path.basename(name))
    if not run or not os.path.exists(path) or not name.endswith((".mp4", ".json", ".md")): raise HTTPException(404)
    return FileResponse(path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
