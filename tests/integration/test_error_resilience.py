"""Testes de resiliência e tratamento de erros — Fase 8.

Cobre todos os cenários da tabela Error Handling do design.md,
verificando que o sistema responde corretamente a falhas de cada componente.

Refs: design.md § Error Handling
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_orchestrador, get_session_store
from app.core.exceptions import (
    DatabaseUnavailableError,
    InteractionServiceUnavailableError,
    KnowledgeBaseUnavailableError,
    PatientNotFoundError,
    PLNTimeoutError,
)
from app.main import create_app
from app.models.domain import (
    Aviso,
    RespostaClinica,
    SessaoMedico,
    TipoAviso,
)
from tests.integration.conftest import SESSAO_ID, make_mock_orq, make_store


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _cliente(orq=None, store=None) -> TestClient:
    app = create_app()
    if orq is not None:
        app.dependency_overrides[get_orchestrador] = lambda: orq
    store = store or make_store()
    app.dependency_overrides[get_session_store] = lambda: store
    return TestClient(app, raise_server_exceptions=False)


def _resposta_padrao(texto: str = "Resposta clínica.") -> RespostaClinica:
    return RespostaClinica(
        texto_resposta=texto,
        fontes=[],
        avisos=[Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False)],
        confianca=0.85,
    )


# ================================================================== #
# Cenário 1: Base_de_Conhecimento indisponível → 503                  #
# ================================================================== #


def test_error_kb_indisponivel_retorna_503() -> None:
    """Req 1.10: KB indisponível → 503 sem resposta clínica parcial."""
    orq = make_mock_orq()
    orq.processar_pergunta = AsyncMock(side_effect=KnowledgeBaseUnavailableError())

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "teste", "sessao_id": SESSAO_ID})

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "knowledge_base_unavailable"
    assert "error" in body
    # Não retorna resposta clínica parcial
    assert "texto_resposta" not in body


def test_error_kb_indisponivel_mensagem_em_pt_br() -> None:
    """Mensagem de erro KB indisponível deve estar em pt-BR."""
    orq = make_mock_orq()
    orq.processar_pergunta = AsyncMock(side_effect=KnowledgeBaseUnavailableError())

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "teste", "sessao_id": SESSAO_ID})

    msg = resp.json()["error"]["message"].lower()
    assert any(tok in msg for tok in ("indisponível", "tente", "serviço", "base"))


# ================================================================== #
# Cenário 2: Timeout PLN > 10s → 504                                  #
# ================================================================== #


def test_error_pln_timeout_retorna_504() -> None:
    """Req 1.11: timeout PLN → 504 com mensagem de timeout."""
    orq = make_mock_orq()
    orq.processar_pergunta = AsyncMock(side_effect=PLNTimeoutError())

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "teste", "sessao_id": SESSAO_ID})

    assert resp.status_code == 504
    assert resp.json()["error"]["code"] == "pln_timeout"


def test_error_pln_timeout_nao_retorna_resposta_parcial() -> None:
    """Timeout PLN não deve retornar resposta clínica parcial."""
    orq = make_mock_orq()
    orq.processar_pergunta = AsyncMock(side_effect=PLNTimeoutError())

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "teste", "sessao_id": SESSAO_ID})

    assert "texto_resposta" not in resp.json()


# ================================================================== #
# Cenário 3: Prontuário não encontrado → 404                          #
# ================================================================== #


def test_error_prontuario_nao_encontrado_exames_retorna_404() -> None:
    """Req 3.3: prontuário não cadastrado em exames → 404."""
    orq = make_mock_orq()
    orq.handle_verificacao_exames = AsyncMock(
        side_effect=PatientNotFoundError("Paciente não encontrado.")
    )

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/INVALIDO/exames-pendentes")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "patient_not_found"


def test_error_prontuario_nao_encontrado_tratamento_retorna_404() -> None:
    """Req 4.1: prontuário não cadastrado em tratamento → 404."""
    orq = make_mock_orq()
    orq.handle_sugestao_tratamento = AsyncMock(
        side_effect=PatientNotFoundError("Paciente não encontrado.")
    )

    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/pacientes/INVALIDO/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 404


def test_error_404_mensagem_solicita_correcao() -> None:
    """Req 3.3: mensagem 404 deve pedir ao médico que verifique o prontuário."""
    orq = make_mock_orq()
    orq.handle_verificacao_exames = AsyncMock(side_effect=PatientNotFoundError())

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/X/exames-pendentes")

    msg = resp.json()["error"]["message"].lower()
    assert any(tok in msg for tok in ("verifique", "paciente", "prontuário", "encontrado"))


# ================================================================== #
# Cenário 4: Nenhum exame pendente → 200 com mensagem específica      #
# ================================================================== #


def test_error_sem_exames_pendentes_retorna_200() -> None:
    """Req 3.4: sem exames pendentes → 200 com mensagem, não lista vazia."""
    resposta = _resposta_padrao("Não há exames pendentes para o paciente PRT-002.")
    orq = make_mock_orq(handle_exames=resposta)

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-002/exames-pendentes")

    assert resp.status_code == 200
    body = resp.json()["texto_resposta"].lower()
    assert "pendente" in body or "nenhum" in body


def test_error_sem_exames_retorna_estrutura_clinica() -> None:
    """Mesmo sem exames, resposta segue estrutura RespostaClinica."""
    resposta = _resposta_padrao("Nenhum exame pendente.")
    orq = make_mock_orq(handle_exames=resposta)

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-003/exames-pendentes")

    body = resp.json()
    assert "texto_resposta" in body
    assert "fontes" in body
    assert "avisos" in body


# ================================================================== #
# Cenário 5: Serviço de interações indisponível → 503                 #
# ================================================================== #


def test_error_interacoes_indisponivel_retorna_503() -> None:
    """Req 4.7: serviço de interações indisponível → 503 bloqueia sugestão."""
    orq = make_mock_orq()
    orq.handle_sugestao_tratamento = AsyncMock(
        side_effect=InteractionServiceUnavailableError()
    )

    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/pacientes/PRT-001/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "interaction_service_unavailable"


def test_error_interacoes_indisponivel_nao_retorna_sugestao() -> None:
    """Req 4.7: quando interações indisponíveis, nenhuma sugestão de tratamento."""
    orq = make_mock_orq()
    orq.handle_sugestao_tratamento = AsyncMock(
        side_effect=InteractionServiceUnavailableError()
    )

    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/pacientes/PRT-001/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    # Não há campo texto_resposta (não é resposta clínica parcial)
    assert "texto_resposta" not in resp.json()


# ================================================================== #
# Cenário 6: Sem protocolo/artigo → informa ausência                  #
# ================================================================== #


def test_error_sem_evidencia_retorna_200_com_aviso() -> None:
    """Req 2.7: sem protocolo ou artigo → 200 com mensagem e recomendação."""
    resposta = _resposta_padrao(
        "Não há evidência disponível para o quadro descrito. "
        "Recomendamos consultar um especialista."
    )
    orq = make_mock_orq(handle_conduta=resposta)

    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "condição rara", "sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 200
    body = resp.json()["texto_resposta"].lower()
    assert "especialista" in body or "evidência" in body or "disponível" in body


# ================================================================== #
# Cenário 7: Confiança abaixo do limiar → aviso baixa_confianca       #
# ================================================================== #


def test_error_baixa_confianca_retorna_200_com_aviso() -> None:
    """Req 1.6: confiança abaixo do limiar → 200 com aviso baixa_confianca."""
    resposta = RespostaClinica(
        texto_resposta="Resposta com baixa confiança.",
        fontes=[],
        avisos=[
            Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
            Aviso(tipo=TipoAviso.BAIXA_CONFIANCA, mensagem="baixa", destaque=False),
        ],
        confianca=0.3,
    )
    orq = make_mock_orq(processar=resposta)

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "dúvida", "sessao_id": SESSAO_ID})

    assert resp.status_code == 200
    tipos = [a["tipo"] for a in resp.json()["avisos"]]
    assert "baixa_confianca" in tipos


# ================================================================== #
# Cenário 8: Intenção não reconhecida → esclarecimento                 #
# ================================================================== #


def test_error_intencao_desconhecida_retorna_esclarecimento() -> None:
    """Req 1.8: intenção desconhecida → orquestrador retorna pedido de esclarecimento."""
    resposta = _resposta_padrao(
        "Esclarecimento 1/3: poderia descrever com mais detalhes sua solicitação?"
    )
    orq = make_mock_orq(processar=resposta)

    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/consulta",
            json={"texto": "asdlfkj xyzabc", "sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 200
    assert "esclarecimento" in resp.json()["texto_resposta"].lower()


# ================================================================== #
# Cenário 9: Prontuário sem campos obrigatórios → bloqueio            #
# ================================================================== #


def test_error_prontuario_incompleto_retorna_200_com_indicacao() -> None:
    """Req 4.9: prontuário incompleto → 200 com campos faltantes."""
    resposta = _resposta_padrao(
        "Prontuário incompleto. Campos obrigatórios ausentes: diagnostico_ativo, alergias."
    )
    orq = make_mock_orq(handle_tratamento=resposta)

    with _cliente(orq) as tc:
        resp = tc.post(
            "/v1/pacientes/PRT-INCOMPLETO/tratamento",
            json={"sessao_id": SESSAO_ID},
        )

    assert resp.status_code == 200
    body = resp.json()["texto_resposta"].lower()
    assert "incompleto" in body or "ausente" in body


# ================================================================== #
# Cenário 10: Falha de conexão com banco → 503                        #
# ================================================================== #


def test_error_banco_indisponivel_retorna_503() -> None:
    """Req 3.1/4.1: falha de conexão com banco → 503."""
    orq = make_mock_orq()
    orq.handle_verificacao_exames = AsyncMock(side_effect=DatabaseUnavailableError())

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-001/exames-pendentes")

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "database_unavailable"


def test_error_banco_indisponivel_nao_retorna_dados_parciais() -> None:
    """Req 3.1: falha de banco não retorna dados parciais."""
    orq = make_mock_orq()
    orq.handle_verificacao_exames = AsyncMock(side_effect=DatabaseUnavailableError())

    with _cliente(orq) as tc:
        resp = tc.get("/v1/pacientes/PRT-001/exames-pendentes")

    assert "texto_resposta" not in resp.json()


# ================================================================== #
# Orquestrador ausente → 503                                          #
# ================================================================== #


def test_error_sem_orquestrador_consulta_retorna_503() -> None:
    """Sem RAG configurado (vectorstore=None) → 503 em qualquer endpoint clínico."""
    app = create_app()
    app.dependency_overrides[get_session_store] = lambda: make_store()
    with TestClient(app, raise_server_exceptions=False) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "teste", "sessao_id": SESSAO_ID})
    assert resp.status_code == 503


def test_error_sem_orquestrador_conduta_retorna_503() -> None:
    app = create_app()
    app.dependency_overrides[get_session_store] = lambda: make_store()
    with TestClient(app, raise_server_exceptions=False) as tc:
        resp = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "gripe", "sessao_id": SESSAO_ID},
        )
    assert resp.status_code == 503


# ================================================================== #
# Sessão inválida → 404 em endpoints que requerem sessão              #
# ================================================================== #


@pytest.mark.parametrize(
    "path,method,payload",
    [
        ("/v1/consulta", "POST", {"texto": "teste", "sessao_id": "invalida"}),
        ("/v1/conduta", "POST", {"quadro_clinico": "gripe", "sessao_id": "invalida"}),
        ("/v1/pacientes/PRT-001/tratamento", "POST", {"sessao_id": "invalida"}),
    ],
)
def test_error_sessao_invalida_retorna_404(path: str, method: str, payload: dict) -> None:
    """Sessão inexistente deve retornar 404 em qualquer endpoint que a exija."""
    orq = make_mock_orq()
    with _cliente(orq) as tc:
        if method == "POST":
            resp = tc.post(path, json=payload)
        else:
            resp = tc.get(path)
    assert resp.status_code == 404


# ================================================================== #
# Erro interno inesperado → 500                                        #
# ================================================================== #


def test_error_excecao_inesperada_retorna_500() -> None:
    """Exceção não mapeada deve retornar 500 sem vazar stack trace."""
    orq = make_mock_orq()
    orq.processar_pergunta = AsyncMock(side_effect=RuntimeError("boom inesperado"))

    with _cliente(orq) as tc:
        resp = tc.post("/v1/consulta", json={"texto": "teste", "sessao_id": SESSAO_ID})

    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "internal_error"
    # Sem vazar detalhes internos
    assert "boom" not in body["error"].get("message", "")
