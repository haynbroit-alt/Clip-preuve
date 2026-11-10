#!/usr/bin/env python3
"""Test PIÈGE : l'orateur dit « l'erreur que tout le monde fait, c'est X » puis explique que X est faux.
Transcription SYNTHÉTIQUE (texte + timestamps, pas d'audio) : on teste le Falsificateur, pas Whisper.
A = clip qui s'arrête AVANT la correction -> doit être CONFLIT (contredit_apres).
B = clip qui inclut la correction -> ne doit pas être CONFLIT sur contredit_apres.
C = boucle complète : le Falsificateur doit ajuster les bornes de A pour inclure la correction.
Le verdict du LLM seul et celui du garde-fou lexical sont affichés séparément (honnêteté).
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents import falsificateur as F

TXT = [
 "Bonjour à tous et bienvenue dans ce nouvel épisode consacré à la course à pied pour les débutants.",
 "Aujourd'hui je reçois Claire, coach depuis quinze ans, qui a entraîné plus de deux mille coureurs amateurs.",
 "On va parler de l'échauffement, de la récupération et des blessures les plus fréquentes.",
 "Claire, quand vous voyez un débutant arriver au club, qu'est-ce que vous remarquez en premier ?",
 "Je remarque surtout qu'ils partent trop vite, ils veulent tout faire dès la première semaine.",
 "Et ils sont souvent mal équipés, avec des chaussures qui ne sont pas adaptées à leur foulée.",
 "Alors parlons de la préparation avant la course.",
 "L'erreur que tout le monde fait, c'est de faire de longs étirements statiques juste avant de courir.",
 "On voit ça dans tous les parcs le dimanche matin : les gens tirent sur leurs jambes pendant cinq minutes.",
 "Ils pensent que ça protège les muscles et que ça évite les blessures.",
 "Et franchement, ça paraît logique, on nous l'a appris à l'école pendant des années.",
 "Mais attention, c'est faux : les études montrent que l'étirement statique juste avant l'effort ne réduit pas les blessures et diminue même la force pendant une heure.",
 "Ce qu'il faut faire à la place, c'est un échauffement dynamique : dix minutes de footing lent, des montées de genoux et des talons-fesses.",
 "Les étirements, gardez-les pour plus tard dans la journée, quand le corps est froid et reposé.",
 "Passons maintenant à la récupération, qui est le deuxième grand sujet de ce matin.",
 "Le sommeil reste le meilleur outil de récupération, bien avant les compléments alimentaires.",
 "Dormir huit heures après une séance difficile change vraiment la progression sur trois mois.",
 "Enfin, buvez régulièrement pendant la journée, pas seulement pendant la course.",
]
t, sents = 0.0, []
for x in TXT:
    d = max(4.0, len(x.split()) * 0.42)  # ~2,4 mots/s
    sents.append({"s": round(t, 2), "e": round(t + d, 2), "text": x, "q": x.endswith("?")}); t += d + 0.6

run = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trap_run"); os.makedirs(run, exist_ok=True)
open(os.path.join(run, "llm_calls.jsonl"), "w").close()
res = {}
A = F.falsify(run, sents, 7, 10, 1)       # s'arrête avant « c'est faux »
B = F.falsify(run, sents, 7, 12, 2)       # inclut la correction + la consigne
for name, r in (("A_avant_correction", A), ("B_avec_correction", B)):
    res[name] = {"bornes_s": [r["s"], r["e"]], "duree_s": round(r["e"] - r["s"], 1),
                 "llm_seul": r["llm_derive"],
                 "garde_fou": {k: v["verdict"] for k, v in r["garde_fou"].items() if k != "k"},
                 "final": {k: v["verdict"] for k, v in r["final"].items()}}
ranked = [{"id": "A", "i": 7, "j": 10, "score": 9.0}]
v, c, log = F.run_agent(run, sents, ranked)
res["C_boucle"] = {"iterations": len(log), "bornes_finales_phrases": [v["i"], v["j"]], "statut": v["statut"],
                   "inclut_correction": v["j"] >= 11, "actions": [r.get("action") for r in log]}
okA = res["A_avant_correction"]["final"]["contredit_apres"] == "CONFLIT"
okB = res["B_avec_correction"]["final"]["contredit_apres"] != "CONFLIT"
res["RESULTAT"] = {"A_rejete": "PROUVÉ" if okA else "ÉCHEC", "B_non_rejete_pour_contradiction": "PROUVÉ" if okB else "ÉCHEC",
                   "A_rejete_par_LLM_seul": res["A_avant_correction"]["llm_seul"]["contredit_apres"] == "CONFLIT",
                   "C_bornes_etendues_jusqua_correction": "PROUVÉ" if res["C_boucle"]["inclut_correction"] else "ÉCHEC"}
json.dump(res, open(os.path.join(run, "resultat.json"), "w"), ensure_ascii=False, indent=2)
print(json.dumps(res, ensure_ascii=False, indent=2))
