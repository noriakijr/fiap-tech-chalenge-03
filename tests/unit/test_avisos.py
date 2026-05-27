"""Testes para app/orchestrator/avisos.py (Task 5.2)."""

from __future__ import annotations

import pytest

from app.models.domain import (
    Aviso,
    DecisaoFinal,
    DocumentoRecuperado,
    RespostaClinica,
    RespostaRAG,
    TipoAviso,
    TipoFonte,
)
from app.orchestrator.avisos import ContextoAvisos, aplicar_avisos


def _resposta_vazia(confianca: float = 0.9) -> RespostaClinica:
    return RespostaClinica(texto_resposta="ok", fontes=[], avisos=[], confianca=confianca)


def _rag(
    confianca: float = 0.9,
    aviso_baixa: bool = False,
    documentos: list[DocumentoRecuperado] | None = None,
) -> RespostaRAG:
    return RespostaRAG(
        resposta_texto="resp",
        documentos=documentos or [],
        confianca_geral=confianca,
        aviso_baixa_confianca=aviso_baixa,
    )


def _artigo(
    id_: str,
    decisao: DecisaoFinal = DecisaoFinal.YES,
    reasoning: bool = False,
) -> DocumentoRecuperado:
    return DocumentoRecuperado(
        tipo=TipoFonte.ARTIGO,
        identificador=id_,
        titulo=f"Artigo {id_}",
        decisao_final=decisao,
        reasoning_required=reasoning,
        score_relevancia=0.8,
    )


def _protocolo(id_: str) -> DocumentoRecuperado:
    return DocumentoRecuperado(
        tipo=TipoFonte.PROTOCOLO,
        identificador=id_,
        titulo=f"Protocolo {id_}",
        score_relevancia=0.7,
    )


# ------------------------------------------------------------------ #
# APOIO_DECISAO sempre presente                                        #
# ------------------------------------------------------------------ #


def test_apoio_decisao_sem_rag() -> None:
    resultado = aplicar_avisos(_resposta_vazia(), ContextoAvisos())
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.APOIO_DECISAO in tipos


def test_apoio_decisao_com_rag_alta_confianca() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(resposta_rag=_rag(confianca=0.95), confidence_threshold=0.65),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.APOIO_DECISAO in tipos


def test_apoio_decisao_nao_duplicado() -> None:
    resposta = _resposta_vazia().model_copy(
        update={
            "avisos": [
                Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="já existe", destaque=False)
            ]
        }
    )
    resultado = aplicar_avisos(resposta, ContextoAvisos())
    contagem = sum(1 for a in resultado.avisos if a.tipo == TipoAviso.APOIO_DECISAO)
    assert contagem == 1


# ------------------------------------------------------------------ #
# BAIXA_CONFIANCA                                                      #
# ------------------------------------------------------------------ #


def test_baixa_confianca_quando_abaixo_do_limiar() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(resposta_rag=_rag(confianca=0.5), confidence_threshold=0.65),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.BAIXA_CONFIANCA in tipos


def test_baixa_confianca_quando_flag_ativo() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(
            resposta_rag=_rag(confianca=0.9, aviso_baixa=True),
            confidence_threshold=0.65,
        ),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.BAIXA_CONFIANCA in tipos


def test_sem_baixa_confianca_quando_acima_do_limiar() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(resposta_rag=_rag(confianca=0.8), confidence_threshold=0.65),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.BAIXA_CONFIANCA not in tipos


def test_sem_baixa_confianca_sem_rag() -> None:
    resultado = aplicar_avisos(_resposta_vazia(), ContextoAvisos())
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.BAIXA_CONFIANCA not in tipos


# ------------------------------------------------------------------ #
# EVIDENCIA_INCONCLUSIVA                                               #
# ------------------------------------------------------------------ #


def test_evidencia_inconclusiva_com_artigo_maybe() -> None:
    docs = [_artigo("A1", DecisaoFinal.MAYBE)]
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(resposta_rag=_rag(documentos=docs)),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.EVIDENCIA_INCONCLUSIVA in tipos


