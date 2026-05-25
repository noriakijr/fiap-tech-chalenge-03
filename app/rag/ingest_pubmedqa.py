"""Ingestão da Base de Conhecimento PubMedQA.

Camadas:

- `carregar_pubmedqa(path) -> list[EntradaPubMedQA]`: parser puro, testável sem
  rede.
- `para_documents(entradas) -> list[Document]`: converte para Documents
  LangChain com metadata (id, MESHES, final_decision, reasoning_required_pred,
  YEAR), preservando os CONTEXTS.
- `construir_indice_faiss(documents, embeddings, destino)`: usa as embeddings
  recebidas para construir e persistir um índice FAISS.

A dependência de OpenAI fica isolada em `construir_indice_faiss`; os tests
injetam embeddings determinísticas (sem rede).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.models.domain import EntradaPubMedQA


class PubMedQAInvalidoError(ValueError):
    """Levantado quando uma entrada não respeita o schema PubMedQA."""


def _normalizar_year(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise PubMedQAInvalidoError(f"YEAR inválido: {value!r}")


def _to_entrada(id_: str, raw: dict[str, Any]) -> EntradaPubMedQA:
    payload = {
        "id": id_,
        "QUESTION": raw.get("QUESTION"),
        "CONTEXTS": list(raw.get("CONTEXTS") or []),
        "LABELS": list(raw.get("LABELS") or []),
        "MESHES": list(raw.get("MESHES") or []),
        "YEAR": _normalizar_year(raw.get("YEAR")),
        "reasoning_required_pred": raw.get("reasoning_required_pred"),
        "final_decision": raw.get("final_decision"),
        "LONG_ANSWER": raw.get("LONG_ANSWER", "") or "",
    }
    try:
        return EntradaPubMedQA(**payload)
    except Exception as exc:
        raise PubMedQAInvalidoError(
            f"Entrada PubMedQA {id_!r} inválida: {exc}"
        ) from exc


def carregar_pubmedqa(path: str | Path) -> list[EntradaPubMedQA]:
    """Lê arquivo JSON no formato PubMedQA.

    Aceita dois formatos:
    - Objeto: `{ "<id>": { "QUESTION": ..., ... }, ... }` (formato oficial).
    - Lista: `[ { "id": "...", "QUESTION": ..., ... }, ... ]` (sem necessidade
      de chave externa).
    """

    arquivo = Path(path)
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo PubMedQA não encontrado: {arquivo}")

    try:
        conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PubMedQAInvalidoError(f"JSON inválido em {arquivo}: {exc}") from exc

    if isinstance(conteudo, dict):
        return [_to_entrada(id_, raw) for id_, raw in conteudo.items()]
    if isinstance(conteudo, list):
        entradas = []
        for item in conteudo:
            if not isinstance(item, dict) or "id" not in item:
                raise PubMedQAInvalidoError(
                    "Lista PubMedQA deve conter objetos com campo `id`."
                )
            id_ = item.pop("id")
            entradas.append(_to_entrada(id_, item))
        return entradas
    raise PubMedQAInvalidoError(
        f"Arquivo {arquivo} deve conter objeto ou lista de objetos."
    )


def para_documents(entradas: Iterable[EntradaPubMedQA]) -> list[Document]:
    """Converte entradas em Documents LangChain.

    Estratégia: um Document por entrada, com `page_content` agregando a
    pergunta clínica e os trechos de CONTEXTS (necessários para que a busca
    semântica recupere o conteúdo do artigo). Metadados incluem todos os
    campos usados pelos filtros do retriever (Requisitos 1.3, 1.4, 4.3).
    """

    docs: list[Document] = []
    for entrada in entradas:
        partes = [f"QUESTION: {entrada.QUESTION}"]
        for label, ctx in zip(entrada.LABELS, entrada.CONTEXTS, strict=False):
            partes.append(f"[{label}] {ctx}")
        if not entrada.LABELS:
            partes.extend(entrada.CONTEXTS)
        if entrada.LONG_ANSWER:
            partes.append(f"LONG_ANSWER: {entrada.LONG_ANSWER}")

        metadata = {
            "tipo": "artigo",
            "id": entrada.id,
            "QUESTION": entrada.QUESTION,
            "YEAR": entrada.YEAR,
            "MESHES": list(entrada.MESHES),
            "final_decision": entrada.final_decision.value,
            "reasoning_required_pred": entrada.reasoning_required_pred.value,
            "CONTEXTS": list(entrada.CONTEXTS),
            "LONG_ANSWER": entrada.LONG_ANSWER,
        }
        docs.append(Document(page_content="\n\n".join(partes), metadata=metadata))
    return docs


def construir_indice_faiss(
    documents: list[Document],
    embeddings: Embeddings,
    destino: str | Path | None = None,
) -> FAISS:
    """Constrói índice FAISS a partir dos Documents e persiste em disco se `destino`."""

    if not documents:
        raise ValueError("Não há documentos para indexar.")

    vectorstore = FAISS.from_documents(documents, embeddings)

    if destino is not None:
        destino_path = Path(destino)
        destino_path.mkdir(parents=True, exist_ok=True)
        vectorstore.save_local(str(destino_path))

    return vectorstore


def carregar_indice_faiss(
    origem: str | Path, embeddings: Embeddings
) -> FAISS:
    """Recarrega índice FAISS previamente persistido."""

    origem_path = Path(origem)
    if not origem_path.exists():
        raise FileNotFoundError(f"Índice FAISS não encontrado em {origem_path}.")

    return FAISS.load_local(
        str(origem_path),
        embeddings,
        allow_dangerous_deserialization=True,
    )
