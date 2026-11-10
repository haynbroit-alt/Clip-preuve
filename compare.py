#!/usr/bin/env python3
"""COMPARE : même vidéo, notre clip à côté d'une sortie manuelle fournie.
Usage : python compare.py runs/<run> --manuel clip_manuel.mp4 [--debut 00:12:03 --fin 00:12:48]
Sortie : <run>/compare.mp4 (côte à côte, 2x 540x960) + <run>/compare.json (chevauchement temporel si bornes manuelles données).
Sans référence manuelle : verdict INCONNU (on ne compare pas à du vide). Cas limites : durées différentes -> la plus longue
est conservée, l'autre se fige ; référence sans son -> silence.
"""
import argparse
import json
import os
import subprocess
import sys


def sec(t):
    p = [float(x) for x in str(t).split(":")]
    return sum(v * 60 ** k for k, v in enumerate(reversed(p)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--manuel")
    ap.add_argument("--debut")
    ap.add_argument("--fin")
    a = ap.parse_args(argv)
    with open(os.path.join(a.run, "preuve.json"), encoding="utf-8") as f:
        card = json.load(f)
    ours = os.path.join(a.run, card["clip"]["fichier"])
    res = {"notre_clip": {"debut": card["clip"]["debut"], "fin": card["clip"]["fin"], "statut": card["statut"]}}
    if not a.manuel or not os.path.exists(a.manuel):
        res["verdict"] = "INCONNU"
        res["raison"] = "aucune sortie manuelle fournie : comparaison impossible"
    else:
        if a.debut and a.fin:
            s1, e1, s2, e2 = card["clip"]["debut_s"], card["clip"]["fin_s"], sec(a.debut), sec(a.fin)
            inter = max(0, min(e1, e2) - max(s1, s2))
            union = max(e1, e2) - min(s1, s2)
            res["chevauchement_IoU"] = round(inter / union, 3) if union else 0
            res["manuel"] = {"debut": a.debut, "fin": a.fin}
        out = os.path.join(a.run, "compare.mp4")
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", ours, "-i", a.manuel, "-filter_complex",
             "[0:v]scale=540:960:force_original_aspect_ratio=decrease,pad=540:960:(ow-iw)/2:(oh-ih)/2,setsar=1,"
             "drawtext=text='Clip+Preuve':x=10:y=10:fontsize=28:fontcolor=yellow[a];"
             "[1:v]scale=540:960:force_original_aspect_ratio=decrease,pad=540:960:(ow-iw)/2:(oh-ih)/2,setsar=1,"
             "drawtext=text='Manuel':x=10:y=10:fontsize=28:fontcolor=white[b];[a][b]hstack=inputs=2:shortest=0[v]",
             "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "22", "-c:a", "aac", out],
            capture_output=True, text=True)
        res["fichier"] = out if r.returncode == 0 else None
        res["verdict"] = "PROUVÉ (vidéo côte à côte produite)" if r.returncode == 0 else "ÉCHEC : " + r.stderr[-300:]
    with open(os.path.join(a.run, "compare.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    return res


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
    sys.exit(0)
