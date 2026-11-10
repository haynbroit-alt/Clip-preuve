#!/usr/bin/env python3
"""Mesure si une vidéo bouge : nb d'images, % de durée figée (freezedetect -60dB, 0,5 s), score moyen de changement
de scène (scdet) et différence moyenne entre images (YDIF de signalstats).
Usage : mesure_mouvement.py f.mp4 [debut durée]"""

import json
import re
import subprocess
import sys


def mesure(path, ss=None, t=None):
    cut = ["-ss", str(ss), "-t", str(t)] if ss is not None else []
    dur = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    if t:
        dur = min(float(t), dur - float(ss or 0))
    r = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            *cut,
            "-i",
            path,
            "-an",
            "-vf",
            "freezedetect=n=-60dB:d=0.5,select=gte(scene\\,0),metadata=print:key=lavfi.scene_score:file=-,signalstats,metadata=print:key=lavfi.signalstats.YDIF:file=-",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    err, out = r.stderr, r.stdout
    fz = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", err)]
    starts = re.findall(r"freeze_start: ([\d.]+)", err)
    if len(starts) > len(fz):  # gel jusqu'à la fin
        fz.append(dur - float(starts[-1]))
    sc = [float(x) for x in re.findall(r"lavfi\.scene_score=([\d.]+)", out)]
    yd = [float(x) for x in re.findall(r"YDIF=([\d.]+)", out)]
    frames = re.findall(r"frame=\s*(\d+)", err)
    return {
        "fichier": path,
        "duree_s": round(dur, 2),
        "images": int(frames[-1]) if frames else None,
        "fige_pct": round(100 * sum(fz) / dur, 1) if dur else None,
        "scene_score_moy": round(sum(sc) / len(sc), 3) if sc else None,
        "coupes_scene_gt_0_3": sum(x > 0.3 for x in sc),
        "ydif_moy": round(sum(yd) / len(yd), 3) if yd else None,
    }


if __name__ == "__main__":
    a = sys.argv[1:]
    print(json.dumps(mesure(a[0], *(a[1:3] if len(a) > 1 else [])), ensure_ascii=False))
