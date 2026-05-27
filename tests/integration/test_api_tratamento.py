"""Testes de contrato para POST /v1/pacientes/{numero_prontuario}/tratamento (Task 6.4)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.core.exceptions import InteractionServiceUnavailableError, PatientNotFoundError
from app.models.domain import Aviso, RespostaClinica, TipoAviso
from tests.integration.conftest import SESSAO_ID, make_mock_orq, make_store


def _client_customizado(orq):
    from fastapi.testclient import TestClient
    from app.api.deps import get_orchestrador, get_session_store
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_orchestrador] = lambda: orq
    app.dependency_overrides[get_session_store] = lambda: make_store()
    return TestClient(app, raise_server_exceptions=False)


def test_tratamento_retorna_200(client) -> None:
    response = client.post(
        "/v1/pacientes/PRT-001/tratamento",
        json={"sessao_id": SESSAO_ID},
    )
    assert response.status_code == 200


def test_tratamento_retorna_estrutura_resposta_clinica(client) -> None:
    response = client.post(
        "/v1/pacientes/PRT-001/tratamento",
        json={"sessao_id": SESSAO_ID},
    )
    body = response.json()
    assert "texto_resposta" in body
    assert "fontes" in body
    assert "avisos" in body
    assert "confianca" in body


def test_tratamento_sessao_inexistente_retorna_404(client) -> None:
    response = client.post(
        "/v1/pacientes/PRT-001/tratamento",
        json={"sessao_id": "invalida"},
    )
    assert response.status_code == 404


def test_tratamento_paciente_inexistente_retorna_404() -> None:
    orq = make_mock_orq()
    orq.handle_sugestao_tratamento = AsyncMock(
        side_effect=PatientNotFoundError("Paciente não encontrado.")
    )
    tc = _client_customizado(orq)
    response = tc.post(
        "/v1/pacientes/INEXISTENTE/tratamento",
        json={"sessao_id": SESSAO_ID},
    )
    assert response.status_code == 404


def test_tratamento_servico_interacoes_indisponivel_retorna_503() -> None:
    """Req 4.7: bloqueia quando serviço de interações indisponível."""
    orq = make_mock_orq()
    orq.handle_sugestao_tratamento = AsyncMock(
        side_effect=InteractionServiceUnavailableError()
    )
    tc = _client_customizado(orq)
    response = tc.post(
        "/v1/pacientes/PRT-001/tratamento",
        json={"sessao_id": SESSAO_ID},
    )
    assert response.status_code == 503


def test_tratamento_prontuario_incompleto_retorna_200_com_mensagem() -> None:
    """Req 4.9: bloqueio de sugestão com mensagem clara (não erro HTTP)."""
    resposta_bloqueio = RespostaClinica(
        texto_resposta=(
            "Prontuário incompleto. Campos obrigatórios ausentes: "
            "diagnostico_ativo, alergias."
        ),
        fontes=[],
        avisos=[Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False)],
        confianca=0.0,
    )
    orq = make_mock_orq(handle_tratamento=resposta_bloqueio)
    tc = _client_customizado(orq)
    response = tc.post(
        "/v1/pacientes/PRT-003/tratamento",
        json={"sessao_id": SESSAO_ID},
    )
    assert response.status_code == 200
    assert "incompleto" in response.json()["texto_resposta"].lower()


def test_tratamento_numero_prontuario_passado_ao_handler(client, mock_orq) -> None:
    client.post(
        "/v1/pacientes/PRT-ESPECIFICO/tratamento",
        json={"sessao_id": SESSAO_ID},
    )
    mock_orq.handle_sugestao_tratamento.assert_called_once()
    nlu_arg = mock_orq.handle_sugestao_tratamento.call_args[0][1]
    assert nlu_arg.entidades["numero_prontuario"] == "PRT-ESPECIFICO"


def test_tratamento_medicamentos_sugeridos_passados_ao_handler(client, mock_orq) -> None:
    client.post(
        "/v1/pacientes/PRT-001/tratamento",
        json={"sessao_id": SESSAO_ID, "medicamentos_sugeridos": ["Warfarina", "Aspirina"]},
    )
    nlu_arg = mock_orq.handle_sugestao_tratamento.call_args[0][1]
    assert nlu_arg.entidades["medicamentos_mencionados"] == ["Warfarina", "Aspirina"]


def test_tratamento_sem_rag_retorna_503(client_no_orq) -> None:
    response = client_no_orq.post(
        "/v1/pacientes/PRT-001/tratamento",
        json={"sessao_id": SESSAO_ID},
    )
    assert response.status_code == 503


def test_tratamento_sem_sessao_id_retorna_422(client) -> None:
    response = client.post("/v1/pacientes/PRT-001/tratamento", json={})
    assert response.status_code == 422


def test_tratamento_aviso_apoio_decisao_presente(client) -> None:
    response = client.post(
        "/v1/pacientes/PRT-001/tratamento",
        json={"sessao_id": SESSAO_ID},
    )
    tipos = [a["tipo"] for a in response.json()["avisos"]]
    assert "apoio_decisao" in tipos
