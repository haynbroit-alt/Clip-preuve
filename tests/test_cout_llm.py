"""Journal de coût : chaque appel LLM est tracé, la clé n'est jamais écrite."""

import io
import json

import pytest

from agents import llm


def _chat(content, prompt=10, completion=5):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


def _installer(monkeypatch, payloads):
    reqs = []

    def _open(req, timeout=600):
        reqs.append(req)
        body = payloads[len(reqs) - 1]
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", _open)
    return reqs


def _lignes(run):
    return [json.loads(line) for line in (run / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()]


def test_appel_local_coute_zero_et_extrait_le_json(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "PRICE", 9.0)
    reqs = _installer(monkeypatch, [_chat('texte avant {"valeur": 2} texte après', 12, 3)])
    out = llm.call_json(str(tmp_path), "juge", "système", "utilisateur", {"type": "object"})
    assert out == {"valeur": 2}
    rec = _lignes(tmp_path)[0]
    assert rec["provider"] == "local-llama.cpp"
    assert rec["model"] == "mock.gguf"
    assert rec["role"] == "juge"
    assert rec["prompt_tokens"] == 12
    assert rec["completion_tokens"] == 3
    assert rec["cost_eur"] == 0.0
    assert rec["ok"] is True
    assert rec["attempt"] == 0
    body = json.loads(reqs[0].data.decode())
    assert body["temperature"] == 0
    assert body["response_format"]["schema"] == {"type": "object"}
    assert body["repeat_penalty"] == 1.1
    assert reqs[0].get_header("Authorization") is None


def test_openrouter_gratuit_et_payant_sans_fuite_de_cle(tmp_path, monkeypatch):
    cle = "sk-test-not-a-real-key"
    monkeypatch.setattr(llm, "OR_KEY", cle)
    monkeypatch.setattr(llm, "OR_MODEL", "vendor/model:free")
    monkeypatch.setattr(llm, "PRICE", 4.0)
    (tmp_path / "free").mkdir()
    reqs = _installer(monkeypatch, [_chat("{}", 8, 2)])
    llm.call_json(str(tmp_path / "free"), "falsificateur_it1", "s", "u", {})
    assert _lignes(tmp_path / "free")[0]["cost_eur"] == 0.0
    assert reqs[0].get_header("Authorization") == "Bearer " + cle
    assert cle not in (tmp_path / "free" / "llm_calls.jsonl").read_text(encoding="utf-8")
    assert "Bearer" not in (tmp_path / "free" / "llm_calls.jsonl").read_text(encoding="utf-8")

    (tmp_path / "paid").mkdir()
    monkeypatch.setattr(llm, "OR_MODEL", "vendor/paid-model")
    monkeypatch.setattr(llm, "PRICE", 3.0)
    _installer(monkeypatch, [_chat('{"ok": true}', 100, 50)])
    llm.call_json(str(tmp_path / "paid"), "juge", "s", "u", {})
    rec = _lignes(tmp_path / "paid")[0]
    assert rec["cost_eur"] == pytest.approx(150 * 3.0 / 1e6)
    assert rec["provider"] == "openrouter"
    assert cle not in (tmp_path / "paid" / "llm_calls.jsonl").read_text(encoding="utf-8")


def test_json_invalide_puis_succes_au_second_essai(tmp_path, monkeypatch):
    reqs = _installer(monkeypatch, [_chat("pas du json", 1, 1), _chat('{"ok": 1}', 4, 2)])
    out = llm.call_json(str(tmp_path), "juge", "s", "u", {})
    assert out == {"ok": 1}
    rows = _lignes(tmp_path)
    assert [r["ok"] for r in rows] == [False, True]
    assert [r["attempt"] for r in rows] == [0, 1]
    assert json.loads(reqs[1].data.decode())["temperature"] == 0.3


def test_trois_echecs_levent_et_sont_journalises(tmp_path, monkeypatch):
    _installer(monkeypatch, [_chat("non")] * 3)
    with pytest.raises(RuntimeError, match="ÉCHEC appel LLM"):
        llm.call_json(str(tmp_path), "juge", "s", "u", {})
    rows = _lignes(tmp_path)
    assert len(rows) == 3
    assert all(r["ok"] is False for r in rows)


def test_sans_dossier_de_run_rien_n_est_ecrit(tmp_path, monkeypatch):
    _installer(monkeypatch, [_chat('{"ok": true}')])
    assert llm.call_json(None, "juge", "s", "u", {}) == {"ok": True}
    assert not (tmp_path / "llm_calls.jsonl").exists()
