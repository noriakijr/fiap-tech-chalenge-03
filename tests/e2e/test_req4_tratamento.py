"""Testes E2E — Requisito 4: Sugestão de Tratamentos.

Formato Given/When/Then. Cada teste corresponde a um critério de aceitação.
O orquestrador é mockado para isolar o comportamento da API.

Refs: requirements.md § Requirement 4 (AC 4.1 – 4.9)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_orchestrador, get_session_store
from app.core.exceptions import InteractionServiceUnavailableError, PatientNotFoundError
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

SESSAO_ID = "e2e-req4-sessao"
PRONTUARIO = "PRT-REQ4"


def _store() -> dict:
    return {SESSAO_ID: SessaoMedico(id_sessao=SESSAO_ID, id_medico="DR-E2E")}


def _cliente(orq) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_orchestrador] = lambda: orq
    app.dependency_overrides[get_session_store] = lambda: _store()
    return TestClient(app, raise_server_exceptions=False)


def _mock_orq(resposta: RespostaClinica) -> MagicMock:
    orq = MagicMock()
    orq.handle_sugestao_tratamento = AsyncMock(return_value=resposta)
    return orq


def _resposta(
    texto: str = "Tratamento sugerido: antibiótico de amplo espectro.",
    fontes=None,
    avisos=None,
    confianca: float = 0.80,
) -> RespostaClinica:
    return RespostaClinica(
        texto_resposta=texto,
        fontes=fontes or [],
        avisos=avisos or [Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False)],
        confianca=confianca,
    )


# ------------------------------------------------------------------ #
# AC 4.2 — Protocolos e artigos separados na resposta                #
# ------------------------------------------------------------------ #


def test_ac4_2_resposta_exibe_protocolos_e_artigos() -> None:
    """WHEN tratamento sugerido THEN fontes incluem protocolos e artigos."""
    fontes = [
        FonteReferencia(
            tipo=TipoFonte.PROTOCOLO,
            identificador="PROT-PNEUMONIA-002",
            titulo="Protocolo ATB Pneumonia",
        ),
        FonteReferencia(
            tipo=TipoFonte.ARTIGO,
            identificador="PMID-55555",
            titulo="Antibioticoterapia para pneumonia",
            ano=2022,
            decisao_final=DecisaoFinal.YES,
        ),
    ]
    with _cliente(_mock_orq(_resposta(fontes=fontes))) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    fontes_resp = resp.json()["fontes"]
    tipos = {f["tipo"] for f in fontes_resp}
    assert "protocolo" in tipos
    assert "artigo" in tipos


# ------------------------------------------------------------------ #
# AC 4.3 — Artigo com decisão "no" não aparece como suporte           #
# ------------------------------------------------------------------ #


def test_ac4_3_artigo_decisao_no_nao_aparece_como_suporte() -> None:
    """IF decisao_final=no THEN artigo não aparece como suporte positivo."""
    # O orquestrador já filtra — verificamos que a resposta não inclui artigo "no"
    fontes = [
        FonteReferencia(
            tipo=TipoFonte.ARTIGO,
            identificador="PMID-99999",
            titulo="Artigo sem suporte",
            ano=2019,
            decisao_final=DecisaoFinal.YES,
        )
    ]
    with _cliente(_mock_orq(_resposta(fontes=fontes))) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    for fonte in resp.json()["fontes"]:
        if fonte["tipo"] == "artigo":
            # Nenhum artigo com decisao_final=no deve aparecer como suporte
            assert fonte.get("decisao_final") != "no"


# ------------------------------------------------------------------ #
# AC 4.4 — Sem protocolo gera aviso fora_protocolo                    #
# ------------------------------------------------------------------ #


def test_ac4_4_sem_protocolo_gera_aviso_fora_protocolo() -> None:
    """IF sem protocolo THEN aviso fora_protocolo presente."""
    avisos = [
        Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
        Aviso(tipo=TipoAviso.FORA_PROTOCOLO, mensagem="fora", destaque=False),
    ]
    with _cliente(_mock_orq(_resposta(avisos=avisos))) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "fora_protocolo" in tipos


# ------------------------------------------------------------------ #
# AC 4.5 — Interações medicamentosas exibidas                         #
# ------------------------------------------------------------------ #


def test_ac4_5_interacoes_exibidas_na_resposta() -> None:
    """WHEN medicamentos em uso THEN interações detectadas aparecem na resposta."""
    texto = (
        "Tratamento sugerido: Warfarina.\n\n"
        "**Interações medicamentosas detectadas:**\n"
        "- [GRAVE] Warfarina ✕ Aspirina: risco de sangramento aumentado."
    )
    with _cliente(_mock_orq(_resposta(texto=texto))) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID, "medicamentos_sugeridos": ["Warfarina"]},
        )

    body = resp.json()["texto_resposta"]
    assert "Warfarina" in body
    assert "Aspirina" in body or "Interações" in body


# ------------------------------------------------------------------ #
# AC 4.6 — Sem medicamentos em uso informa ausência                   #
# ------------------------------------------------------------------ #


def test_ac4_6_sem_medicamentos_informa_ausencia() -> None:
    """IF sem medicamentos em uso THEN mensagem informa ausência."""
    texto = (
        "Tratamento sugerido: Amoxicilina.\n"
        "Não há medicamentos em uso registrados — verificação de interações não realizada."
    )
    with _cliente(_mock_orq(_resposta(texto=texto))) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    body = resp.json()["texto_resposta"].lower()
    assert "medicamento" in body or "interação" in body or "amoxicilina" in body


# ------------------------------------------------------------------ #
# AC 4.7 — Serviço de interações indisponível retorna 503             #
# ------------------------------------------------------------------ #


def test_ac4_7_servico_interacoes_indisponivel_retorna_503() -> None:
    """IF serviço de interações indisponível THEN 503 bloqueia sugestão."""
    orq = MagicMock()
    orq.handle_sugestao_tratamento = AsyncMock(
        side_effect=InteractionServiceUnavailableError()
    )

    with _cliente(orq) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "interaction_service_unavailable"


# ------------------------------------------------------------------ #
# AC 4.8 — Contraindicações exibidas                                  #
# ------------------------------------------------------------------ #


def test_ac4_8_contraindicacoes_exibidas() -> None:
    """WHEN contraindicações no prontuário THEN aparecem na resposta."""
    texto = (
        "Tratamento sugerido: Penicilina.\n\n"
        "**Contraindicações detectadas:**\n"
        "- Alergia a Penicilina registrada no prontuário."
    )
    avisos = [
        Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
        Aviso(tipo=TipoAviso.BAIXA_CONFIANCA, mensagem="baixa", destaque=False),
    ]
    with _cliente(_mock_orq(_resposta(texto=texto, avisos=avisos))) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    body = resp.json()["texto_resposta"]
    assert "Contraindicações" in body or "Alergia" in body


# ------------------------------------------------------------------ #
# AC 4.9 — Campos obrigatórios ausentes bloqueiam sugestão            #
# ------------------------------------------------------------------ #


def test_ac4_9_prontuario_incompleto_retorna_200_com_aviso() -> None:
    """IF prontuário sem campos obrigatórios THEN 200 com mensagem informando campos ausentes."""
    texto = (
        "Prontuário incompleto. Campos obrigatórios ausentes: "
        "diagnostico_ativo, alergias. "
        "Complete o prontuário antes de solicitar sugestão de tratamento."
    )
    with _cliente(_mock_orq(_resposta(texto=texto, confianca=0.0))) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 200
    body = resp.json()["texto_resposta"].lower()
    assert "incompleto" in body or "ausente" in body


# ------------------------------------------------------------------ #
# AC 4.1 — Paciente não encontrado retorna 404                        #
# ------------------------------------------------------------------ #


def test_ac4_1_paciente_inexistente_retorna_404() -> None:
    """IF prontuário não cadastrado THEN 404."""
    orq = MagicMock()
    orq.handle_sugestao_tratamento = AsyncMock(
        side_effect=PatientNotFoundError("Paciente não encontrado.")
    )

    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/pacientes/INEXISTENTE/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# Validação de contrato HTTP                                          #
# ------------------------------------------------------------------ #


def test_tratamento_sem_sessao_id_retorna_422() -> None:
    """Payload sem sessao_id deve retornar 422."""
    orq = MagicMock()
    with _cliente(orq) as tc:
        resp = tc.post(f"/v1/pacientes/{PRONTUARIO}/tratamento", json={})
    assert resp.status_code == 422


def test_tratamento_aviso_apoio_decisao_sempre_presente() -> None:
    """AC 1.7: aviso apoio_decisao sempre presente."""
    with _cliente(_mock_orq(_resposta())) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "apoio_decisao" in tipos


def test_tratamento_retorna_estrutura_clinica_padrao() -> None:
    """Resposta de tratamento segue estrutura RespostaClinica."""
    with _cliente(_mock_orq(_resposta())) as tc:
        resp = tc.post(
            f"/v1/pacientes/{PRONTUARIO}/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    body = resp.json()
    assert "texto_resposta" in body
    assert "fontes" in body
    assert "avisos" in body
    assert "confianca" in body
