"""Outils partagés : chemins, minuterie d'étape, lecture/écriture JSON, prompts skills/.
Cas limites : un artefact déjà présent est réutilisé (reprise après crash, Régénérer gratuit).
"""
import json, os, subprocess, time
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_BIN = os.path.dirname(os.sys.executable)


def skill(name):
    with open(os.path.join(ROOT, "skills", name + ".md"), encoding="utf-8") as f:
        return f.read()


def jload(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def jsave(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def progress(run, step, pct, msg=""):
    jsave(os.path.join(run, "progress.json"), {"step": step, "pct": pct, "msg": msg, "ts": time.time()})
    print(f"[{pct:3d}%] {step} {msg}", flush=True)


@contextmanager
def timed(run, step):
    p = os.path.join(run, "timings.json")
    t = time.monotonic()
    yield
    d, dt = jload(p, {}), round(time.monotonic() - t, 2)
    if dt >= 1 or step not in d:  # étape réutilisée depuis le cache : on garde le temps mesuré la 1re fois
        d[step] = dt
    jsave(p, d)


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"ÉCHEC commande {cmd[0]} : {r.stderr[-800:]}")
    return r


def ytdlp():
    """yt-dlp + runtime JS node si présent (sinon YouTube ne donne que l'audio pour les sections)."""
    import shutil
    base = [tool("yt-dlp")]
    if shutil.which("node"): base += ["--js-runtimes", "node"]
    return base


def tool(name):
    """yt-dlp du venv courant sinon PATH."""
    p = os.path.join(VENV_BIN, name)
    return p if os.path.exists(p) else name


def hms(t):
    t = max(0.0, t)
    return f"{int(t//3600):02d}:{int(t%3600//60):02d}:{t%60:06.3f}"
