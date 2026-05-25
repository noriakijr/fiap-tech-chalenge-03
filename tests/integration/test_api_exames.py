"""Testes de contrato para GET /v1/pacientes/{numero_prontuario}/exames-pendentes (Task 6.3)."""

from __future__ import annotations

from app.core.exceptions import PatientNotFoundError
from app.models.domain import (
    Aviso,
    RespostaClinica,
    TipoAviso,
)
from tests.integration.conftest import make_mock_orq, make_store


def _client_com_orq_customizado(orq):
    """Helper para criar TestClient com orquestrador específico."""
    from fastapi.testclient import TestClient
    from app.api.deps import get_orchestrador, get_session_store
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_orchestrador] = lambda: orq
    app.dependency_overrides[get_session_store] = lambda: make_store()
    return TestClient(app, raise_server_exceptions=False)


def test_exames_retorna_200(client) -> None:
    response = client.get("/v1/pacientes/PRT-001/exames-pendentes")
    assert response.status_code == 200


def test_exames_retorna_estrutura_resposta_clinica(client) -> None:
    response = client.get("/v1/pacientes/PRT-001/exames-pendentes")
    body = response.json()
    assert "texto_resposta" in body
    assert "fontes" in body
    assert "avisos" in body
    assert "confianca" in body


def test_exames_numero_prontuario_passado_ao_handler(client, mock_orq) -> None:
    client.get("/v1/pacientes/PRT-ESPECIFICO/exames-pendentes")
    mock_orq.handle_verificacao_exames.assert_called_once()
    nlu_arg = mock_orq.handle_verificacao_exames.call_args[0][0]
    assert nlu_arg.entidades["numero_prontuario"] == "PRT-ESPECIFICO"


def test_exames_paciente_inexistente_retorna_404() -> None:
    from unittest.mock import AsyncMock

    orq = make_mock_orq()
    orq.handle_verificacao_exames = AsyncMock(
        side_effect=PatientNotFoundError("Paciente não encontrado.")
    )
    tc = _client_com_orq_customizado(orq)
    response = tc.get("/v1/pacientes/INEXISTENTE/exames-pendentes")
    assert response.status_code == 404


def test_exames_404_corpo_em_pt_br() -> None:
    from unittest.mock import AsyncMock

    orq = make_mock_orq()
    orq.handle_verificacao_exames = AsyncMock(
        side_effect=PatientNotFoundError()
    )
    tc = _client_com_orq_customizado(orq)
    response = tc.get("/v1/pacientes/XXX/exames-pendentes")
    body = response.json()
    assert "error" in body
    assert "message" in body["error"]
    # mensagem deve estar em português
    msg = body["error"]["message"].lower()
    assert any(token in msg for token in ("paciente", "prontuário", "verifique"))


def test_exames_sem_pendentes_retorna_200_com_mensagem() -> None:
    resposta_sem_exames = RespostaClinica(
        texto_resposta="Não há exames pendentes para o paciente PRT-002.",
        fontes=[],
        avisos=[Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False)],
        confianca=1.0,
    )
    orq = make_mock_orq(handle_exames=resposta_sem_exames)
    tc = _client_com_orq_customizado(orq)
    response = tc.get("/v1/pacientes/PRT-002/exames-pendentes")
    assert response.status_code == 200
    assert "pendentes" in response.json()["texto_resposta"].lower()


def test_exames_sem_rag_retorna_503(client_no_orq) -> None:
    response = client_no_orq.get("/v1/pacientes/PRT-001/exames-pendentes")
    assert response.status_code == 503
