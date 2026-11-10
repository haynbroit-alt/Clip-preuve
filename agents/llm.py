"""Client LLM unique (local llama.cpp par défaut, OpenRouter :free si clé en env).

Chaque appel est loggé dans <run>/llm_calls.jsonl avec tokens, durée et coût en €.
Cas limites : serveur local éteint -> RuntimeError claire (ÉCHEC) ; JSON invalide ou
tronqué -> 2 relances (temp 0.3), puis l'appel échoue (jamais PROUVÉ par défaut).
Coût : local = 0 € (électricité non comptée) ; OpenRouter ':free' = 0 € ;
autre modèle = prix env CLIP_PRICE_EUR_PER_MTOK.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, cast

from .log import logger

LOCAL_URL = os.environ.get("CLIP_LLM_URL", "http://127.0.0.1:8088/v1/chat/completions")
OR_KEY = os.environ.get("OPENROUTER_API_KEY")  # jamais affichée
OR_MODEL = os.environ.get("CLIP_OR_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
PRICE = float(os.environ.get("CLIP_PRICE_EUR_PER_MTOK", "0"))

_LOCAL_NAME: str | None = None


def backend() -> tuple[str, str]:
    """(fournisseur, modèle). Le nom local est lu sur le serveur llama.cpp."""
    global _LOCAL_NAME
    if OR_KEY:
        return ("openrouter", OR_MODEL)
    if _LOCAL_NAME is None:
        try:
            url = LOCAL_URL.replace("/chat/completions", "/models")
            charge = json.load(urllib.request.urlopen(url, timeout=5))
            _LOCAL_NAME = os.path.realpath(charge["data"][0]["id"]).split("/")[-1]
        except Exception:
            _LOCAL_NAME = "inconnu"
    return ("local-llama.cpp", _LOCAL_NAME)


def call_json(
    run_dir: str | None,
    role: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int = 400,
) -> dict[str, Any]:
    prov, model = backend()
    body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    headers: dict[str, str]
    if prov == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": "Bearer " + (OR_KEY or "")}
        body["model"] = model
        body["response_format"] = {"type": "json_object"}
    else:
        url = LOCAL_URL
        headers = {}
        body["response_format"] = {"type": "json_object", "schema": schema}
        body["repeat_penalty"] = 1.1  # évite les boucles de répétition du petit modèle
    headers["Content-Type"] = "application/json"
    last_err: BaseException | None = None
    for attempt in range(3):
        # à partir du 2e essai, température 0.3 pour sortir d'une boucle déterministe
        if attempt:
            body["temperature"] = 0.3
        debut = time.monotonic()
        d: dict[str, Any] = {}
        txt = ""
        out: Any = None
        try:
            req = urllib.request.Request(url, json.dumps(body).encode(), headers)
            charge = json.load(urllib.request.urlopen(req, timeout=600))
            d = charge
            txt = d["choices"][0]["message"]["content"]
            out = json.loads(txt[txt.find("{") : txt.rfind("}") + 1])
        except Exception as exc:
            last_err = exc
            out = None
        usage = d.get("usage", {})
        pt = usage.get("prompt_tokens", 0)
        ct = usage.get("completion_tokens", 0)
        if prov == "local-llama.cpp" or model.endswith(":free"):
            cost = 0.0
        else:
            cost = (pt + ct) * PRICE / 1e6
        rec = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "role": role,
            "provider": prov,
            "model": model,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "seconds": round(time.monotonic() - debut, 2),
            "cost_eur": cost,
            "ok": out is not None,
            "attempt": attempt,
            "raw": txt[:2000],
        }
        if run_dir:
            with open(os.path.join(run_dir, "llm_calls.jsonl"), "a", encoding="utf-8") as handle:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        logger().info(
            "appel llm",
            extra={
                "role": role,
                "provider": prov,
                "model": model,
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "cost_eur": cost,
                "ok": out is not None,
                "attempt": attempt,
            },
        )
        if out is not None:
            return cast(dict[str, Any], out)
    raise RuntimeError(f"ÉCHEC appel LLM ({role}) : {last_err}")
