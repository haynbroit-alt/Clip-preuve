"""Agent MONTEUR : récupère seulement la section vidéo utile (yt-dlp --download-sections), recadre en 9:16 sur le visage
suivi du visage sur TOUT le clip (mediapipe ~5 img/s, lissage aller-retour, zone morte, remise à zéro aux vrais
changements de plan), repli recadrage centré ; source figée (>80 % freezedetect)
-> image entière + fond flouté + zoom lent ;
sous-titres karaoké mot par mot (mot actif jaune + effet pop) ;
audio passe-haut 80 Hz + débruitage afftdn + loudnorm -14 LUFS + fondus 80 ms.
Artefacts : section.mp4, crop.json, subs.ass, clip.mp4.
Cas limites : pas de piste vidéo (podcast audio) -> fond noir 1080x1920 + sous-titres ; aucun visage -> centre (noté) ;
source déjà verticale -> pas de recadrage horizontal.
"""

from __future__ import annotations

import glob
import math
import os
import subprocess
from typing import Any, cast

from .common import jsave, progress, sh, ytdlp
from .locuteur import integrer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACE_MODEL = os.path.join(ROOT, "llm", "blaze_face_short_range.tflite")
PAD = 1.0


def fetch_section(run: str, meta: dict[str, Any], s: float, e: float) -> str:
    out = os.path.join(run, f"section_{s:.2f}_{e:.2f}.mp4")
    if os.path.exists(out):
        return out
    a, b = max(0, s - PAD), e + PAD
    if meta["kind"] == "url":
        for ancien in glob.glob(os.path.join(run, "section_dl.*")):
            os.remove(ancien)
        sh(
            [
                *ytdlp(),
                "-f",
                "bv*[protocol*=m3u8][height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b",
                "--no-playlist",
                "--download-sections",
                f"*{a:.2f}-{b:.2f}",
                "--merge-output-format",
                "mp4",
                "-o",
                os.path.join(run, "section_dl.%(ext)s"),
                meta["src"],
            ]
        )
        src = glob.glob(os.path.join(run, "section_dl.*"))[0]
        if not probe(src):
            raise RuntimeError("ÉCHEC : YouTube n'a fourni que l'audio pour la section (runtime JS manquant ?)")
        os.replace(src, out)
    else:
        sh(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                f"{a:.3f}",
                "-to",
                f"{b:.3f}",
                "-i",
                meta["src"],
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-c:a",
                "aac",
                out,
            ]
        )
    return out


def probe(path: str) -> tuple[int, int] | None:
    r = sh(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            path,
        ]
    ).stdout.strip()
    if not r:
        return None
    return cast(tuple[int, int], tuple(int(x) for x in r.split(",")[:2]))


def freeze_pct(path: str, a: float, dur: float) -> float:
    """% de la durée [a, a+dur] où la source est figée (freezedetect -60 dB, 0,5 s)."""
    import re

    r = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            f"{a:.3f}",
            "-t",
            f"{dur:.3f}",
            "-i",
            path,
            "-an",
            "-vf",
            "freezedetect=n=-60dB:d=0.5",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stderr
    fz = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", r)]
    st = re.findall(r"freeze_start: ([\d.]+)", r)
    if len(st) > len(fz):
        fz.append(dur - float(st[-1]))
    return round(100 * sum(fz) / dur, 1) if dur else 0.0


def scene_cuts(path: str, a: float, dur: float, thr: float = 0.3) -> list[float]:
    """Instants (relatifs au début du clip) des vrais changements de plan de la source."""
    import re

    r = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            f"{a:.3f}",
            "-t",
            f"{dur:.3f}",
            "-i",
            path,
            "-an",
            "-vf",
            f"select=gt(scene\\,{thr}),metadata=print:file=-",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stdout
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", r)]


def track_faces(
    path: str, w: int, a: float, dur: float, hz: float = 5.0
) -> list[tuple[float, list[tuple[float, float]]]]:
    """Détection mediapipe à ~5 images/s sur tout le clip. Renvoie [(t, centre_x en px ou None, aire)]."""
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    det = vision.FaceDetector.create_from_options(
        vision.FaceDetectorOptions(base_options=BaseOptions(model_asset_path=FACE_MODEL), min_detection_confidence=0.5)
    )
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, a * 1000)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, int(round(fps / hz)))
    n = 0
    out: list[tuple[float, list[tuple[float, float]]]] = []
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = n / fps
        if t > dur:
            break
        if n % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
                out.append(
                    (
                        t,
                        [
                            (
                                (d.bounding_box.origin_x + d.bounding_box.width / 2),
                                d.bounding_box.width * d.bounding_box.height,
                            )
                            for d in res.detections
                        ],
                    )
                )
        n += 1
    cap.release()
    det.close()
    return out


