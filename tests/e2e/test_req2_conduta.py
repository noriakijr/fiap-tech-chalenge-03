"""Testes E2E — Requisito 2: Sugestão de Condutas Clínicas.

Formato Given/When/Then. Cada teste corresponde a um critério de aceitação.
O orquestrador é mockado para isolar o comportamento da API.

Refs: requirements.md § Requirement 2 (AC 2.1 – 2.7)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_orchestrador, get_session_store
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

SESSAO_ID = "e2e-req2-sessao"


def _store() -> dict:
    return {SESSAO_ID: SessaoMedico(id_sessao=SESSAO_ID, id_medico="DR-E2E")}


def _cliente(orq) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_orchestrador] = lambda: orq
    app.dependency_overrides[get_session_store] = lambda: _store()
    return TestClient(app, raise_server_exceptions=False)


def _resposta(
    texto: str = "Conduta clínica recomendada.",
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


def _mock_orq(resposta: RespostaClinica) -> MagicMock:
    orq = MagicMock()
    orq.handle_sugestao_conduta = MagicMock(return_value=resposta)
    return orq


# ------------------------------------------------------------------ #
# AC 2.2 — Fontes de protocolo com identificador, título e nível de  #
#           evidência e contraindicações                               #
# ------------------------------------------------------------------ #


def test_ac2_2_protocolo_exibe_id_e_titulo() -> None:
    """WHEN conduta baseada em protocolo THEN exibe identificador e título."""
    fontes = [
        FonteReferencia(
            tipo=TipoFonte.PROTOCOLO,
            identificador="PROT-SEPSE-001",
            titulo="Protocolo de Tratamento de Sepse",
        )
    ]
    with _cliente(_mock_orq(_resposta(fontes=fontes))) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "sepse grave", "sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 200
    fonte = resp.json()["fontes"][0]
    assert fonte["tipo"] == "protocolo"
    assert fonte["identificador"] == "PROT-SEPSE-001"
    assert fonte["titulo"] == "Protocolo de Tratamento de Sepse"


# ------------------------------------------------------------------ #
# AC 2.3 — Fonte de artigo exibe identificador, decisão_final         #
# ------------------------------------------------------------------ #


def test_ac2_3_artigo_exibe_id_e_decisao_final() -> None:
    """WHEN conduta baseada em artigo THEN exibe id e decisao_final."""
    fontes = [
        FonteReferencia(
            tipo=TipoFonte.ARTIGO,
            identificador="PMID-98765",
            titulo="Manejo de sepse em UTI",
            ano=2021,
            decisao_final=DecisaoFinal.YES,
        )
    ]
    with _cliente(_mock_orq(_resposta(fontes=fontes))) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "sepse", "sessao_id": SESSAO_ID},
        )

    fonte = resp.json()["fontes"][0]
    assert fonte["identificador"] == "PMID-98765"
    assert fonte["decisao_final"] == "yes"


# ------------------------------------------------------------------ #
# AC 2.4 — Ordenação: protocolos antes de artigos                     #
# ------------------------------------------------------------------ #


def test_ac2_4_protocolos_listados_antes_de_artigos() -> None:
    """WHEN múltiplas fontes THEN protocolos aparecem antes dos artigos."""
    fontes = [
        FonteReferencia(
            tipo=TipoFonte.PROTOCOLO,
            identificador="PROT-001",
            titulo="Protocolo A",
        ),
        FonteReferencia(
            tipo=TipoFonte.ARTIGO,
            identificador="PMID-001",
            titulo="Artigo recente",
            ano=2023,
            decisao_final=DecisaoFinal.YES,
        ),
    ]
    with _cliente(_mock_orq(_resposta(fontes=fontes))) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "infecção respiratória", "sessao_id": SESSAO_ID},
        )

    tipos = [f["tipo"] for f in resp.json()["fontes"]]
    # Protocolo deve preceder artigo
    assert tipos.index("protocolo") < tipos.index("artigo")


# ------------------------------------------------------------------ #
# AC 2.5 — Emergência exibe aviso em destaque                         #
# ------------------------------------------------------------------ #


def test_ac2_5_emergencia_gera_aviso_destaque() -> None:
    """WHEN quadro é emergência THEN aviso emergencia presente com destaque=True."""
    avisos = [
        Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
        Aviso(tipo=TipoAviso.EMERGENCIA, mensagem="Emergência!", destaque=True),
    ]
    with _cliente(_mock_orq(_resposta(avisos=avisos))) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "parada cardiorrespiratória", "sessao_id": SESSAO_ID},
        )

    avisos_resp = resp.json()["avisos"]
    emergencias = [a for a in avisos_resp if a["tipo"] == "emergencia"]
    assert len(emergencias) == 1
    assert emergencias[0]["destaque"] is True


# ------------------------------------------------------------------ #
# AC 2.6 — Máximo 5 protocolos retornados                             #
# ------------------------------------------------------------------ #


def test_ac2_6_maximo_5_protocolos() -> None:
    """WHEN múltiplos protocolos THEN no máximo 5 são retornados."""
    # Simulamos que o orquestrador já aplicou o limite
    fontes = [
        FonteReferencia(
            tipo=TipoFonte.PROTOCOLO,
            identificador=f"PROT-{i:03d}",
            titulo=f"Protocolo {i}",
        )
        for i in range(1, 6)  # exatamente 5
    ]
    with _cliente(_mock_orq(_resposta(fontes=fontes))) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "condição polimórfica", "sessao_id": SESSAO_ID},
        )

    protocolos = [f for f in resp.json()["fontes"] if f["tipo"] == "protocolo"]
    assert len(protocolos) <= 5


# ------------------------------------------------------------------ #
# AC 2.7 — Sem evidência disponível informa ausência                  #
# ------------------------------------------------------------------ #


def test_ac2_7_sem_evidencia_retorna_mensagem_adequada() -> None:
    """IF sem protocolo/artigo THEN resposta informa ausência e recomenda especialista."""
    texto = (
        "Não há evidência disponível na base para o quadro descrito. "
        "Recomendamos consultar um especialista."
    )
    with _cliente(_mock_orq(_resposta(texto=texto, fontes=[]))) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "síndrome inexistente", "sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 200
    body = resp.json()["texto_resposta"].lower()
    assert "especialista" in body or "evidência" in body or "disponível" in body


# ------------------------------------------------------------------ #
# Validação de contrato HTTP                                          #
# ------------------------------------------------------------------ #


def test_conduta_sem_quadro_clinico_retorna_422() -> None:
    """Payload sem quadro_clinico deve retornar 422."""
    orq = MagicMock()
    with _cliente(orq) as tc:
        resp = tc.post("/v1/conduta", json={"sessao_id": SESSAO_ID})
    assert resp.status_code == 422


def test_conduta_sessao_invalida_retorna_404() -> None:
    """Sessão inexistente deve retornar 404."""
    orq = MagicMock()
    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "gripe", "sessao_id": "sessao-invalida"},
        )
    assert resp.status_code == 404


def test_conduta_aviso_apoio_decisao_sempre_presente() -> None:
    """AC relacionado 1.7: aviso apoio_decisao sempre presente."""
    with _cliente(_mock_orq(_resposta())) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "gripe", "sessao_id": SESSAO_ID},
        )

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "apoio_decisao" in tipos


def test_conduta_fora_protocolo_gera_aviso() -> None:
    """WHEN sem cobertura de protocolo THEN aviso fora_protocolo presente."""
    avisos = [
        Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
        Aviso(tipo=TipoAviso.FORA_PROTOCOLO, mensagem="fora", destaque=False),
    ]
    with _cliente(_mock_orq(_resposta(avisos=avisos))) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "condição rara", "sessao_id": SESSAO_ID},
        )

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "fora_protocolo" in tipos
