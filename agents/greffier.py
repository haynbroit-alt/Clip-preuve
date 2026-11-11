"""Agent GREFFIER : écrit la carte de preuve (preuve.json + preuve.md lisible) et le bilan de coût.
Coût = somme des appels LLM loggés (llm_calls.jsonl) / heures de source -> objectif < 0,10 €/h, affiché.
Cas limites : citation début/fin = mots exacts de la transcription (pas réécrits par le LLM) ;
statut global INCONNU + avertissement si le Falsificateur n'a rien validé ;
phrase clé du juge = recherchée dans les mots du clip final : retrouvée -> mots exacts de la transcription,
sinon null + INCONNU visible (le statut global, qui porte sur les 4 tests, ne change pas) ;
« pourquoi ce moment » = avis du juge (IA), étiqueté non vérifié ; erreurs de transcription Whisper possibles (notées).
"""

from __future__ import annotations

import difflib
import json
import os
import re
from typing import Any

from .common import hms, jload, jsave
from .llm import backend


def costs(run: str, hours: float) -> dict[str, Any]:
    calls = []
    p = os.path.join(run, "llm_calls.jsonl")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as handle:
            calls = [json.loads(ligne) for ligne in handle]
    eur = sum(c["cost_eur"] for c in calls)
    per_h = eur / hours if hours else 0
    return {
        "appels_llm": len(calls),
        "tokens": sum(c["prompt_tokens"] + c["completion_tokens"] for c in calls),
        "secondes_llm": round(sum(c["seconds"] for c in calls), 1),
        "cout_eur": round(eur, 5),
        "heures_source": round(hours, 3),
        "cout_eur_par_heure": round(per_h, 5),
        "objectif_0_10_eur_h": "PROUVÉ" if per_h < 0.10 else "ÉCHEC",
        "note": "LLM local (llama.cpp CPU) : 0 € d'API ; électricité/CPU non comptés."
        if backend()[0].startswith("local")
        else "",
    }


SOURCE_RAISON = "avis du juge (IA), non vérifié"
_TOKEN = re.compile(r"[\w']+")


def _tokens(texte: str) -> list[str]:
    return _TOKEN.findall(texte.lower().replace("\u2019", "'").replace("-", " "))


def verifier_phrase_cle(phrase: object, mots: list[dict[str, Any]]) -> dict[str, Any]:
    """Cherche la phrase du juge dans les mots du clip. Renvoie le texte de la TRANSCRIPTION (jamais celui du LLM).

    - séquence identique (casse, ponctuation, tirets ignorés) -> PROUVÉ ;
    - 6 mots ou plus, à un mot près (ratio >= 0,9) -> PROUVÉ, preuve « à un mot près » ;
    - sinon -> INCONNU, phrase_cle = None.
    """
    texte_juge = phrase if isinstance(phrase, str) else None
    q = _tokens(texte_juge or "")
    absent = {"verdict": "INCONNU", "texte": None, "texte_juge": texte_juge, "debut_s": None, "fin_s": None}
    if not q:
        return dict(absent, preuve="le juge n'a fourni aucune phrase clé")
    flat: list[tuple[str, int]] = [(t, k) for k, w in enumerate(mots) for t in _tokens(str(w["w"]))]
    toks = [t for t, _ in flat]

    def trouve(a: int, b: int, preuve: str) -> dict[str, Any]:
        k0, k1 = flat[a][1], flat[b - 1][1]
        return {
            "verdict": "PROUVÉ",
            "texte": " ".join(str(w["w"]) for w in mots[k0 : k1 + 1]),
            "texte_juge": texte_juge,
            "debut_s": mots[k0]["s"],
            "fin_s": mots[k1]["e"],
            "preuve": preuve,
        }

    n = len(q)
    for a in range(len(toks) - n + 1):
        if toks[a : a + n] == q:
            return trouve(a, a + n, "retrouvée mot pour mot dans la transcription du clip")
    if n >= 6:
        meilleur, borne = 0.0, None
        for taille in (n - 1, n, n + 1):
            for a in range(len(toks) - taille + 1):
                r = difflib.SequenceMatcher(None, q, toks[a : a + taille], autojunk=False).ratio()
                if r > meilleur:
                    meilleur, borne = r, (a, a + taille)
        if borne and meilleur >= 0.9:
            preuve = "retrouvée à un mot près dans la transcription du clip (texte affiché : transcription)"
            return trouve(*borne, preuve)
    return dict(absent, preuve="introuvable dans la transcription du clip : non affichée")


