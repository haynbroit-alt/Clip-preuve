"""Points de coupe en EDL CMX 3600 et FCPXML, pour Premiere ou Resolve."""

from __future__ import annotations

import html
from typing import Any


def _tc(secondes: float, fps: int = 25) -> str:
    total = max(0, int(round(secondes * fps)))
    images = total % fps
    reste = total // fps
    s = reste % 60
    reste //= 60
    m = reste % 60
    h = reste // 60
    return f"{h:02d}:{m:02d}:{s:02d}:{images:02d}"


def edl(clips: list[dict[str, Any]], fps: int = 25, titre: str = "Clip-preuve") -> str:
    lignes = [f"TITLE: {titre}", "FCM: NON-DROP FRAME", ""]
    curseur = 0.0
    for i, clip in enumerate(clips, start=1):
        duree = float(clip["fin_s"]) - float(clip["debut_s"])
        lignes.append(
            f"{i:03d}  AX       V     C        {_tc(float(clip['debut_s']), fps)} {_tc(float(clip['fin_s']), fps)} "
            f"{_tc(curseur, fps)} {_tc(curseur + duree, fps)}"
        )
        lignes.append(f"* FROM CLIP NAME: {clip.get('nom', 'source')}")
        curseur += duree
    return "\n".join(lignes) + "\n"


def _sec(secondes: float) -> str:
    return f"{max(0.0, secondes):.3f}s"


def fcpxml(clips: list[dict[str, Any]], fps: int = 25, titre: str = "Clip-preuve") -> str:
    ressources = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE fcpxml>",
        '<fcpxml version="1.9">',
        "  <resources>",
        f'    <format id="r1" name="FFVideoFormat1080p{fps}" frameDuration="1/{fps}s" width="1920" height="1080"/>',
    ]
    for i, clip in enumerate(clips, start=2):
        nom = html.escape(str(clip.get("nom", "source")))
        src = html.escape(str(clip.get("src", "source.mp4")))
        ressources.append(
            f'    <asset id="r{i}" name="{nom}" src="{src}" start="0s" hasVideo="1" hasAudio="1" format="r1"/>'
        )
    ressources.append("  </resources>")
    ressources.append("  <library>")
    ressources.append(f'    <event name="{html.escape(titre)}">')
    ressources.append(f'      <project name="{html.escape(titre)}">')
    duree_totale = sum(float(c["fin_s"]) - float(c["debut_s"]) for c in clips)
    ressources.append(f'        <sequence format="r1" duration="{_sec(duree_totale)}">')
    ressources.append("          <spine>")
    offset = 0.0
    for i, clip in enumerate(clips, start=2):
        duree = float(clip["fin_s"]) - float(clip["debut_s"])
        nom = html.escape(str(clip.get("nom", "clip")))
        ressources.append(
            f'            <asset-clip ref="r{i}" offset="{_sec(offset)}" name="{nom}" '
            f'start="{_sec(float(clip["debut_s"]))}" duration="{_sec(duree)}"/>'
        )
        offset += duree
    ressources.extend(
        [
            "          </spine>",
            "        </sequence>",
            "      </project>",
            "    </event>",
            "  </library>",
            "</fcpxml>",
            "",
        ]
    )
    return "\n".join(ressources)
