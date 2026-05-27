"""Testes E2E — Requisito 1: Interface de Consulta Clínica.

Formato Given/When/Then. Cada teste corresponde a um critério de aceitação.
O orquestrador é mockado para isolar o comportamento da API.

Refs: requirements.md § Requirement 1 (AC 1.1 – 1.11)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_orchestrador, get_session_store
from app.core.exceptions import KnowledgeBaseUnavailableError, PLNTimeoutError
from app.main import create_app
from app.models.domain import (
    Aviso,
    DecisaoFinal,
    FonteReferencia,
    RespostaClinica,
    SessaoMedico,
    TipoAviso,
    TipoFonte,
)

SESSAO_ID = "e2e-req1-sessao"


def _store() -> dict:
    return {SESSAO_ID: SessaoMedico(id_sessao=SESSAO_ID, id_medico="DR-E2E")}


def _cliente(orq) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_orchestrador] = lambda: orq
    app.dependency_overrides[get_session_store] = lambda: _store()
    return TestClient(app, raise_server_exceptions=False)


def _resposta(
    texto: str = "Resposta clínica.",
    fontes=None,
    avisos=None,
    confianca: float = 0.85,
) -> RespostaClinica:
    return RespostaClinica(
        texto_resposta=texto,
        fontes=fontes or [],
        avisos=avisos or [Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False)],
        confianca=confianca,
    )


# ------------------------------------------------------------------ #
# AC 1.2 — Fontes exibidas junto à resposta                           #
# ------------------------------------------------------------------ #


def test_ac1_2_resposta_inclui_fontes_com_id_titulo_ano() -> None:
    """WHEN o Assistente gera resposta THEN exibe fontes com id, título e ano."""
    fontes = [
        FonteReferencia(
            tipo=TipoFonte.ARTIGO,
            identificador="PMID-12345",
            titulo="Tratamento de pneumonia em adultos",
            ano=2022,
            decisao_final=DecisaoFinal.YES,
        )
    ]
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(return_value=_resposta(fontes=fontes))

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "tratamento pneumonia", "sessao_id": SESSAO_ID})

    assert resp.status_code == 200
    fontes_resp = resp.json()["fontes"]
    assert len(fontes_resp) == 1
    assert fontes_resp[0]["identificador"] == "PMID-12345"
    assert fontes_resp[0]["titulo"] == "Tratamento de pneumonia em adultos"
    assert fontes_resp[0]["ano"] == 2022


def test_ac1_2_fonte_protocolo_tem_id_e_titulo() -> None:
    """THEN protocolos aparecem com identificador e título."""
    fontes = [
        FonteReferencia(
            tipo=TipoFonte.PROTOCOLO,
            identificador="PROT-PNEUMONIA-001",
            titulo="Protocolo de Pneumonia Hospitalar",
        )
    ]
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(return_value=_resposta(fontes=fontes))

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "conduta pneumonia", "sessao_id": SESSAO_ID})

    fonte = resp.json()["fontes"][0]
    assert fonte["tipo"] == "protocolo"
    assert fonte["identificador"] == "PROT-PNEUMONIA-001"
    assert fonte["titulo"] == "Protocolo de Pneumonia Hospitalar"


# ------------------------------------------------------------------ #
# AC 1.3 — Evidência inconclusiva sinalizada                          #
# ------------------------------------------------------------------ #


def test_ac1_3_maybe_gera_aviso_inconclusivo() -> None:
    """WHEN artigo tem final_decision=maybe THEN aviso evidencia_inconclusiva presente."""
    avisos = [
        Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
        Aviso(tipo=TipoAviso.EVIDENCIA_INCONCLUSIVA, mensagem="inconclusivo", destaque=False),
    ]
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(return_value=_resposta(avisos=avisos))

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "sepse?", "sessao_id": SESSAO_ID})

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "evidencia_inconclusiva" in tipos


# ------------------------------------------------------------------ #
# AC 1.4 — Raciocínio necessário exibe LONG_ANSWER                    #
# ------------------------------------------------------------------ #


def test_ac1_4_reasoning_required_gera_aviso() -> None:
    """WHEN reasoning_required_pred=yes THEN aviso raciocinio_necessario presente."""
    avisos = [
        Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
        Aviso(tipo=TipoAviso.RACIOCINIO_NECESSARIO, mensagem="long_answer", destaque=False),
    ]
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(return_value=_resposta(avisos=avisos))

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "mecanismo?", "sessao_id": SESSAO_ID})

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "raciocinio_necessario" in tipos


# ------------------------------------------------------------------ #
# AC 1.6 — Aviso de baixa confiança                                   #
# ------------------------------------------------------------------ #


def test_ac1_6_baixa_confianca_gera_aviso() -> None:
    """IF confiança abaixo do limiar THEN aviso baixa_confianca exibido."""
    avisos = [
        Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
        Aviso(tipo=TipoAviso.BAIXA_CONFIANCA, mensagem="baixa", destaque=False),
    ]
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(return_value=_resposta(avisos=avisos, confianca=0.3))

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "dúvida clínica", "sessao_id": SESSAO_ID})

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "baixa_confianca" in tipos


# ------------------------------------------------------------------ #
# AC 1.7 — Aviso fixo de apoio à decisão                              #
# ------------------------------------------------------------------ #


def test_ac1_7_aviso_apoio_decisao_sempre_presente() -> None:
    """THE Assistente SHALL exibir aviso fixo de apoio à decisão em TODAS as respostas."""
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(return_value=_resposta())

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "pergunta qualquer", "sessao_id": SESSAO_ID})

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "apoio_decisao" in tipos


# ------------------------------------------------------------------ #
# AC 1.9 — Resposta em português do Brasil                            #
# ------------------------------------------------------------------ #


def test_ac1_9_resposta_em_portugues() -> None:
    """WHEN pergunta em pt-BR THEN resposta em pt-BR (verificado pelo campo de texto)."""
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(
        return_value=_resposta(texto="O diagnóstico mais provável é pneumonia bacteriana.")
    )

    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/consulta",
            json={"texto": "Qual o diagnóstico?", "sessao_id": SESSAO_ID},
        )

    assert "pneumonia" in resp.json()["texto_resposta"].lower()


# ------------------------------------------------------------------ #
# AC 1.10 — Base de conhecimento indisponível                         #
# ------------------------------------------------------------------ #


def test_ac1_10_base_conhecimento_indisponivel_retorna_503() -> None:
    """IF Base_de_Conhecimento indisponível THEN 503 sem resposta clínica parcial."""
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(side_effect=KnowledgeBaseUnavailableError())

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "teste", "sessao_id": SESSAO_ID})

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "knowledge_base_unavailable"


# ------------------------------------------------------------------ #
# AC 1.11 — Timeout do PLN                                            #
# ------------------------------------------------------------------ #


def test_ac1_11_timeout_pln_retorna_504() -> None:
    """WHEN PLN não responde em 10s THEN 504 com mensagem de timeout."""
    orq = AsyncMock()
    orq.processar_pergunta = AsyncMock(side_effect=PLNTimeoutError())

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "teste", "sessao_id": SESSAO_ID})

    assert resp.status_code == 504
    assert resp.json()["error"]["code"] == "pln_timeout"
