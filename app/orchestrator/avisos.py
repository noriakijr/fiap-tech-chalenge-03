"""Aplicação de avisos clínicos à RespostaClinica (Fase 5, Task 5.2).

Regras (Requisitos 1.3, 1.4, 1.6, 1.7, 2.5, 4.4; Propriedades 1, 2, 3, 8, 10, 15):
- APOIO_DECISAO: sempre presente.
- BAIXA_CONFIANCA: quando confiança abaixo do limiar ou flag do RAG ativo.
- EVIDENCIA_INCONCLUSIVA: quando algum artigo tem final_decision=maybe.
- RACIOCINIO_NECESSARIO: quando algum documento tem reasoning_required=True.
- EMERGENCIA: quando emergência detectada no quadro clínico.
- FORA_PROTOCOLO: quando conduta não coberta por protocolos vigentes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.domain import (
    Aviso,
    DecisaoFinal,
    DocumentoRecuperado,
    RespostaClinica,
    RespostaRAG,
    TipoAviso,
    TipoFonte,
)

_MENSAGENS: dict[TipoAviso, str] = {
    TipoAviso.APOIO_DECISAO: (
        "Este sistema é um auxílio à decisão clínica. "
        "O julgamento final é de responsabilidade exclusiva do médico."
    ),
    TipoAviso.BAIXA_CONFIANCA: (
        "A confiança da resposta está abaixo do limiar configurado. "
        "Verifique as fontes antes de tomar decisões."
    ),
    TipoAviso.EVIDENCIA_INCONCLUSIVA: (
        "Uma ou mais evidências são inconclusivas (maybe). "
        "Avalie com cautela adicional."
    ),
    TipoAviso.RACIOCINIO_NECESSARIO: (
        "Esta resposta requer raciocínio clínico aprofundado. "
        "Consulte o texto completo das fontes (LONG_ANSWER)."
    ),
    TipoAviso.EMERGENCIA: (
        "ATENÇÃO: situação de emergência detectada. "
        "Acione os protocolos de emergência imediatamente."
    ),
    TipoAviso.FORA_PROTOCOLO: (
        "A conduta sugerida não está coberta por protocolos internos vigentes."
    ),
}


@dataclass
class ContextoAvisos:
    """Informações de contexto para geração de avisos."""

    resposta_rag: RespostaRAG | None = None
    emergencia_detectada: bool = False
    fora_protocolo: bool = False
    confidence_threshold: float = 0.65


def _aviso(tipo: TipoAviso, destaque: bool = False) -> Aviso:
    return Aviso(tipo=tipo, mensagem=_MENSAGENS[tipo], destaque=destaque)


def _tem_evidencia_inconclusiva(documentos: list[DocumentoRecuperado]) -> bool:
    return any(
        d.decisao_final == DecisaoFinal.MAYBE
        for d in documentos
        if d.tipo == TipoFonte.ARTIGO
    )


def _tem_raciocinio_necessario(documentos: list[DocumentoRecuperado]) -> bool:
    return any(d.reasoning_required for d in documentos)


def aplicar_avisos(
    resposta: RespostaClinica,
    contexto: ContextoAvisos,
) -> RespostaClinica:
    """Adiciona avisos à resposta clínica conforme o contexto.

    Avisos já presentes (por tipo) não são duplicados.
    """
    tipos_existentes = {a.tipo for a in resposta.avisos}
    novos: list[Aviso] = []

    def _add(tipo: TipoAviso, destaque: bool = False) -> None:
        if tipo not in tipos_existentes:
            tipos_existentes.add(tipo)
            novos.append(_aviso(tipo, destaque))

    # Aviso fixo — sempre presente (Propriedade 1, Req 1.7)
    _add(TipoAviso.APOIO_DECISAO)

    if contexto.emergencia_detectada:
        _add(TipoAviso.EMERGENCIA, destaque=True)

    if contexto.resposta_rag is not None:
        rag = contexto.resposta_rag
        if rag.aviso_baixa_confianca or rag.confianca_geral < contexto.confidence_threshold:
            _add(TipoAviso.BAIXA_CONFIANCA)
        if _tem_evidencia_inconclusiva(rag.documentos):
            _add(TipoAviso.EVIDENCIA_INCONCLUSIVA)
        if _tem_raciocinio_necessario(rag.documentos):
            _add(TipoAviso.RACIOCINIO_NECESSARIO)

    if contexto.fora_protocolo:
        _add(TipoAviso.FORA_PROTOCOLO)

    return resposta.model_copy(update={"avisos": resposta.avisos + novos})