def smooth_path(
    samples: list[tuple[float, list[tuple[float, float]]]],
    cuts: list[float],
    w: int,
    cw: int,
    dur: float,
    hz: float = 5.0,
) -> list[tuple[float, int]] | None:
    """Trajectoire du cadre 9:16 : suit le visage choisi (le plus proche du précédent, le plus grand après une coupe),
    trous comblés, lissage aller-retour (constante ~1 s), zone morte de 4 % ;
    remise à zéro à chaque vrai changement de plan.
    """

    def seg_id(t: float) -> int:
        return sum(c <= t + 1e-3 for c in cuts)

    raw: list[tuple[float, int, float | None]] = []
    prev: float | None = None
    prev_seg = -1
    for t, faces in samples:
        sg = seg_id(t)
        if sg != prev_seg:
            prev = None
            prev_seg = sg
        if faces:
            big = max(faces, key=lambda f: f[1])
            if prev is None:
                pick = big
            else:
                ancre = prev
                near = min(faces, key=lambda f: abs(f[0] - ancre))
                pick = big if big[1] > 2.5 * near[1] else near
            prev = pick[0]
            raw.append((t, sg, pick[0]))
        else:
            raw.append((t, sg, None))
    if not any(x for _, _, x in raw):
        return None
    xs: list[list[Any]] = []
    out: list[tuple[float, int]] = []
    for _k, (t, sg, x) in enumerate(raw):  # combler les trous : valeur connue la plus proche dans le même plan
        if x is None:
            cand = [(abs(t2 - t), x2) for t2, s2, x2 in raw if s2 == sg and x2 is not None]
            x = min(cand)[1] if cand else w / 2
        xs.append([t, sg, x])
    alpha = 1 - math.exp(-1 / (hz * 0.8))
    for direction in (1, -1):  # lissage exponentiel avant puis arrière = sans retard
        idx = range(len(xs)) if direction == 1 else range(len(xs) - 1, -1, -1)
        last, lseg = None, None
        for k in idx:
            if last is None or xs[k][1] != lseg:
                last = xs[k][2]
            else:
                last = last + alpha * (xs[k][2] - last)
            xs[k][2] = last
            lseg = xs[k][1]
    held, lseg = None, None
    for t, sg, x in xs:  # zone morte : on ne bouge que si le visage s'écarte de plus de 4 % de la largeur
        if held is None or sg != lseg or abs(x - held) > 0.04 * w:
            held = x if held is None or sg != lseg else held + (x - held) * 0.5
        lseg = sg
        out.append((t, int(min(max(held - cw / 2, 0), w - cw))))
    return out


