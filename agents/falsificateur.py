"""Agent FALSIFICATEUR : appel LLM séparé (skills/falsificateur.md) qui tente de CASSER le clip avec ±60 s de contexte.
4 critères PROUVÉ/INCONNU/CONFLIT + garde-fou lexical (détecte « l'erreur que tout le monde fait… » suivi de « c'est faux »).
Verdict final par critère = le pire des deux (CONFLIT > INCONNU > PROUVÉ). Boucle : CONFLIT -> bornes ajustées ou candidat
suivant, 3 itérations max ; sinon meilleur candidat rendu en INCONNU + avertissement. Artefact : falsification.json.
Cas limites : clip en tout début/fin de vidéo -> contexte court (noté) ; extension > 90 s -> on raccourcit le début,
sinon candidat suivant ; LLM en panne -> critères INCONNU (jamais PROUVÉ par défaut).
"""
import os, re
from .common import jsave, progress, skill
from .llm import call_json

CRIT = ["hors_contexte", "info_prealable", "contredit_apres", "coupe_mi_idee"]
RANK = {"PROUVÉ": 0, "INCONNU": 1, "CONFLIT": 2}
V = {"type": "object", "properties": {"verdict": {"type": "string", "enum": list(RANK)}, "preuve": {"type": "string", "maxLength": 140}},
     "required": ["verdict", "preuve"]}
Q = {"type": "string", "maxLength": 220}
SCHEMA = {"type": "object", "properties": {"affirmation_du_clip": {"type": "string", "maxLength": 140}, "correction_apres": Q,
          "suite_necessaire": Q, "hors_contexte": V, "info_prealable": V},
          "required": ["affirmation_du_clip", "correction_apres", "suite_necessaire", "hors_contexte", "info_prealable"]}


def locate(quote, sents, ks):
    """La citation du LLM doit exister dans le contexte APRÈS (preuve vérifiable). Renvoie l'indice de phrase ou None."""
    q = norm(quote).split()
    if len(q) < 4:
        return None
    best, bk = 0.0, None
    for k in ks:
        st = set(norm(sents[k]["text"]).split())
        r = sum(w in st for w in q) / len(q)
        if r > best: best, bk = r, k
    return bk if best >= 0.7 else None


def from_quote(quote, sents, after, label):
    if norm(quote) in ("aucune", "aucun", ""):
        return {"verdict": "PROUVÉ", "preuve": f"le Falsificateur n'a trouvé aucune {label} dans les 60 s qui suivent"}, None
    k = locate(quote, sents, after)
    if k is None:
        return {"verdict": "INCONNU", "preuve": f"citation introuvable dans le contexte APRÈS : «{quote[:100]}»"}, None
    return {"verdict": "CONFLIT", "preuve": f"«{sents[k]['text'][:130]}»"}, k
CLAIM = ["erreur", "tout le monde", "on croit", "on pense", "on dit souvent", "beaucoup de gens", "la plupart des gens", "il faut toujours"]
CORR = ["c'est faux", "c'est pas vrai", "ce n'est pas vrai", "n'est pas vrai", "en réalité", "au contraire", "c'est l'inverse",
        "mais non", "pas du tout", "c'est une erreur", "contrairement", "c'est un mythe", "faux"]
BAD_END = {"et", "mais", "donc", "parce", "que", "qui", "de", "le", "la", "les", "un", "une", "des", "à", "pour"}


def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\wàâçéèêëîïôûùüÿœ' ]", " ", t.lower())).strip()


def ctx(sents, i, j):
    s, e = sents[i]["s"], sents[j]["e"]
    before = [k for k in range(i) if sents[k]["e"] > s - 60]
    after = [k for k in range(j + 1, len(sents)) if sents[k]["s"] < e + 60]
    return before, after


def guard(sents, i, j, after):
    clip = norm(" ".join(sents[k]["text"] for k in range(i, j + 1)))
    out = {}
    hit = next((k for k in after if sents[k]["s"] < sents[j]["e"] + 40 and any(m in norm(sents[k]["text"]) for m in CORR)), None)
    if hit is not None and any(m in clip for m in CLAIM):
        out["contredit_apres"] = {"verdict": "CONFLIT", "preuve": f"garde-fou : après le clip, «{sents[hit]['text'][:120]}»", "k": hit}
    lw = norm(sents[j]["text"]).split()[-1:] or [""]
    if lw[0] in BAD_END or sents[j]["text"].rstrip().endswith((",", ":")):
        out["coupe_mi_idee"] = {"verdict": "CONFLIT", "preuve": f"garde-fou : fin sur «{sents[j]['text'][-40:]}»"}
    return out


