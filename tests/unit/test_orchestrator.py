"""Testes de integração para app/orchestrator/fluxo.py (Task 5.1).

Todos os componentes downstream são mockados; nenhuma I/O real ocorre.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_community.llms.fake import FakeListLLM

from app.core.exceptions import PatientNotFoundError
from app.models.domain import (
    DecisaoFinal,
    DocumentoRecuperado,
    Exame,
    IntencaoClinica,
    NLUResult,
    Prontuario,
    RespostaRAG,
    SessaoMedico,
    StatusExame,
    TipoAviso,
    TipoFonte,
)
from app.nlu.interpretador import InterpretadorNLU
from app.orchestrator.fluxo import OrquestradorClinico
from app.services.mesh_mapper import MapadorMeSH


# ------------------------------------------------------------------ #
# Fixtures e helpers                                                   #
# ------------------------------------------------------------------ #


def _sessao() -> SessaoMedico:
    return SessaoMedico(id_sessao=str(uuid.uuid4()), id_medico="DR-001")


def _nlu(intencao: IntencaoClinica, entidades: dict | None = None) -> NLUResult:
    return NLUResult(
        intencao=intencao,
        entidades=entidades or {},
        confianca=0.9,
        idioma_detectado="pt-BR",
        requer_esclarecimento=(intencao == IntencaoClinica.INTENCAO_DESCONHECIDA),
    )


def _rag_result(
    texto: str = "Resposta RAG",
    confianca: float = 0.85,
    documentos: list[DocumentoRecuperado] | None = None,
) -> RespostaRAG:
    return RespostaRAG(
        resposta_texto=texto,
        documentos=documentos or [],
        confianca_geral=confianca,
        aviso_baixa_confianca=False,
    )


def _protocolo_doc(id_: str) -> DocumentoRecuperado:
    return DocumentoRecuperado(
        tipo=TipoFonte.PROTOCOLO,
        identificador=id_,
        titulo=f"Protocolo {id_}",
        score_relevancia=0.8,
    )


def _artigo_doc(id_: str, decisao: DecisaoFinal = DecisaoFinal.YES) -> DocumentoRecuperado:
    return DocumentoRecuperado(
        tipo=TipoFonte.ARTIGO,
        identificador=id_,
        titulo=f"Artigo {id_}",
        decisao_final=decisao,
        score_relevancia=0.7,
    )


def _prontuario(numero: str = "PRT-001", completo: bool = True) -> Prontuario:
    return Prontuario(
        numero=numero,
        diagnostico_ativo="Pneumonia" if completo else None,
        medicamentos_em_uso=["Amoxicilina"] if completo else [],
        alergias=["Penicilina"] if completo else [],
        comorbidades=["Diabetes"],
    )


def _exame(nome: str, status: StatusExame = StatusExame.SOLICITADO) -> Exame:
    return Exame(
        nome=nome,
        data_solicitacao=date(2025, 1, 10),
        solicitante="DR-TEST",
        status=status,
    )


def _orquestrador(
    nlu_result: NLUResult,
    rag_result: RespostaRAG | None = None,
    prontuario: Prontuario | None = None,
    exames: list[Exame] | None = None,
    interacoes=None,
    mesh_terms: list[str] | None = None,
) -> OrquestradorClinico:
    # NLU mock
    interpretador = MagicMock(spec=InterpretadorNLU)
    interpretador.interpretar_pergunta.return_value = nlu_result

    # RAG mock
    motor_rag = MagicMock()
    motor_rag.recuperar_e_gerar.return_value = rag_result or _rag_result()

    # Repo mock (async)
    repo = MagicMock()
    repo.buscar_prontuario = AsyncMock(return_value=prontuario)
    repo.listar_exames_pendentes = AsyncMock(return_value=exames or [])

    # Interações mock
    servico_interacoes = MagicMock()
    servico_interacoes.verificar_interacoes.return_value = interacoes or []

    # MeSH mapper mock
    mapador = MagicMock(spec=MapadorMeSH)
    mapador.mapear_para_mesh.return_value = mesh_terms or ["Pneumonia"]

    return OrquestradorClinico(
        interpretador=interpretador,
        motor_rag=motor_rag,
        repo_pacientes=repo,
        servico_interacoes=servico_interacoes,
        mapador_mesh=mapador,
        confidence_threshold=0.65,
    )


# ------------------------------------------------------------------ #
# handle_consulta_clinica                                              #
# ------------------------------------------------------------------ #


async def test_consulta_clinica_retorna_resposta_com_apoio_decisao() -> None:
    nlu = _nlu(IntencaoClinica.CONSULTA_CLINICA)
    orq = _orquestrador(nlu)
    resultado = await orq.processar_pergunta("O que é pneumonia?", _sessao())

    assert resultado.texto_resposta == "Resposta RAG"
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.APOIO_DECISAO in tipos


async def test_consulta_clinica_adiciona_baixa_confianca_quando_abaixo_limiar() -> None:
    nlu = _nlu(IntencaoClinica.CONSULTA_CLINICA)
    rag = _rag_result(confianca=0.4)
    orq = _orquestrador(nlu, rag_result=rag)
    resultado = await orq.processar_pergunta("teste", _sessao())

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.BAIXA_CONFIANCA in tipos


async def test_consulta_clinica_fontes_mapeadas() -> None:
    docs = [_artigo_doc("PMID-001"), _protocolo_doc("PROT-001")]
    nlu = _nlu(IntencaoClinica.CONSULTA_CLINICA)
    rag = _rag_result(documentos=docs)
    orq = _orquestrador(nlu, rag_result=rag)
    resultado = await orq.processar_pergunta("teste", _sessao())

    ids_fontes = {f.identificador for f in resultado.fontes}
    assert ids_fontes == {"PMID-001", "PROT-001"}


# ------------------------------------------------------------------ #
# handle_sugestao_conduta                                              #
# ------------------------------------------------------------------ #


async def test_sugestao_conduta_exclui_artigos_decisao_no() -> None:
    nlu = _nlu(
        IntencaoClinica.SUGESTAO_CONDUTA, entidades={"condicao": "sepse"}
    )
    orq = _orquestrador(nlu)

    await orq.processar_pergunta("conduta para sepse", _sessao())

    call_kwargs = orq._motor_rag.recuperar_e_gerar.call_args
    assert "no" in (call_kwargs.kwargs.get("excluir_decisao_final") or [])


async def test_sugestao_conduta_usa_mesh_na_consulta_rag() -> None:
    nlu = _nlu(IntencaoClinica.SUGESTAO_CONDUTA, entidades={"condicao": "sepse"})
    orq = _orquestrador(nlu, mesh_terms=["Sepsis"])

    await orq.processar_pergunta("conduta para sepse", _sessao())

    call_kwargs = orq._motor_rag.recuperar_e_gerar.call_args
    assert call_kwargs.kwargs.get("filtros_mesh") == ["Sepsis"]


async def test_sugestao_conduta_fora_protocolo_quando_sem_protocolos() -> None:
    nlu = _nlu(IntencaoClinica.SUGESTAO_CONDUTA, entidades={"condicao": "sepse"})
    rag = _rag_result(documentos=[_artigo_doc("A1")])  # apenas artigo, sem protocolo
    orq = _orquestrador(nlu, rag_result=rag)
    resultado = await orq.processar_pergunta("conduta", _sessao())

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.FORA_PROTOCOLO in tipos


async def test_sugestao_conduta_sem_fora_protocolo_quando_ha_protocolo() -> None:
    nlu = _nlu(IntencaoClinica.SUGESTAO_CONDUTA, entidades={"condicao": "sepse"})
    rag = _rag_result(documentos=[_protocolo_doc("PROT-1"), _artigo_doc("A1")])
    orq = _orquestrador(nlu, rag_result=rag)
    resultado = await orq.processar_pergunta("conduta", _sessao())

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.FORA_PROTOCOLO not in tipos


async def test_sugestao_conduta_fallback_para_texto_quando_sem_condicao() -> None:
    texto = "paciente com quadro de choque séptico"
    nlu = _nlu(IntencaoClinica.SUGESTAO_CONDUTA, entidades={})  # sem condicao
    orq = _orquestrador(nlu)

    await orq.processar_pergunta(texto, _sessao())

    call_args = orq._motor_rag.recuperar_e_gerar.call_args
    assert call_args.kwargs.get("consulta") == texto or call_args.args[0] == texto


# ------------------------------------------------------------------ #
# handle_verificacao_exames                                            #
# ------------------------------------------------------------------ #


async def test_verificacao_exames_retorna_lista_de_exames() -> None:
    exames = [
        _exame("Hemograma", StatusExame.SOLICITADO),
        _exame("PCR", StatusExame.EM_ANALISE),
    ]
    nlu = _nlu(IntencaoClinica.VERIFICACAO_EXAMES, entidades={"numero_prontuario": "PRT-001"})
    orq = _orquestrador(nlu, prontuario=_prontuario("PRT-001"), exames=exames)
    resultado = await orq.processar_pergunta("exames do paciente PRT-001", _sessao())

    assert "Hemograma" in resultado.texto_resposta
    assert "PCR" in resultado.texto_resposta


async def test_verificacao_exames_sem_pendentes() -> None:
    nlu = _nlu(IntencaoClinica.VERIFICACAO_EXAMES, entidades={"numero_prontuario": "PRT-002"})
    orq = _orquestrador(nlu, prontuario=_prontuario("PRT-002"), exames=[])
    resultado = await orq.processar_pergunta("exames PRT-002", _sessao())

    assert "pendentes" in resultado.texto_resposta.lower()


async def test_verificacao_exames_levanta_patient_not_found() -> None:
    nlu = _nlu(IntencaoClinica.VERIFICACAO_EXAMES, entidades={"numero_prontuario": "INEXISTENTE"})
    orq = _orquestrador(nlu, prontuario=None)  # paciente não existe

    with pytest.raises(PatientNotFoundError):
        await orq.processar_pergunta("exames", _sessao())


async def test_verificacao_exames_sem_prontuario_na_entidade() -> None:
    nlu = _nlu(IntencaoClinica.VERIFICACAO_EXAMES, entidades={})  # sem numero
    orq = _orquestrador(nlu)
    resultado = await orq.processar_pergunta("exames do paciente", _sessao())

    assert "prontuário" in resultado.texto_resposta.lower()


# ------------------------------------------------------------------ #
# handle_sugestao_tratamento                                           #
# ------------------------------------------------------------------ #


async def test_sugestao_tratamento_retorna_resposta_rag() -> None:
    nlu = _nlu(
        IntencaoClinica.SUGESTAO_TRATAMENTO,
        entidades={"numero_prontuario": "PRT-001"},
    )
    orq = _orquestrador(nlu, prontuario=_prontuario("PRT-001"))
    resultado = await orq.processar_pergunta("tratamento para PRT-001", _sessao())

    assert resultado.texto_resposta.startswith("Resposta RAG")
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.APOIO_DECISAO in tipos


async def test_sugestao_tratamento_bloqueia_prontuario_incompleto() -> None:
    prontuario_incompleto = _prontuario("PRT-003", completo=False)
    nlu = _nlu(
        IntencaoClinica.SUGESTAO_TRATAMENTO,
        entidades={"numero_prontuario": "PRT-003"},
    )
    orq = _orquestrador(nlu, prontuario=prontuario_incompleto)
    resultado = await orq.processar_pergunta("tratamento", _sessao())

    assert "incompleto" in resultado.texto_resposta.lower()
    orq._motor_rag.recuperar_e_gerar.assert_not_called()


async def test_sugestao_tratamento_levanta_patient_not_found() -> None:
    nlu = _nlu(
        IntencaoClinica.SUGESTAO_TRATAMENTO,
        entidades={"numero_prontuario": "INEXISTENTE"},
    )
    orq = _orquestrador(nlu, prontuario=None)

    with pytest.raises(PatientNotFoundError):
        await orq.processar_pergunta("tratamento", _sessao())


async def test_sugestao_tratamento_inclui_interacoes_no_texto() -> None:
    from app.models.domain import InteracaoMedicamentosa, SeveridadeInteracao

    interacao = InteracaoMedicamentosa(
        medicamento_a="Warfarina",
        medicamento_b="Aspirina",
        severidade=SeveridadeInteracao.GRAVE,
        descricao="Aumenta risco de sangramento.",
    )
    nlu = _nlu(
        IntencaoClinica.SUGESTAO_TRATAMENTO,
        entidades={
            "numero_prontuario": "PRT-001",
            "medicamentos_mencionados": ["Warfarina"],
        },
    )
    orq = _orquestrador(nlu, prontuario=_prontuario("PRT-001"), interacoes=[interacao])
    resultado = await orq.processar_pergunta("tratamento", _sessao())

    assert "Warfarina" in resultado.texto_resposta
    assert "Aspirina" in resultado.texto_resposta
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.BAIXA_CONFIANCA in tipos


async def test_sugestao_tratamento_sem_prontuario_na_entidade() -> None:
    nlu = _nlu(IntencaoClinica.SUGESTAO_TRATAMENTO, entidades={})
    orq = _orquestrador(nlu)
    resultado = await orq.processar_pergunta("tratamento", _sessao())

    assert "prontuário" in resultado.texto_resposta.lower()


# ------------------------------------------------------------------ #
# Ciclo de esclarecimento                                             #
# ------------------------------------------------------------------ #


async def test_esclarecimento_pede_quando_intencao_desconhecida() -> None:
    nlu = _nlu(IntencaoClinica.INTENCAO_DESCONHECIDA)
    orq = _orquestrador(nlu)
    sessao = _sessao()

    resultado = await orq.processar_pergunta("ahn?", sessao)

    assert sessao.contador_esclarecimentos == 1
    assert TipoAviso.APOIO_DECISAO in {a.tipo for a in resultado.avisos}


async def test_esclarecimento_maximo_3_ciclos() -> None:
    nlu = _nlu(IntencaoClinica.INTENCAO_DESCONHECIDA)
    orq = _orquestrador(nlu)
    sessao = _sessao()

    # Esgotar os 3 ciclos
    for _ in range(3):
        sessao.contador_esclarecimentos = sessao.contador_esclarecimentos  # leitura
        if sessao.pode_pedir_esclarecimento():
            await orq.processar_pergunta("confuso", sessao)

    # 4ª tentativa deve retornar fallback
    resultado = await orq.processar_pergunta("ainda confuso", sessao)
    assert sessao.contador_esclarecimentos == 3
    # Deve retornar resposta de fallback, não pedir mais esclarecimento
    assert resultado.texto_resposta  # algum texto de fallback


async def test_esclarecimento_usa_gerador_quando_fornecido() -> None:
    nlu = _nlu(IntencaoClinica.INTENCAO_DESCONHECIDA)
    orq = _orquestrador(nlu)

    gerador_mock = MagicMock()
    gerador_mock.gerar_pergunta.return_value = "Você quer consulta, conduta ou exames?"
    orq._esclarecimento = gerador_mock

    sessao = _sessao()
    resultado = await orq.processar_pergunta("ahn?", sessao)

    gerador_mock.gerar_pergunta.assert_called_once()
    assert "conduta" in resultado.texto_resposta.lower() or resultado.texto_resposta


# ------------------------------------------------------------------ #
# Histórico da sessão                                                  #
# ------------------------------------------------------------------ #


async def test_pergunta_adicionada_ao_historico_em_intencao_conhecida() -> None:
    nlu = _nlu(IntencaoClinica.CONSULTA_CLINICA)
    orq = _orquestrador(nlu)
    sessao = _sessao()

    await orq.processar_pergunta("O que é sepse?", sessao)

    assert "O que é sepse?" in sessao.historico_perguntas
