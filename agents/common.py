"""Outils partagés : chemins, minuterie d'étape, lecture/écriture JSON, prompts skills/.

Cas limites : un artefact déjà présent est réutilisé (reprise après crash, Régénérer gratuit).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from .log import logger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_BIN = os.path.dirname(sys.executable)


def skill(name: str) -> str:
    with open(os.path.join(ROOT, "skills", name + ".md"), encoding="utf-8") as handle:
        return handle.read()


def jload(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def jsave(path: str, obj: object) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def progress(run: str, step: str, pct: int, msg: str = "") -> None:
    jsave(
        os.path.join(run, "progress.json"),
        {"step": step, "pct": pct, "msg": msg, "ts": time.time()},
    )
    print(f"[{pct:3d}%] {step} {msg}", flush=True)
    logger().info("progress", extra={"step": step, "pct": pct, "detail": msg, "run": run})


@contextmanager
def timed(run: str, step: str) -> Iterator[None]:
    path = os.path.join(run, "timings.json")
    debut = time.monotonic()
    yield
    mesures = cast(dict[str, float], jload(path, {}))
    duree = round(time.monotonic() - debut, 2)
    # étape réutilisée depuis le cache : on garde le temps mesuré la 1re fois
    if duree >= 1 or step not in mesures:
        mesures[step] = duree
    jsave(path, mesures)


def sh(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
    resultat = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if resultat.returncode != 0:
        raise RuntimeError(f"ÉCHEC commande {cmd[0]} : {resultat.stderr[-800:]}")
    return resultat


def tool(name: str) -> str:
    """Binaire du venv courant, sinon celui du PATH."""
    chemin = os.path.join(VENV_BIN, name)
    return chemin if os.path.exists(chemin) else name


def ytdlp() -> list[str]:
    """yt-dlp + runtime JS node si présent (sinon YouTube ne donne que l'audio)."""
    base = [tool("yt-dlp")]
    if shutil.which("node"):
        base += ["--js-runtimes", "node"]
    return base


def hms(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:06.3f}"
