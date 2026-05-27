import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import (
    BaseAppError,
    DatabaseUnavailableError,
    InteractionServiceUnavailableError,
    KnowledgeBaseUnavailableError,
    PatientNotFoundError,
    PLNTimeoutError,
    register_exception_handlers,
)


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise/{code}")
    async def raise_route(code: str) -> None:
        mapping: dict[str, type[BaseAppError]] = {
            "kb": KnowledgeBaseUnavailableError,
            "pln": PLNTimeoutError,
            "patient": PatientNotFoundError,
            "interaction": InteractionServiceUnavailableError,
            "db": DatabaseUnavailableError,
        }
        if code in mapping:
            raise mapping[code]()
        if code == "unexpected":
            raise RuntimeError("boom")
        raise BaseAppError()

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "path, expected_status, expected_code",
    [
        ("/raise/kb", 503, "knowledge_base_unavailable"),
        ("/raise/pln", 504, "pln_timeout"),
        ("/raise/patient", 404, "patient_not_found"),
        ("/raise/interaction", 503, "interaction_service_unavailable"),
        ("/raise/db", 503, "database_unavailable"),
    ],
)
def test_known_exceptions_map_to_correct_status_and_code(
    client: TestClient, path: str, expected_status: int, expected_code: str
) -> None:
    response = client.get(path)
    assert response.status_code == expected_status
    body = response.json()
    assert body["error"]["code"] == expected_code
    assert body["error"]["message"]


def test_unhandled_exception_returns_500(client: TestClient) -> None:
    response = client.get("/raise/unexpected")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"


def test_base_app_error_includes_detalhes(client: TestClient) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/detalhes")
    async def detalhes_route() -> None:
        raise PatientNotFoundError(numero_prontuario="12345")

    local_client = TestClient(app, raise_server_exceptions=False)
    response = local_client.get("/detalhes")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["detalhes"] == {"numero_prontuario": "12345"}


def test_messages_are_in_pt_br() -> None:
    for exc_cls in (
        KnowledgeBaseUnavailableError,
        PLNTimeoutError,
        PatientNotFoundError,
        InteractionServiceUnavailableError,
        DatabaseUnavailableError,
    ):
        msg = exc_cls.default_message.lower()
        assert any(token in msg for token in ("tente", "verifique", "paciente", "serviço", "banco")), (
            f"Mensagem de {exc_cls.__name__} não parece estar em pt-BR: {msg!r}"
        )