def ass(path: str, words: list[dict[str, Any]], s: float, e: float, t0: float) -> int:
    """Sous-titres karaoké : groupes de 3 mots, mot actif en jaune (pop 118 % -> 100 %)."""

    def ts(t: float) -> str:
        t = max(0, t)
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

    ws = [w for w in words if w["s"] >= s - 0.05 and w["e"] <= e + 0.05]
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: W,DejaVu Sans,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,460,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    groups = [ws[k : k + 3] for k in range(0, len(ws), 3)]
    for gi, g in enumerate(groups):
        for a, w in enumerate(g):
            if a + 1 < len(g):
                end = g[a + 1]["s"]
            elif gi + 1 < len(groups):
                end = min(groups[gi + 1][0]["s"], w["e"] + 0.4)
            else:
                end = w["e"] + 0.3
            txt = " ".join(
                (
                    "{\\c&H00FFFF&\\fscx118\\fscy118\\t(0,90,\\fscx100\\fscy100)}"
                    + x["w"].upper()
                    + "{\\c&HFFFFFF&\\fscx100\\fscy100}"
                )
                if x is w
                else x["w"].upper()
                for x in g
            )
            lines.append(f"Dialogue: 0,{ts(w['s'] - t0)},{ts(max(end, w['e']) - t0)},W,,0,0,0,,{txt}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(ws)


def run_agent(
    run: str,
    meta: dict[str, Any],
    words: list[dict[str, Any]],
    s: float,
    e: float,
    name: str = "clip.mp4",
) -> tuple[str, dict[str, Any]]:
    import time as _t

    progress(run, "monteur", 85, "section vidéo")
    sec = fetch_section(run, meta, s, e)
    t0 = max(0, s - PAD)  # temps source du début de section
    a, dur = s - t0, e - s
    wh = probe(sec)
    crop: dict[str, Any] = {"methode": "aucune vidéo -> fond noir"}
    subs = os.path.join(run, "subs.ass")
    nwords = ass(subs, words, s, e, s)
    progress(run, "monteur", 90, "suivi visage + rendu")
    T = _t.monotonic()
    if wh:
        w, h = wh
        cw = min(w, int(round(h * 9 / 16 / 2) * 2))
        fp = freeze_pct(sec, a, dur)
        cuts = scene_cuts(sec, a, dur)
        crop = {"source_figee_pct": fp, "changements_de_plan_source": len(cuts)}
        if fp > 80:
            # Source quasi fixe (diapo / illustration) : image réelle entière, fond flouté, lent zoom avant (Ken Burns).
            nfr = int(dur * 30) + 1  # zoompan : zoom continu image par image (1,00 -> 1,10), centré
            zp = (
                f"scale=2160:3840,zoompan=z='1+0.10*on/{nfr}':x='iw/2-(iw/zoom/2)'"
                f":y='ih/2-(ih/zoom/2)':d=1:fps=30:s=1080x1920"
            )
            fx = [f for _, fs in track_faces(sec, w, a, dur, hz=0.5) for f in fs]
            if fx:  # image fixe AVEC visage : cadrage 9:16 sur le visage + zoom lent
                x = int(min(max(max(fx, key=lambda f: f[1])[0] - cw / 2, 0), w - cw))
                crop["methode"] = "source figée : cadrage sur le visage + zoom lent (Ken Burns) sur l'image réelle"
                vf = f"[0:v]fps=30,crop={cw}:{h}:{x}:0,scale=1080:1920:flags=lanczos,{zp},setsar=1,ass={subs}[v]"
            else:  # diapo sans visage : image entière lisible sur fond flouté + zoom lent
                crop["methode"] = "source figée sans visage : image entière + fond flouté + zoom lent"
                vf = (
                    f"[0:v]fps=30,split[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.15[b];"
                    f"[fg]scale=1080:-2[f];[b][f]overlay=(W-w)/2:(H-h)/2-180,{zp},setsar=1,ass={subs}[v]"
                )
        else:
            samples = track_faces(sec, w, a, dur)
            path = smooth_path(samples, cuts, w, cw, dur)
            if path is None:
                x = (w - cw) // 2
                path = [(0.0, x)]
                crop["methode"] = "centre (repli : aucun visage)"
            else:
                crop["methode"] = "visage mediapipe suivi + lissé (cadre dynamique)"
            crop.update(
                echantillons=len(samples),
                avec_visage=sum(1 for _, f in samples if f),
                amplitude_px=max(x for _, x in path) - min(x for _, x in path),
                coupes=[round(c, 2) for c in cuts],
            )
            cmd = os.path.join(run, "crop_cmds.txt")
            with open(cmd, "w") as f:
                for t, x in path:
                    f.write(f"{t:.3f} crop@c x {x};\n")
            vf = (
                f"[0:v]sendcmd=f={cmd},crop@c={cw}:{h}:{path[0][1]}:0,"
                f"scale=1080:1920:flags=lanczos,setsar=1,ass={subs}[v]"
            )
        inp = ["-ss", f"{a:.3f}", "-t", f"{dur:.3f}", "-i", sec]
        vmap = ["-filter_complex", vf, "-map", "[v]", "-map", "0:a"]
    else:
        inp = [
            "-f",
            "lavfi",
            "-t",
            f"{dur:.3f}",
            "-i",
            "color=c=black:s=1080x1920:r=30",
            "-ss",
            f"{a:.3f}",
            "-t",
            f"{dur:.3f}",
            "-i",
            sec,
        ]
        vmap = ["-filter_complex", f"[0:v]ass={subs}[v]", "-map", "[v]", "-map", "1:a"]
    af = (
        f"highpass=f=80,afftdn=nf=-25,loudnorm=I=-14:TP=-1.5:LRA=11,"
        f"afade=t=in:st=0:d=0.08,afade=t=out:st={max(0, dur - 0.08):.3f}:d=0.08"
    )
    out = os.path.join(run, name)
    sh(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            *inp,
            *vmap,
            "-af",
            af,
            "-t",
            f"{dur:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            out,
        ]
    )
    crop["mots_sous_titres"] = nwords
    crop["rendu_s"] = round(_t.monotonic() - T, 1)
    integrer(crop, [], [])
    jsave(os.path.join(run, "crop.json"), crop)
    return out, crop