def falsify(run, sents, i, j, it):
    before, after = ctx(sents, i, j)
    T = lambda ks: " ".join(sents[k]["text"] for k in ks) or "(rien : bord de la vidéo)"
    user = (f"CONTEXTE AVANT :\n«{T(before)}»\n\n=== CLIP ({sents[j]['e']-sents[i]['s']:.0f} s) ===\n"
            f"«{T(range(i, j + 1))}»\n=== FIN DU CLIP ===\n\nCONTEXTE APRÈS :\n«{T(after)}»")
    try:
        llm = call_json(run, f"falsificateur_it{it}", skill("falsificateur"), user, SCHEMA, max_tokens=900)
    except RuntimeError as e:
        llm = {"erreur": str(e)}
    derived = {}
    if "erreur" in llm:
        derived = {k: {"verdict": "INCONNU", "preuve": f"LLM indisponible : {llm['erreur'][:80]}"} for k in CRIT}
        kc = ks = None
    else:
        derived["contredit_apres"], kc = from_quote(llm.get("correction_apres", ""), sents, after, "correction")
        derived["coupe_mi_idee"], ks = from_quote(llm.get("suite_necessaire", ""), sents, after, "suite indispensable")
        for k in ("hors_contexte", "info_prealable"):
            derived[k] = llm.get(k) if isinstance(llm.get(k), dict) else {"verdict": "INCONNU", "preuve": "réponse absente"}
    g = guard(sents, i, j, after)
    final = {}
    for k in CRIT:
        a = derived[k]
        a = {"verdict": a.get("verdict") if a.get("verdict") in RANK else "INCONNU", "preuve": a.get("preuve", "")}
        b = g.get(k)
        final[k] = dict(a, source="LLM")
        if b and RANK[b["verdict"]] > RANK[a["verdict"]]:
            final[k] = {"verdict": b["verdict"], "preuve": b["preuve"], "source": "garde-fou lexical", "llm_disait": a}
    return {"i": i, "j": j, "s": sents[i]["s"], "e": sents[j]["e"], "llm": llm, "garde_fou": g, "final": final,
            "after": after, "k_correction": kc, "k_suite": ks,
            "llm_derive": {k: derived[k]["verdict"] for k in CRIT}}


def adjust(sents, r):
    """Nouvelles bornes (i, j) ou None. Étend la fin jusqu'à la correction/conclusion, ou le début vers l'arrière."""
    i, j, f = r["i"], r["j"], r["final"]
    if "CONFLIT" in (f["contredit_apres"]["verdict"], f["coupe_mi_idee"]["verdict"]):
        ks = [k for k in (r.get("k_correction"), r.get("k_suite")) if k is not None]
        target = max(ks) if ks else None
        hit = r["garde_fou"].get("contredit_apres", {}).get("k")
        if hit is not None:  # inclure la correction + la phrase qui la conclut
            target = max(target or 0, min(hit + 1, r["after"][-1]))
        if target is None and r["after"]:
            target = r["after"][0]
        if target is None:
            return None
        nj, ni = target, i
        while sents[nj]["e"] - sents[ni]["s"] > 90 and ni < nj:
            ni += 1
        if sents[nj]["e"] - sents[ni]["s"] < 20:
            return None
        return ni, nj
    if "CONFLIT" in (f["info_prealable"]["verdict"], f["hors_contexte"]["verdict"]) and i > 0:
        ni = i - 1
        while ni > 0 and sents[j]["e"] - sents[ni - 1]["s"] <= 90 and sents[i]["s"] - sents[ni]["s"] < 8:
            ni -= 1
        if sents[j]["e"] - sents[ni]["s"] <= 90:
            return ni, j
    return None


def n_conflit(r):
    return sum(v["verdict"] == "CONFLIT" for v in r["final"].values())


def run_agent(run, sents, ranked, max_it=3):
    log, ci, bounds, adjusted = [], 0, (ranked[0]["i"], ranked[0]["j"]), False
    for it in range(1, max_it + 1):
        c = ranked[ci]
        progress(run, "falsificateur", 70 + 5 * it, f"itération {it}/{max_it} ({c['id']})")
        r = falsify(run, sents, *bounds, it)
        r.update(iteration=it, candidat=c["id"], score=c["score"])
        log.append(r)
        jsave(os.path.join(run, "falsification.json"), log)
        if n_conflit(r) == 0:
            r["statut"] = "PROUVÉ" if all(v["verdict"] == "PROUVÉ" for v in r["final"].values()) else "INCONNU"
            r["avertissement"] = None if r["statut"] == "PROUVÉ" else "Aucun CONFLIT trouvé, mais au moins un critère non prouvé (INCONNU)."
            return r, c, log
        nb = adjust(sents, r) if not adjusted else None  # 1 seul ajustement par candidat, puis on passe au suivant
        if nb and nb != bounds:
            adjusted = True
            r["action"] = f"bornes ajustées -> phrases {nb[0]}..{nb[1]}"
            bounds = nb
        elif ci + 1 < len(ranked):
            ci += 1; bounds = (ranked[ci]["i"], ranked[ci]["j"]); adjusted = False
            r["action"] = f"candidat suivant {ranked[ci]['id']}"
        else:
            r["action"] = "plus de candidat"; break
        jsave(os.path.join(run, "falsification.json"), log)
    best = min(log, key=lambda r: (n_conflit(r), -r["score"]))
    best["statut"] = "INCONNU"
    best["avertissement"] = ("AVERTISSEMENT : aucun candidat n'a passé le Falsificateur en 3 itérations. "
                             "Ce clip est le moins mauvais, il contient encore un ou plusieurs CONFLIT. Ne pas publier sans vérifier.")
    c = next(x for x in ranked if x["id"] == best["candidat"])
    jsave(os.path.join(run, "falsification.json"), log)
    return best, c, log
