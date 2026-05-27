import json
import logging

from app.core.logging import configure_logging


def test_configure_logging_emits_json(capsys) -> None:
    configure_logging("DEBUG")
    logger = logging.getLogger("test_logger")
    logger.info("ola_mundo", extra={"user_id": "abc"})

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "Nenhuma linha de log foi emitida"

    payload = json.loads(captured[-1])
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test_logger"
    assert payload["message"] == "ola_mundo"
    assert payload["user_id"] == "abc"
    assert "timestamp" in payload


def test_configure_logging_is_idempotent() -> None:
    configure_logging("INFO")
    handlers_before = list(logging.getLogger().handlers)
    configure_logging("INFO")
    handlers_after = list(logging.getLogger().handlers)

    assert len(handlers_after) == len(handlers_before) == 1