def run_agent(
    run: str,
    meta: dict[str, Any],
    words: list[dict[str, Any]],
    verdict: dict[str, Any],
    cand: dict[str, Any],
    crop: dict[str, Any],
    clip_path: str,
    certifie: bool = True,
) -> dict[str, Any]:
    s, e = verdict["s"], verdict["e"]
    mots_clip = [w for w in words if s - 0.05 <= w["s"] and w["e"] <= e + 0.05]
    ws = [w["w"] for w in mots_clip]
    bornes_ajustees = (round(cand["s"], 2), round(cand["e"], 2)) != (round(s, 2), round(e, 2))
    verif = verifier_phrase_cle(cand["juge"].get("phrase_cle"), mots_clip)
    relances = jload(os.path.join(run, "vad_relances.json"), [])
    card = {
        "source": {
            "titre": meta.get("title"),
            "chaine": meta.get("channel"),
            "lien": meta["src"],
            "duree_s": round(meta["duration"], 1),
        },
        "clip": {
            "debut": hms(s),
            "fin": hms(e),
            "debut_s": round(s, 3),
            "fin_s": round(e, 3),
            "duree_s": round(e - s, 2),
            "fichier": os.path.basename(clip_path),
        },
        "citation_debut": " ".join(ws[:12]),
        "citation_fin": " ".join(ws[-12:]),
        "pourquoi_ce_moment": cand["juge"].get("raison"),
        "pourquoi_ce_moment_source": SOURCE_RAISON
        + (" ; donné sur les bornes initiales du candidat" if bornes_ajustees else ""),
        "phrase_cle": verif["texte"],
        "phrase_cle_verification": verif,
        "notes_juge": {k: cand["juge"].get(k) for k in ["accroche_3s", "autonomie", "payoff", "densite", "citabilite"]},
        "score": cand["score"],
        "candidat": cand["id"],
        "bornes_ajustees": bornes_ajustees,
        "falsificateur": verdict["final"],
        "statut": verdict["statut"],
        "certifie": certifie,
        "avertissement": verdict.get("avertissement"),
        "iterations_falsificateur": verdict["iteration"],
        "recadrage": crop,
        "modele_llm": "/".join(backend()),
        "cout": costs(run, meta["duration"] / 3600),
        "temps_s": jload(os.path.join(run, "timings.json"), {}),
        "transcription": {"relances_sans_vad": relances},
    }
    jsave(os.path.join(run, "preuve.json"), card)
    F = card["falsificateur"]
    md = [
        f"# Carte de preuve — statut : {card['statut']}",
        "",
        f"**Certifié** : {'oui' if card['certifie'] else 'non'}",
        "",
    ]
    md = [f"# Carte de preuve — statut : {card['statut']}", ""]
    if verif["verdict"] != "PROUVÉ":
        md += [f"> Phrase clé : INCONNU — {verif['preuve']}.", ""]
    if relances:
        debuts = ", ".join(hms(r["debut_s"]) for r in relances)
        md += [
            f"> Transcription : {len(relances)} morceau(x) de 10 min repassé(s) sans filtre de parole (VAD), "
            f"débutant à {debuts}. Mots de ces passages à vérifier à l'écoute.",
            "",
        ]
    if card["avertissement"]:
        md += [f"> ⚠️ {card['avertissement']}", ""]
    md += [
        f"**Source** : {card['source']['titre']} ({card['source']['chaine']}) — {card['source']['lien']}",
        f"**Clip** : {card['clip']['debut']} → {card['clip']['fin']} ({card['clip']['duree_s']} s)"
        + (" — bornes ajustées par le Falsificateur" if card["bornes_ajustees"] else ""),
        "",
        f"**Commence par** : « {card['citation_debut']} … »",
        f"**Finit par** : « … {card['citation_fin']} »",
        "",
        f"**Pourquoi ce moment** ({card['pourquoi_ce_moment_source']}) : {card['pourquoi_ce_moment']}",
        (
            f"**Phrase clé** ({verif['preuve']}) : « {card['phrase_cle']} »"
            if card["phrase_cle"]
            else f"**Phrase clé** : INCONNU — {verif['preuve']}"
        ),
        "",
        "**Notes du juge (0-10)** : " + ", ".join(f"{k} {v}" for k, v in card["notes_juge"].items()),
        "",
        "## Verdict du Falsificateur",
        "| Test | Verdict | Preuve | Source |",
        "|---|---|---|---|",
    ]
    lab = {
        "hors_contexte": "Hors contexte ?",
        "info_prealable": "Besoin d'info avant ?",
        "contredit_apres": "Contredit juste après ?",
        "coupe_mi_idee": "Coupé en pleine idée ?",
    }
    for k, v in F.items():
        md.append(f"| {lab[k]} | {v['verdict']} | {str(v['preuve']).replace('|', '/')[:160]} | {v.get('source', '')} |")
    c = card["cout"]
    md += [
        "",
        f"**Coût mesuré** : {c['cout_eur']} € pour {c['heures_source']} h de source = {c['cout_eur_par_heure']} €/h "
        f"(objectif < 0,10 €/h : {c['objectif_0_10_eur_h']}). "
        f"{c['appels_llm']} appels LLM, {c['tokens']} tokens. {c['note']}",
        f"**Recadrage** : {crop.get('methode')}",
        f"**Temps par étape (s)** : {card['temps_s']}",
    ]
    with open(os.path.join(run, "preuve.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return card
