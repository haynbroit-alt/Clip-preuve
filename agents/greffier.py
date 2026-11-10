"""Agent GREFFIER : écrit la carte de preuve (preuve.json + preuve.md lisible) et le bilan de coût.
Coût = somme des appels LLM loggés (llm_calls.jsonl) / heures de source -> objectif < 0,10 €/h, affiché.
Cas limites : citation début/fin = mots exacts de la transcription (pas réécrits par le LLM) ;
statut global INCONNU + avertissement si le Falsificateur n'a rien validé ;
erreurs de transcription Whisper possibles (notées).
"""

from __future__ import annotations

import json
import os
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


def run_agent(
    run: str,
    meta: dict[str, Any],
    words: list[dict[str, Any]],
    verdict: dict[str, Any],
    cand: dict[str, Any],
    crop: dict[str, Any],
    clip_path: str,
) -> dict[str, Any]:
    s, e = verdict["s"], verdict["e"]
    ws = [w["w"] for w in words if s - 0.05 <= w["s"] and w["e"] <= e + 0.05]
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
        "phrase_cle": cand["juge"].get("phrase_cle"),
        "notes_juge": {k: cand["juge"].get(k) for k in ["accroche_3s", "autonomie", "payoff", "densite", "citabilite"]},
        "score": cand["score"],
        "candidat": cand["id"],
        "bornes_ajustees": (round(cand["s"], 2), round(cand["e"], 2)) != (round(s, 2), round(e, 2)),
        "falsificateur": verdict["final"],
        "statut": verdict["statut"],
        "avertissement": verdict.get("avertissement"),
        "iterations_falsificateur": verdict["iteration"],
        "recadrage": crop,
        "modele_llm": "/".join(backend()),
        "cout": costs(run, meta["duration"] / 3600),
        "temps_s": jload(os.path.join(run, "timings.json"), {}),
    }
    jsave(os.path.join(run, "preuve.json"), card)
    F = card["falsificateur"]
    md = [f"# Carte de preuve — statut : {card['statut']}", ""]
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
        f"**Pourquoi ce moment** : {card['pourquoi_ce_moment']}",
        f"**Phrase clé** : « {card['phrase_cle']} »",
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
