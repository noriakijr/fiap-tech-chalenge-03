"""Ingestão de protocolos clínicos internos.

Lê arquivos JSON em `data/protocolos/` (ou caminho equivalente) e produz:

- `list[Protocolo]` (modelo Pydantic) — usado pelos serviços de emergência e
  contraindicações.
- `list[Document]` (LangChain) — usado pelo motor RAG para indexação FAISS.

O campo `texto` dos arquivos JSON não pertence ao modelo `Protocolo`; é
preservado como `page_content` do `Document`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from app.models.domain import Protocolo


class ProtocoloInvalidoError(ValueError):
    """Levantado quando um arquivo de protocolo não respeita o schema."""


def _ler_arquivo(path: Path) -> list[dict[str, Any]]:
    try:
        conteudo = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocoloInvalidoError(f"JSON inválido em {path}: {exc}") from exc

    if isinstance(conteudo, dict):
        return [conteudo]
    if isinstance(conteudo, list):
        return list(conteudo)
    raise ProtocoloInvalidoError(
        f"Arquivo {path} deve conter objeto ou lista de objetos."
    )


def _to_protocolo(raw: dict[str, Any], origem: Path) -> tuple[Protocolo, str]:
    texto = raw.pop("texto", None)
    if not isinstance(texto, str) or not texto.strip():
        raise ProtocoloInvalidoError(
            f"Protocolo em {origem} requer campo `texto` não vazio."
        )
    try:
        protocolo = Protocolo(**raw)
    except Exception as exc:  # ValidationError do Pydantic
        raise ProtocoloInvalidoError(
            f"Protocolo em {origem} inválido: {exc}"
        ) from exc
    return protocolo, texto


def carregar_protocolos(
    diretorio: str | Path,
    *,
    apenas_vigentes: bool = True,
) -> list[tuple[Protocolo, str]]:
    """Lê todos os `*.json` do diretório e retorna pares (Protocolo, texto)."""

    base = Path(diretorio)
    if not base.exists():
        raise FileNotFoundError(f"Diretório de protocolos não existe: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"{base} não é diretório.")

    resultado: list[tuple[Protocolo, str]] = []
    for arquivo in sorted(base.glob("*.json")):
        for raw in _ler_arquivo(arquivo):
            protocolo, texto = _to_protocolo(raw, arquivo)
            if apenas_vigentes and not protocolo.vigente:
                continue
            resultado.append((protocolo, texto))

    return resultado


def para_documents(pares: Iterable[tuple[Protocolo, str]]) -> list[Document]:
    """Converte (Protocolo, texto) em Documents LangChain com metadata padrão."""

    docs: list[Document] = []
    for protocolo, texto in pares:
        metadata = {
            "tipo": "protocolo",
            "id": protocolo.id,
            "titulo": protocolo.titulo,
            "nivel_evidencia": protocolo.nivel_evidencia,
            "condicoes_aplicaveis": list(protocolo.condicoes_aplicaveis),
            "contraindicacoes": list(protocolo.contraindicacoes),
            "termos_emergencia": list(protocolo.termos_emergencia),
            "vigente": protocolo.vigente,
        }
        docs.append(Document(page_content=texto, metadata=metadata))
    return docs