def test_sem_evidencia_inconclusiva_com_artigo_yes() -> None:
    docs = [_artigo("A1", DecisaoFinal.YES)]
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(resposta_rag=_rag(documentos=docs)),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.EVIDENCIA_INCONCLUSIVA not in tipos


def test_sem_evidencia_inconclusiva_com_protocolo_maybe_tipo_ignorado() -> None:
    # Protocolos não têm decisao_final — não disparam aviso
    docs = [_protocolo("P1")]
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(resposta_rag=_rag(documentos=docs)),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.EVIDENCIA_INCONCLUSIVA not in tipos


# ------------------------------------------------------------------ #
# RACIOCINIO_NECESSARIO                                                #
# ------------------------------------------------------------------ #


def test_raciocinio_necessario_quando_reasoning_required() -> None:
    docs = [_artigo("A1", reasoning=True)]
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(resposta_rag=_rag(documentos=docs)),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.RACIOCINIO_NECESSARIO in tipos


def test_sem_raciocinio_quando_nao_requerido() -> None:
    docs = [_artigo("A1", reasoning=False)]
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(resposta_rag=_rag(documentos=docs)),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.RACIOCINIO_NECESSARIO not in tipos


# ------------------------------------------------------------------ #
# EMERGENCIA                                                           #
# ------------------------------------------------------------------ #


def test_emergencia_quando_detectada() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(emergencia_detectada=True),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.EMERGENCIA in tipos


def test_emergencia_tem_destaque() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(emergencia_detectada=True),
    )
    aviso_emerg = next(a for a in resultado.avisos if a.tipo == TipoAviso.EMERGENCIA)
    assert aviso_emerg.destaque is True


def test_sem_emergencia_quando_nao_detectada() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(emergencia_detectada=False),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.EMERGENCIA not in tipos


# ------------------------------------------------------------------ #
# FORA_PROTOCOLO                                                       #
# ------------------------------------------------------------------ #


def test_fora_protocolo_quando_flag_ativo() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(fora_protocolo=True),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.FORA_PROTOCOLO in tipos


def test_sem_fora_protocolo_quando_flag_inativo() -> None:
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(fora_protocolo=False),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert TipoAviso.FORA_PROTOCOLO not in tipos


# ------------------------------------------------------------------ #
# Combinações e preservação de avisos existentes                       #
# ------------------------------------------------------------------ #


def test_avisos_existentes_sao_preservados() -> None:
    aviso_existente = Aviso(
        tipo=TipoAviso.FORA_PROTOCOLO, mensagem="já marcado", destaque=False
    )
    resposta = _resposta_vazia().model_copy(update={"avisos": [aviso_existente]})
    resultado = aplicar_avisos(
        resposta,
        ContextoAvisos(fora_protocolo=True),
    )
    fora_avisos = [a for a in resultado.avisos if a.tipo == TipoAviso.FORA_PROTOCOLO]
    assert len(fora_avisos) == 1
    assert fora_avisos[0].mensagem == "já marcado"


def test_multiplos_avisos_simultaneos() -> None:
    docs = [_artigo("A1", DecisaoFinal.MAYBE, reasoning=True)]
    resultado = aplicar_avisos(
        _resposta_vazia(),
        ContextoAvisos(
            resposta_rag=_rag(confianca=0.3, documentos=docs),
            emergencia_detectada=True,
            fora_protocolo=True,
            confidence_threshold=0.65,
        ),
    )
    tipos = {a.tipo for a in resultado.avisos}
    assert tipos == {
        TipoAviso.APOIO_DECISAO,
        TipoAviso.BAIXA_CONFIANCA,
        TipoAviso.EVIDENCIA_INCONCLUSIVA,
        TipoAviso.RACIOCINIO_NECESSARIO,
        TipoAviso.EMERGENCIA,
        TipoAviso.FORA_PROTOCOLO,
    }
