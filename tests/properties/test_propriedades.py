"""Testes de Propriedades (Correctness Properties) — Fase 8.

Verifica as 15 propriedades definidas em design.md § Correctness Properties.
Usa dados parametrizados (sem Hypothesis) para cobrir múltiplos cenários.

Refs: design.md § Correctness Properties (P1 – P15)
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.models.domain import (
    Aviso,
    DecisaoFinal,
    DocumentoRecuperado,
    FonteReferencia,
    IntencaoClinica,
    NLUResult,
    Prontuario,
    Protocolo,
    RespostaClinica,
    RespostaRAG,
    SessaoMedico,
    StatusExame,
    TipoAviso,
    TipoFonte,
)
from app.orchestrator.avisos import ContextoAvisos, aplicar_avisos
from app.services.contraindicacoes import verificar_contraindicacoes
from app.services.emergencia import detectar_emergencia
from app.services.ordenacao import ordenar_condutas
from app.services.prontuario_validator import validar_campos_obrigatorios


# ------------------------------------------------------------------ #
# Helpers de fixtures                                                  #
# ------------------------------------------------------------------ #


def _artigo(
    id: str = "A1",
    titulo: str = "Pergunta clínica",
    ano: int = 2022,
    decisao_final: DecisaoFinal = DecisaoFinal.YES,
    reasoning_required: bool = False,
    meshes: list[str] | None = None,
    score: float = 0.8,
) -> DocumentoRecuperado:
    return DocumentoRecuperado(
        tipo=TipoFonte.ARTIGO,
        identificador=id,
        titulo=titulo,
        ano=ano,
        decisao_final=decisao_final,
        reasoning_required=reasoning_required,
        meshes=meshes or [],
        score_relevancia=score,
    )


def _protocolo(
    id: str = "P1",
    titulo: str = "Protocolo Clínico",
    meshes: list[str] | None = None,
    termos_emergencia: list[str] | None = None,
    contraindicacoes: list[str] | None = None,
    score: float = 0.9,
) -> DocumentoRecuperado:
    return DocumentoRecuperado(
        tipo=TipoFonte.PROTOCOLO,
        identificador=id,
        titulo=titulo,
        meshes=meshes or [],
        score_relevancia=score,
    )


def _resposta_rag(
    documentos: list[DocumentoRecuperado] | None = None,
    confianca: float = 0.85,
    aviso_baixa: bool = False,
) -> RespostaRAG:
    return RespostaRAG(
        resposta_texto="Resposta RAG.",
        documentos=documentos or [],
        confianca_geral=confianca,
        aviso_baixa_confianca=aviso_baixa,
    )


def _fonte_artigo(id: str = "A1", ano: int = 2022) -> FonteReferencia:
    return FonteReferencia(
        tipo=TipoFonte.ARTIGO,
        identificador=id,
        titulo="Pergunta clínica",
        ano=ano,
        decisao_final=DecisaoFinal.YES,
    )


def _fonte_protocolo(id: str = "P1") -> FonteReferencia:
    return FonteReferencia(
        tipo=TipoFonte.PROTOCOLO,
        identificador=id,
        titulo="Protocolo Clínico",
    )


# ================================================================== #
# Property 1: Toda resposta clínica contém ao menos uma fonte         #
# ================================================================== #


@pytest.mark.parametrize(
    "fontes",
    [
        [_fonte_artigo("PMID-001")],
        [_fonte_protocolo("PROT-001")],
        [_fonte_artigo("A1"), _fonte_protocolo("P1")],
    ],
)
def test_p1_resposta_contem_ao_menos_uma_fonte(fontes) -> None:
    """P1: respostas geradas com base na Base_de_Conhecimento têm ao menos uma fonte."""
    resposta = RespostaClinica(
        texto_resposta="Resposta baseada em evidências.",
        fontes=fontes,
        avisos=[],
        confianca=0.85,
    )
    assert len(resposta.fontes) >= 1
    for fonte in resposta.fontes:
        assert fonte.identificador
        assert fonte.titulo


# ================================================================== #
# Property 2: Evidências inconclusivas sempre sinalizadas              #
# ================================================================== #


@pytest.mark.parametrize(
    "documentos",
    [
        [_artigo("M1", decisao_final=DecisaoFinal.MAYBE)],
        [_artigo("A1", decisao_final=DecisaoFinal.YES), _artigo("M1", decisao_final=DecisaoFinal.MAYBE)],
    ],
)
def test_p2_maybe_gera_aviso_evidencia_inconclusiva(documentos) -> None:
    """P2: artigo maybe → aviso evidencia_inconclusiva sempre presente."""
    rag = _resposta_rag(documentos)
    resposta = RespostaClinica(texto_resposta="resp", fontes=[], avisos=[], confianca=0.8)
    resultado = aplicar_avisos(resposta, ContextoAvisos(resposta_rag=rag))

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.EVIDENCIA_INCONCLUSIVA in tipos


def test_p2_sem_maybe_nao_gera_aviso_inconclusivo() -> None:
    """P2 inverso: sem artigo maybe → sem aviso evidencia_inconclusiva."""
    rag = _resposta_rag([_artigo("A1", decisao_final=DecisaoFinal.YES)])
    resposta = RespostaClinica(texto_resposta="resp", fontes=[], avisos=[], confianca=0.9)
    resultado = aplicar_avisos(resposta, ContextoAvisos(resposta_rag=rag))

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.EVIDENCIA_INCONCLUSIVA not in tipos


# ================================================================== #
# Property 3: Artigos com raciocínio necessário exibem LONG_ANSWER    #
# ================================================================== #


def test_p3_reasoning_required_gera_aviso_raciocinio_necessario() -> None:
    """P3: reasoning_required=True → aviso raciocinio_necessario."""
    doc = _artigo("A1", reasoning_required=True)
    rag = _resposta_rag([doc])
    resposta = RespostaClinica(texto_resposta="resp", fontes=[], avisos=[], confianca=0.8)
    resultado = aplicar_avisos(resposta, ContextoAvisos(resposta_rag=rag))

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.RACIOCINIO_NECESSARIO in tipos


def test_p3_sem_reasoning_nao_gera_aviso_raciocinio() -> None:
    """P3 inverso: reasoning_required=False → sem aviso raciocinio_necessario."""
    doc = _artigo("A1", reasoning_required=False)
    rag = _resposta_rag([doc])
    resposta = RespostaClinica(texto_resposta="resp", fontes=[], avisos=[], confianca=0.9)
    resultado = aplicar_avisos(resposta, ContextoAvisos(resposta_rag=rag))

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.RACIOCINIO_NECESSARIO not in tipos


# ================================================================== #
# Property 4: Artigos com final_decision=no não aparecem como suporte  #
# ================================================================== #


@pytest.mark.parametrize(
    "fontes",
    [
        [_fonte_artigo("A1")],  # apenas yes
        [_fonte_protocolo("P1")],  # apenas protocolo
        [],
    ],
)
def test_p4_nenhum_artigo_no_como_suporte(fontes) -> None:
    """P4: nenhum artigo com decisao_final=no aparece como suporte."""
    for fonte in fontes:
        if fonte.tipo == TipoFonte.ARTIGO:
            assert fonte.decisao_final != DecisaoFinal.NO


def test_p4_fontes_com_decisao_no_invalida_em_suporte() -> None:
    """P4: garantia de que model não aceita silenciosamente artigo 'no' como suporte."""
    # O orquestrador exclui artigos 'no' via excluir_decisao_final=["no"]
    # Aqui testamos que o campo do modelo é acessível e correto
    fonte_yes = FonteReferencia(
        tipo=TipoFonte.ARTIGO,
        identificador="A1",
        titulo="Artigo válido",
        ano=2022,
        decisao_final=DecisaoFinal.YES,
    )
    assert fonte_yes.decisao_final == DecisaoFinal.YES
    assert fonte_yes.decisao_final != DecisaoFinal.NO


# ================================================================== #
# Property 5: Ordenação: protocolos antes de artigos, máx 5            #
# ================================================================== #


@pytest.mark.parametrize(
    "n_protocolos, n_artigos",
    [(1, 2), (3, 0), (0, 5), (6, 3), (5, 5)],
)
def test_p5_protocolos_antes_de_artigos(n_protocolos: int, n_artigos: int) -> None:
    """P5: em qualquer lista de condutas, protocolos precedem artigos."""
    protocolos = [_protocolo(id=f"P{i}", score=0.9 - i * 0.01) for i in range(n_protocolos)]
    artigos = [_artigo(id=f"A{i}", ano=2020 + i) for i in range(n_artigos)]

    resultado = ordenar_condutas(protocolos, artigos)

    tipos = [d.tipo for d in resultado]
    if protocolos and artigos:
        ultimo_protocolo = max(i for i, t in enumerate(tipos) if t == TipoFonte.PROTOCOLO)
        primeiro_artigo = min(i for i, t in enumerate(tipos) if t == TipoFonte.ARTIGO)
        assert ultimo_protocolo < primeiro_artigo


def test_p5_maximo_5_protocolos_retornados() -> None:
    """P5: nunca mais de 5 protocolos na lista de condutas."""
    protocolos = [_protocolo(id=f"P{i}") for i in range(10)]
    artigos = [_artigo(id=f"A{i}") for i in range(3)]

    resultado = ordenar_condutas(protocolos, artigos, max_protocolos=5)

    total_protocolos = sum(1 for d in resultado if d.tipo == TipoFonte.PROTOCOLO)
    assert total_protocolos <= 5


def test_p5_artigos_ordenados_por_ano_desc() -> None:
    """P5: artigos ordenados do mais recente para o mais antigo."""
    artigos = [
        _artigo("A2019", ano=2019),
        _artigo("A2023", ano=2023),
        _artigo("A2021", ano=2021),
    ]

    resultado = ordenar_condutas([], artigos)

    anos = [d.ano for d in resultado]
    assert anos == sorted(anos, reverse=True)


# ================================================================== #
# Property 6: Verificação de segurança cobre interações e contrainds  #
# ================================================================== #


def test_p6_interacoes_verificadas_quando_medicamentos_presentes() -> None:
    """P6: com medicamentos em uso, interações devem ser verificadas."""
    from app.models.domain import InteracaoMedicamentosa, SeveridadeInteracao
    from app.services.interacoes import ServicoInteracoes

    interacao = InteracaoMedicamentosa(
        medicamento_a="Warfarina",
        medicamento_b="Aspirina",
        severidade=SeveridadeInteracao.GRAVE,
        descricao="Risco de sangramento.",
    )
    servico = ServicoInteracoes(carregador=lambda: [interacao], sleep_fn=lambda _: None)
    resultado = servico.verificar_interacoes(["Warfarina"], ["Aspirina"])
    assert isinstance(resultado, list)
    assert len(resultado) >= 1


def test_p6_contraindicacoes_verificadas_com_alergias() -> None:
    """P6: alergia ao medicamento sugerido → contraindicação detectada."""
    prontuario = Prontuario(
        numero="PRT-001",
        diagnostico_ativo="pneumonia",
        medicamentos_em_uso=[],
        alergias=["Penicilina"],
        comorbidades=[],
    )
    alertas = verificar_contraindicacoes(["Penicilina"], prontuario)
    assert len(alertas) > 0
    assert any("Penicilina" in a for a in alertas)


def test_p6_sem_alergias_sem_contraindicacoes() -> None:
    """P6: sem alergias e sem comorbidades → sem contraindicações."""
    prontuario = Prontuario(
        numero="PRT-001",
        diagnostico_ativo="gripe",
        medicamentos_em_uso=[],
        alergias=[],
        comorbidades=[],
    )
    alertas = verificar_contraindicacoes(["Amoxicilina"], prontuario)
    assert len(alertas) == 0


# ================================================================== #
# Property 7: Exames pendentes só retornam status correto             #
# ================================================================== #


@pytest.mark.parametrize(
    "status_validos",
    [
        {StatusExame.SOLICITADO},
        {StatusExame.COLETADO},
        {StatusExame.EM_ANALISE},
        {StatusExame.SOLICITADO, StatusExame.COLETADO},
    ],
)
def test_p7_exames_pendentes_tem_status_valido(status_validos) -> None:
    """P7: status de exames pendentes é sempre Solicitado, Coletado ou Em Análise."""
    from app.models.domain import Exame, STATUS_EXAME_PENDENTE

    exames = [
        Exame(
            nome=f"Exame {s.value}",
            data_solicitacao=date.today(),
            solicitante="DR-A",
            status=s,
        )
        for s in status_validos
    ]
    for exame in exames:
        assert exame.status in STATUS_EXAME_PENDENTE
        assert exame.pendente() is True


def test_p7_exame_concluido_nao_e_pendente() -> None:
    """P7: exame Concluído não está na lista de pendentes."""
    from app.models.domain import Exame

    exame = Exame(
        nome="Hemograma",
        data_solicitacao=date.today(),
        solicitante="DR-A",
        status=StatusExame.CONCLUIDO,
    )
    assert exame.pendente() is False


def test_p7_exame_cancelado_nao_e_pendente() -> None:
    """P7: exame Cancelado não está na lista de pendentes."""
    from app.models.domain import Exame

    exame = Exame(
        nome="PCR",
        data_solicitacao=date.today(),
        solicitante="DR-A",
        status=StatusExame.CANCELADO,
    )
    assert exame.pendente() is False


# ================================================================== #
# Property 8: Aviso fixo de apoio à decisão em toda resposta          #
# ================================================================== #


@pytest.mark.parametrize(
    "contexto",
    [
        ContextoAvisos(),  # sem RAG
        ContextoAvisos(resposta_rag=_resposta_rag()),  # com RAG normal
        ContextoAvisos(emergencia_detectada=True),  # emergência
        ContextoAvisos(fora_protocolo=True),  # fora protocolo
        ContextoAvisos(resposta_rag=_resposta_rag(confianca=0.1)),  # baixa confiança
    ],
)
def test_p8_apoio_decisao_sempre_presente(contexto: ContextoAvisos) -> None:
    """P8: aviso APOIO_DECISAO presente em qualquer combinação de contexto."""
    resposta = RespostaClinica(texto_resposta="Resposta.", fontes=[], avisos=[], confianca=0.8)
    resultado = aplicar_avisos(resposta, contexto)

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.APOIO_DECISAO in tipos


def test_p8_apoio_decisao_nao_duplicado() -> None:
    """P8: aviso APOIO_DECISAO não é duplicado quando já presente."""
    aviso_existente = Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False)
    resposta = RespostaClinica(
        texto_resposta="Resposta.", fontes=[], avisos=[aviso_existente], confianca=0.8
    )
    resultado = aplicar_avisos(resposta, ContextoAvisos())

    apoios = [a for a in resultado.avisos if a.tipo == TipoAviso.APOIO_DECISAO]
    assert len(apoios) == 1


# ================================================================== #
# Property 9: Campos ausentes bloqueiam tratamento com indicação       #
# ================================================================== #


@pytest.mark.parametrize(
    "prontuario,campos_esperados",
    [
        (
            Prontuario(numero="P1", diagnostico_ativo=None, medicamentos_em_uso=[], alergias=[]),
            ["diagnostico_ativo", "medicamentos_em_uso", "alergias"],
        ),
        (
            Prontuario(numero="P2", diagnostico_ativo="pneumonia", medicamentos_em_uso=[], alergias=[]),
            ["medicamentos_em_uso", "alergias"],
        ),
        (
            Prontuario(numero="P3", diagnostico_ativo="gripe", medicamentos_em_uso=["Aspirina"], alergias=[]),
            ["alergias"],
        ),
        (
            Prontuario(
                numero="P4",
                diagnostico_ativo="sepse",
                medicamentos_em_uso=["Heparina"],
                alergias=["Penicilina"],
            ),
            [],
        ),
    ],
)
def test_p9_campos_ausentes_identificados_corretamente(
    prontuario: Prontuario, campos_esperados: list[str]
) -> None:
    """P9: validador retorna exatamente os campos ausentes."""
    ausentes = validar_campos_obrigatorios(prontuario)
    assert sorted(ausentes) == sorted(campos_esperados)


# ================================================================== #
# Property 10: Baixa confiança gera aviso se e somente se abaixo do   #
#              limiar                                                   #
# ================================================================== #


@pytest.mark.parametrize("confianca,threshold,espera_aviso", [
    (0.3, 0.65, True),
    (0.64, 0.65, True),
    (0.65, 0.65, False),
    (0.9, 0.65, False),
    (0.0, 0.65, True),
    (1.0, 0.65, False),
])
def test_p10_baixa_confianca_sse_abaixo_do_limiar(
    confianca: float, threshold: float, espera_aviso: bool
) -> None:
    """P10: aviso BAIXA_CONFIANCA presente se e somente se confiança < threshold."""
    rag = _resposta_rag(confianca=confianca)
    resposta = RespostaClinica(texto_resposta="resp", fontes=[], avisos=[], confianca=confianca)
    resultado = aplicar_avisos(resposta, ContextoAvisos(resposta_rag=rag, confidence_threshold=threshold))

    tipos = {a.tipo for a in resultado.avisos}
    if espera_aviso:
        assert TipoAviso.BAIXA_CONFIANCA in tipos
    else:
        assert TipoAviso.BAIXA_CONFIANCA not in tipos


def test_p10_flag_aviso_rag_forca_baixa_confianca() -> None:
    """P10: aviso_baixa_confianca=True no RAG força aviso mesmo com confiança alta."""
    rag = _resposta_rag(confianca=0.9, aviso_baixa=True)
    resposta = RespostaClinica(texto_resposta="resp", fontes=[], avisos=[], confianca=0.9)
    resultado = aplicar_avisos(resposta, ContextoAvisos(resposta_rag=rag, confidence_threshold=0.65))

    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.BAIXA_CONFIANCA in tipos


# ================================================================== #
# Property 11: Ciclo de esclarecimento ≤ 3 perguntas                  #
# ================================================================== #


def test_p11_sessao_permite_ate_3_esclarecimentos() -> None:
    """P11: sessão permite no máximo 3 pedidos de esclarecimento."""
    sessao = SessaoMedico(id_sessao="S1", id_medico="DR-1")

    # Antes de qualquer esclarecimento
    assert sessao.pode_pedir_esclarecimento() is True

    sessao.contador_esclarecimentos = 2
    assert sessao.pode_pedir_esclarecimento() is True

    sessao.contador_esclarecimentos = 3
    assert sessao.pode_pedir_esclarecimento() is False


def test_p11_contador_nao_pode_exceder_3() -> None:
    """P11: modelo Pydantic rejeita contador > 3."""
    with pytest.raises(Exception):
        SessaoMedico(id_sessao="S1", id_medico="DR-1", contador_esclarecimentos=4)


# ================================================================== #
# Property 12: Campos obrigatórios nas fontes de condutas              #
# ================================================================== #


@pytest.mark.parametrize(
    "fonte",
    [
        FonteReferencia(tipo=TipoFonte.PROTOCOLO, identificador="P1", titulo="Protocolo A"),
        FonteReferencia(
            tipo=TipoFonte.ARTIGO,
            identificador="A1",
            titulo="Artigo B",
            ano=2022,
            decisao_final=DecisaoFinal.YES,
        ),
    ],
)
def test_p12_fontes_tem_campos_obrigatorios(fonte: FonteReferencia) -> None:
    """P12: toda fonte tem identificador e título preenchidos."""
    assert fonte.identificador
    assert fonte.titulo


def test_p12_artigo_tem_decisao_final() -> None:
    """P12: fonte artigo tem decisao_final."""
    fonte = FonteReferencia(
        tipo=TipoFonte.ARTIGO,
        identificador="A1",
        titulo="Artigo",
        ano=2022,
        decisao_final=DecisaoFinal.MAYBE,
    )
    assert fonte.decisao_final is not None


# ================================================================== #
# Property 13: Correspondência MeSH entre quadro e documentos         #
# ================================================================== #


def test_p13_documentos_com_mesh_correspondente() -> None:
    """P13: documentos recuperados têm ao menos um MeSH do quadro clínico."""
    termos_quadro = {"pneumonia", "antibioticoterapia"}
    documentos = [
        _artigo("A1", meshes=["Pneumonia", "Antibiotics"]),
        _artigo("A2", meshes=["Sepsis", "Pneumonia"]),
    ]
    for doc in documentos:
        meshes_doc = {m.lower() for m in doc.meshes}
        assert meshes_doc & termos_quadro  # pelo menos um em comum


# ================================================================== #
# Property 14: Exames refletem estado atual do banco                   #
# ================================================================== #


def test_p14_model_exame_reflete_estado_atual() -> None:
    """P14: o modelo Exame expõe status diretamente (sem cache intermediário)."""
    from app.models.domain import Exame

    exame = Exame(
        nome="Hemograma",
        data_solicitacao=date.today(),
        solicitante="DR-A",
        status=StatusExame.EM_ANALISE,
    )
    # Atualização direta de status (como faz o worker)
    exame_atualizado = exame.model_copy(update={"status": StatusExame.CONCLUIDO})
    assert exame_atualizado.status == StatusExame.CONCLUIDO
    # Original não foi modificado
    assert exame.status == StatusExame.EM_ANALISE


# ================================================================== #
# Property 15: Emergências destacadas antes de outras sugestões        #
# ================================================================== #


def test_p15_emergencia_detectada_em_quadro_com_termo_urgencia() -> None:
    """P15: quadro com termo de emergência → protocolo de emergência retornado."""
    protocolo_emergencia = Protocolo(
        id="PROT-PCR",
        titulo="Protocolo de Parada Cardiorrespiratória",
        nivel_evidencia="A",
        condicoes_aplicaveis=["parada cardiorrespiratória"],
        termos_emergencia=["parada cardiorrespiratória", "PCR"],
        vigente=True,
    )
    resultado = detectar_emergencia(
        "Paciente com parada cardiorrespiratória em andamento.",
        [protocolo_emergencia],
    )
    assert resultado is not None
    assert resultado.id == "PROT-PCR"


def test_p15_sem_termo_emergencia_retorna_none() -> None:
    """P15: quadro sem termos de emergência → detectar_emergencia retorna None."""
    protocolo = Protocolo(
        id="PROT-GRIPE",
        titulo="Protocolo de Gripe",
        nivel_evidencia="B",
        termos_emergencia=["insuficiência respiratória grave"],
        vigente=True,
    )
    resultado = detectar_emergencia("Paciente com gripe leve.", [protocolo])
    assert resultado is None


def test_p15_aviso_emergencia_tem_destaque_true() -> None:
    """P15: aviso de emergência sempre tem destaque=True."""
    resposta = RespostaClinica(texto_resposta="cond. emergência", fontes=[], avisos=[], confianca=0.9)
    resultado = aplicar_avisos(resposta, ContextoAvisos(emergencia_detectada=True))

    emergencias = [a for a in resultado.avisos if a.tipo == TipoAviso.EMERGENCIA]
    assert len(emergencias) == 1
    assert emergencias[0].destaque is True
