"""Motor RAG: recuperação de documentos + geração da resposta clínica.

Esta classe é o núcleo da Fase 2. Recebe vectorstore e LLM por injeção para
permitir testes determinísticos (sem rede). A produção monta o motor com
`FAISS.load_local(...)` + `ChatOpenAI(temperature=0.1)`.

Regras críticas:
- Artigos com `final_decision == "no"` são excluídos do retorno quando
  `excluir_decisao_final=["no"]` (Requisito 4.3).
- Artigos com `final_decision == "maybe"` são preservados e passam adiante para
  o orquestrador adicionar o aviso de inconclusividade (Requisito 1.3,
  Propriedade 2).
- Artigos com `reasoning_required_pred == "yes"` carregam `LONG_ANSWER`
  populado no `DocumentoRecuperado` (Requisito 1.4, Propriedade 3).
- `aviso_baixa_confianca` é `True` se e somente se `confianca_geral` < limiar
  configurado (Propriedade 10).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from app.models.domain import (
    DecisaoFinal,
    DocumentoRecuperado,
    ReasoningRequired,
    RespostaRAG,
    TipoFonte,
)

logger = logging.getLogger(__name__)


_PROMPT_PADRAO = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "Você é um assistente médico que responde em português do Brasil "
                "apoiando decisões clínicas. Use exclusivamente os documentos "
                "fornecidos como contexto. Cite os identificadores entre colchetes "
                "(ex.: [PMID-1001], [PROT-SEPSE-001]). Se a evidência for "
                "inconclusiva, deixe isso explícito. Não substitua o julgamento "
                "clínico do médico."
            ),
        ),
        (
            "human",
            (
                "Pergunta: {pergunta}\n\n"
                "Contexto recuperado:\n{contexto}\n\n"
                "Responda de forma objetiva, citando as fontes utilizadas."
            ),
        ),
    ]
)


def _score_a_similaridade(distance: float) -> float:
    """Converte distância L2 do FAISS em similaridade aproximada em [0,1]."""

    if distance < 0:
        distance = 0.0
    return 1.0 / (1.0 + distance)


def _extrair_texto(saida: Any) -> str:
    if isinstance(saida, BaseMessage):
        content = saida.content
        if isinstance(content, str):
            return content
        return str(content)
    if isinstance(saida, str):
        return saida
    return str(saida)


def _document_para_recuperado(doc: Document, score: float) -> DocumentoRecuperado:
    tipo_str = doc.metadata.get("tipo")
    if tipo_str == "protocolo":
        return DocumentoRecuperado(
            tipo=TipoFonte.PROTOCOLO,
            identificador=doc.metadata["id"],
            titulo=doc.metadata.get("titulo") or doc.metadata["id"],
            contextos=[doc.page_content],
            meshes=list(doc.metadata.get("condicoes_aplicaveis") or []),
            score_relevancia=score,
        )

    reasoning = doc.metadata.get("reasoning_required_pred") == ReasoningRequired.YES.value
    return DocumentoRecuperado(
        tipo=TipoFonte.ARTIGO,
        identificador=doc.metadata["id"],
        titulo=doc.metadata.get("QUESTION") or doc.metadata["id"],
        ano=doc.metadata.get("YEAR"),
        decisao_final=DecisaoFinal(doc.metadata["final_decision"]),
        reasoning_required=reasoning,
        contextos=list(doc.metadata.get("CONTEXTS") or []),
        meshes=list(doc.metadata.get("MESHES") or []),
        long_answer=doc.metadata.get("LONG_ANSWER") if reasoning else None,
        score_relevancia=score,
    )


def _construir_filtro(
    filtros_mesh: list[str] | None,
    excluir_decisao_final: list[str] | None,
):
    """Cria callable de filtro compatível com FAISS.similarity_search."""

    mesh_norm = [m.lower() for m in (filtros_mesh or []) if m]
    excluir = set(excluir_decisao_final or [])

    if not mesh_norm and not excluir:
        return None

    def filtro(metadata: dict[str, Any]) -> bool:
        if excluir and metadata.get("final_decision") in excluir:
            return False
        if mesh_norm:
            meshes_doc = [m.lower() for m in (metadata.get("MESHES") or [])]
            condicoes_doc = [
                c.lower() for c in (metadata.get("condicoes_aplicaveis") or [])
            ]
            termos_doc = set(meshes_doc + condicoes_doc)
            if not any(termo in t for t in termos_doc for termo in mesh_norm):
                return False
        return True

    return filtro


class MotorRAG:
    def __init__(
        self,
        vectorstore: FAISS,
        llm: BaseLanguageModel,
        confidence_threshold: float = 0.65,
        prompt: ChatPromptTemplate | None = None,
    ) -> None:
        self._vectorstore = vectorstore
        self._llm = llm
        self._threshold = confidence_threshold
        self._prompt = prompt or _PROMPT_PADRAO

    def recuperar_e_gerar(
        self,
        consulta: str,
        filtros_mesh: list[str] | None = None,
        excluir_decisao_final: list[str] | None = None,
        limite: int = 10,
    ) -> RespostaRAG:
        if not consulta or not consulta.strip():
            raise ValueError("Consulta vazia.")
        if limite <= 0:
            raise ValueError("Limite deve ser > 0.")

        filtro = _construir_filtro(filtros_mesh, excluir_decisao_final)

        resultados: list[tuple[Document, float]] = (
            self._vectorstore.similarity_search_with_score(
                consulta,
                k=limite,
                filter=filtro,
            )
        )

        documentos = [
            _document_para_recuperado(doc, _score_a_similaridade(score))
            for doc, score in resultados
        ]

        confianca = (
            sum(d.score_relevancia for d in documentos) / len(documentos)
            if documentos
            else 0.0
        )

        contexto = self._formatar_contexto(documentos)
        mensagens = self._prompt.format_messages(pergunta=consulta, contexto=contexto)
        saida = self._llm.invoke(mensagens)
        texto = _extrair_texto(saida).strip()

        return RespostaRAG(
            resposta_texto=texto,
            documentos=documentos,
            confianca_geral=confianca,
            aviso_baixa_confianca=confianca < self._threshold,
        )

    @staticmethod
    def _formatar_contexto(documentos: list[DocumentoRecuperado]) -> str:
        if not documentos:
            return "(nenhum documento relevante encontrado)"
        partes: list[str] = []
        for doc in documentos:
            cabecalho = f"[{doc.identificador}] {doc.titulo}"
            if doc.ano:
                cabecalho += f" ({doc.ano})"
            if doc.decisao_final:
                cabecalho += f" — decisão: {doc.decisao_final.value}"
            partes.append(cabecalho)
            for ctx in doc.contextos:
                partes.append(f"  - {ctx}")
            if doc.long_answer:
                partes.append(f"  LONG_ANSWER: {doc.long_answer}")
        return "\n".join(partes)
