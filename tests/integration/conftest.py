"""Fixtures compartilhadas para testes de integração da API (Fase 6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_orchestrador, get_session_store
from app.main import create_app
from app.models.domain import (
    Aviso,
    RespostaClinica,
    SessaoMedico,
    TipoAviso,
)

# Constantes reutilizadas nos testes
SESSAO_ID = "sessao-integracao-001"
MEDICO_ID = "DR-TESTE"

RESPOSTA_PADRAO = RespostaClinica(
    texto_resposta="Resposta clínica de teste.",
    fontes=[],
    avisos=[
        Aviso(
            tipo=TipoAviso.APOIO_DECISAO,
            mensagem="Este sistema é um auxílio à decisão clínica.",
            destaque=False,
        )
    ],
    confianca=0.85,
)


def make_mock_orq(
    processar: RespostaClinica | None = None,
    handle_conduta: RespostaClinica | None = None,
    handle_exames: RespostaClinica | None = None,
    handle_tratamento: RespostaClinica | None = None,
) -> MagicMock:
    """Cria um mock de OrquestradorClinico com respostas configuráveis."""
    orq = MagicMock()
    orq.processar_pergunta = AsyncMock(return_value=processar or RESPOSTA_PADRAO)
    orq.handle_sugestao_conduta = MagicMock(return_value=handle_conduta or RESPOSTA_PADRAO)
    orq.handle_verificacao_exames = AsyncMock(return_value=handle_exames or RESPOSTA_PADRAO)
    orq.handle_sugestao_tratamento = AsyncMock(return_value=handle_tratamento or RESPOSTA_PADRAO)
    return orq


def make_store(sessao_id: str = SESSAO_ID, id_medico: str = MEDICO_ID) -> dict:
    """Cria um store de sessões pré-populado."""
    sessao = SessaoMedico(id_sessao=sessao_id, id_medico=id_medico)
    return {sessao_id: sessao}


@pytest.fixture()
def test_store() -> dict:
    return make_store()


@pytest.fixture()
def mock_orq() -> MagicMock:
    return make_mock_orq()


@pytest.fixture()
def client(test_store, mock_orq) -> TestClient:
    """TestClient com orquestrador mockado e store de teste."""
    app = create_app()
    app.dependency_overrides[get_orchestrador] = lambda: mock_orq
    app.dependency_overrides[get_session_store] = lambda: test_store
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


@pytest.fixture()
def client_no_orq(test_store) -> TestClient:
    """TestClient sem override do orquestrador — útil para testar 503."""
    app = create_app()
    app.dependency_overrides[get_session_store] = lambda: test_store
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
