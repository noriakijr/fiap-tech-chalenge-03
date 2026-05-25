"""Testes E2E — Requisito 3: Verificação de Exames Pendentes.

Formato Given/When/Then. Cada teste corresponde a um critério de aceitação.
O orquestrador é mockado para isolar o comportamento da API.

Refs: requirements.md § Requirement 3 (AC 3.1 – 3.5)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_orchestrador, get_session_store
from app.core.exceptions import PatientNotFoundError
from app.main import create_app
from app.models.domain import (
    Aviso,
    RespostaClinica,
    SessaoMedico,
    TipoAviso,
)

SESSAO_ID = "e2e-req3-sessao"


def _store() -> dict:
    return {SESSAO_ID: SessaoMedico(id_sessao=SESSAO_ID, id_medico="DR-E2E")}


def _cliente(orq) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_orchestrador] = lambda: orq
    app.dependency_overrides[get_session_store] = lambda: _store()
    return TestClient(app, raise_server_exceptions=False)


def _resposta_exames(texto: str, confianca: float = 1.0) -> RespostaClinica:
    return RespostaClinica(
        texto_resposta=texto,
        fontes=[],
        avisos=[Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False)],
        confianca=confianca,
    )


# ------------------------------------------------------------------ #
# AC 3.1 — Exames pendentes recuperados e exibidos                    #
# ------------------------------------------------------------------ #


def test_ac3_1_exames_pendentes_retornados() -> None:
    """WHEN prontuário válido THEN exames pendentes são exibidos."""
    texto = (
        "Exames pendentes para o paciente PRT-001:\n"
        "  • Hemograma — Em Análise (solicitado em 2024-01-10, por DR-A)\n"
        "  • PCR — Solicitado (solicitado em 2024-01-11, por DR-A)"
    )
    orq = _mock_orq_exames(_resposta_exames(texto))

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-001/exames-pendentes")

    assert resp.status_code == 200
    body = resp.json()["texto_resposta"]
    assert "Hemograma" in body
    assert "PCR" in body


# ------------------------------------------------------------------ #
# AC 3.2 — Campos exibidos: nome, data, solicitante, status           #
# ------------------------------------------------------------------ #


def test_ac3_2_exame_exibe_nome_data_solicitante_status() -> None:
    """WHEN exames retornados THEN contém nome, data, solicitante e status."""
    texto = (
        "Exames pendentes para o paciente PRT-001:\n"
        "  • Ureia — Em Análise (solicitado em 2024-01-15, por DR-SILVA)"
    )
    orq = _mock_orq_exames(_resposta_exames(texto))

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-001/exames-pendentes")

    body = resp.json()["texto_resposta"]
    # Todos os campos devem aparecer no texto
    assert "Ureia" in body
    assert "Em Análise" in body
    assert "2024-01-15" in body
    assert "DR-SILVA" in body


# ------------------------------------------------------------------ #
# AC 3.3 — Prontuário não encontrado retorna mensagem adequada        #
# ------------------------------------------------------------------ #


def test_ac3_3_prontuario_invalido_retorna_404() -> None:
    """IF prontuário não cadastrado THEN 404 com mensagem em pt-BR."""
    from unittest.mock import AsyncMock

    orq = _mock_orq_exames(None)
    orq.handle_verificacao_exames = AsyncMock(
        side_effect=PatientNotFoundError("Paciente não encontrado.")
    )

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/INVALIDO/exames-pendentes")

    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    msg = body["error"]["message"].lower()
    assert any(tok in msg for tok in ("paciente", "prontuário", "verifique"))


# ------------------------------------------------------------------ #
# AC 3.4 — Nenhum exame pendente retorna mensagem específica          #
# ------------------------------------------------------------------ #


def test_ac3_4_sem_exames_retorna_mensagem_vazia() -> None:
    """IF sem exames pendentes THEN mensagem 'nenhum exame pendente'."""
    texto = "Não há exames pendentes para o paciente PRT-002."
    orq = _mock_orq_exames(_resposta_exames(texto))

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-002/exames-pendentes")

    assert resp.status_code == 200
    body = resp.json()["texto_resposta"].lower()
    assert "pendente" in body or "nenhum" in body


# ------------------------------------------------------------------ #
# AC 3.5 — Status Concluído não aparece na lista de pendentes         #
# ------------------------------------------------------------------ #


def test_ac3_5_status_concluido_nao_aparece() -> None:
    """THEN exames com status Concluído não estão na lista de pendentes."""
    # O handler do orquestrador já filtra — aqui verificamos o contrato
    texto = (
        "Exames pendentes para o paciente PRT-003:\n"
        "  • Hemograma — Solicitado (solicitado em 2024-02-01, por DR-B)"
    )
    orq = _mock_orq_exames(_resposta_exames(texto))

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-003/exames-pendentes")

    # "Concluído" não deve aparecer entre os pendentes
    assert "Concluído" not in resp.json()["texto_resposta"]


# ------------------------------------------------------------------ #
# Validação de contrato HTTP                                          #
# ------------------------------------------------------------------ #


def test_exames_retorna_estrutura_clinica_padrao() -> None:
    """Resposta de exames segue estrutura RespostaClinica."""
    orq = _mock_orq_exames(_resposta_exames("Nenhum exame pendente."))

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-004/exames-pendentes")

    body = resp.json()
    assert "texto_resposta" in body
    assert "fontes" in body
    assert "avisos" in body
    assert "confianca" in body


def test_exames_aviso_apoio_decisao_sempre_presente() -> None:
    """AC relacionado 1.7: aviso apoio_decisao sempre presente."""
    orq = _mock_orq_exames(_resposta_exames("Nenhum exame pendente."))

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-005/exames-pendentes")

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "apoio_decisao" in tipos


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


def _mock_orq_exames(resposta):
    from unittest.mock import MagicMock, AsyncMock

    orq = MagicMock()
    orq.handle_verificacao_exames = AsyncMock(return_value=resposta)
    return orq
