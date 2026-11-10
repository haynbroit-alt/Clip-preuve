"""Les tests ne contactent ni llama.cpp, ni OpenRouter, ni faster-whisper."""

import pytest

from agents import llm


@pytest.fixture(autouse=True)
def llm_hors_ligne(monkeypatch):
    monkeypatch.setattr(llm, "OR_KEY", None)
    monkeypatch.setattr(llm, "_LOCAL_NAME", "mock.gguf")
    monkeypatch.setattr(llm, "PRICE", 0.0)
