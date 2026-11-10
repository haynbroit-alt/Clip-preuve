"""Journal structuré (une ligne JSON par événement). N'écrit jamais de clé ni de prompt."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_NOM = "clip_preuve"
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Sérialise le record et ses champs `extra` en un objet JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for cle, valeur in record.__dict__.items():
            if cle not in _STANDARD and not cle.startswith("_"):
                payload[cle] = valeur
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class _StderrHandler(logging.StreamHandler[Any]):
    """Écrit toujours sur le stderr courant (compatible avec la capture de pytest)."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)


def logger() -> logging.Logger:
    """Logger du processus. Idempotent : un seul handler stderr."""
    journal = logging.getLogger(_NOM)
    if not journal.handlers:
        handler = _StderrHandler()
        handler.setFormatter(JsonFormatter())
        journal.addHandler(handler)
        journal.setLevel(logging.INFO)
        journal.propagate = False
    return journal
