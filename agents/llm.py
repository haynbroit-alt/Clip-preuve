"""Client LLM unique (local llama.cpp par défaut, OpenRouter :free si clé en env).
Chaque appel est loggé dans <run>/llm_calls.jsonl avec tokens, durée et coût en €.
Cas limites : serveur local éteint -> RuntimeError claire (ÉCHEC) ; JSON invalide/tronqué -> 2 relances (temp 0.3), puis critères INCONNU (jamais PROUVÉ par défaut).
Coût : local = 0 € (électricité non comptée) ; OpenRouter ':free' = 0 € ; autre modèle = prix env CLIP_PRICE_EUR_PER_MTOK.
"""
import json, os, time, urllib.request

LOCAL_URL = os.environ.get("CLIP_LLM_URL", "http://127.0.0.1:8088/v1/chat/completions")
OR_KEY = os.environ.get("OPENROUTER_API_KEY")  # jamais affichée
OR_MODEL = os.environ.get("CLIP_OR_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
PRICE = float(os.environ.get("CLIP_PRICE_EUR_PER_MTOK", "0"))


_LOCAL_NAME = None


def backend():
    """(fournisseur, modèle). Le nom du modèle local est lu sur le serveur llama.cpp (fichier réellement chargé)."""
    global _LOCAL_NAME
    if OR_KEY:
        return ("openrouter", OR_MODEL)
    if _LOCAL_NAME is None:
        try:
            d = json.load(urllib.request.urlopen(LOCAL_URL.replace("/chat/completions", "/models"), timeout=5))
            _LOCAL_NAME = os.path.realpath(d["data"][0]["id"]).split("/")[-1]
        except Exception:  # noqa
            _LOCAL_NAME = "inconnu"
    return ("local-llama.cpp", _LOCAL_NAME)


def call_json(run_dir, role, system, user, schema, max_tokens=400):
    prov, model = backend()
    body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0, "max_tokens": max_tokens}
    if prov == "openrouter":
        url, headers = "https://openrouter.ai/api/v1/chat/completions", {"Authorization": "Bearer " + OR_KEY}
        body["model"] = model
        body["response_format"] = {"type": "json_object"}
    else:
        url, headers = LOCAL_URL, {}
        body["response_format"] = {"type": "json_object", "schema": schema}
        body["repeat_penalty"] = 1.1  # évite les boucles de répétition du petit modèle
    headers["Content-Type"] = "application/json"
    last_err = None
    for attempt in range(3):  # 3 essais ; à partir du 2e, température 0.3 pour sortir d'une boucle déterministe
        if attempt: body["temperature"] = 0.3
        t = time.monotonic()
        d, txt = {}, ""
        try:
            req = urllib.request.Request(url, json.dumps(body).encode(), headers)
            d = json.load(urllib.request.urlopen(req, timeout=600))
            txt = d["choices"][0]["message"]["content"]
            out = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        except Exception as e:  # noqa
            last_err = e
            out = None
        u = d.get("usage", {})
        pt, ct = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        cost = 0.0 if (prov == "local-llama.cpp" or model.endswith(":free")) else (pt + ct) * PRICE / 1e6
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "role": role, "provider": prov, "model": model,
               "prompt_tokens": pt, "completion_tokens": ct, "seconds": round(time.monotonic() - t, 2),
               "cost_eur": cost, "ok": out is not None, "attempt": attempt, "raw": txt[:2000]}
        if run_dir:
            with open(os.path.join(run_dir, "llm_calls.jsonl"), "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if out is not None:
            return out
    raise RuntimeError(f"ÉCHEC appel LLM ({role}) : {last_err}")
