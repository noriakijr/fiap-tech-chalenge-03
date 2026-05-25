"""Testes de contrato para POST /v1/consulta (Task 6.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from tests.integration.conftest import SESSAO_ID, make_mock_orq, RESPOSTA_PADRAO


def test_consulta_retorna_200(client) -> None:
    response = client.post(
        "/v1/consulta",
        json={"texto": "O que é pneumonia?", "sessao_id": SESSAO_ID},
    )
    assert response.status_code == 200


def test_consulta_retorna_estrutura_resposta_clinica(client) -> None:
    response = client.post(
        "/v1/consulta",
        json={"texto": "O que é pneumonia?", "sessao_id": SESSAO_ID},
    )
    body = response.json()
    assert "texto_resposta" in body
    assert "fontes" in body
    assert "avisos" in body
    assert "confianca" in body
    assert "timestamp" in body


def test_consulta_texto_vazio_retorna_422(client) -> None:
    response = client.post(
        "/v1/consulta",
        json={"texto": "", "sessao_id": SESSAO_ID},
    )
    assert response.status_code == 422


def test_consulta_sem_sessao_id_retorna_422(client) -> None:
    response = client.post(
        "/v1/consulta",
        json={"texto": "pergunta"},
    )
    assert response.status_code == 422


def test_consulta_sessao_inexistente_retorna_404(client) -> None:
    response = client.post(
        "/v1/consulta",
        json={"texto": "pergunta", "sessao_id": "nao-existe"},
    )
    assert response.status_code == 404


def test_consulta_chama_processar_pergunta(client, mock_orq, test_store) -> None:
    client.post(
        "/v1/consulta",
        json={"texto": "sepse?", "sessao_id": SESSAO_ID},
    )
    mock_orq.processar_pergunta.assert_called_once()
    args = mock_orq.processar_pergunta.call_args
    assert args[0][0] == "sepse?"  # primeiro argumento posicional é o texto


def test_consulta_sem_rag_retorna_503(client_no_orq) -> None:
    response = client_no_orq.post(
        "/v1/consulta",
        json={"texto": "teste", "sessao_id": SESSAO_ID},
    )
    assert response.status_code == 503


def test_consulta_corpo_ausente_retorna_422(client) -> None:
    response = client.post("/v1/consulta")
    assert response.status_code == 422


def test_consulta_aviso_apoio_decisao_presente(client) -> None:
    response = client.post(
        "/v1/consulta",
        json={"texto": "pergunta clínica", "sessao_id": SESSAO_ID},
    )
    avisos = response.json()["avisos"]
    tipos = [a["tipo"] for a in avisos]
    assert "apoio_decisao" in tipos
