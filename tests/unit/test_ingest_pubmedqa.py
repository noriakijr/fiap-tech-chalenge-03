from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

from app.models.domain import DecisaoFinal, ReasoningRequired
from app.rag.ingest_pubmedqa import (
    PubMedQAInvalidoError,
    carregar_indice_faiss,
    carregar_pubmedqa,
    construir_indice_faiss,
    para_documents,
)


class HashEmbeddings(Embeddings):
    """Embedding determinístico baseado em hash MD5 — sem rede e reprodutível."""

    def __init__(self, size: int = 16) -> None:
        self.size = size

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.md5(text.encode("utf-8")).digest()
        return [digest[i % 16] / 255.0 for i in range(self.size)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def _entrada_obj(**overrides) -> dict:
    base = {
        "QUESTION": "Pergunta clínica?",
        "CONTEXTS": ["trecho A", "trecho B"],
        "LABELS": ["RESULTS", "CONCLUSIONS"],
        "MESHES": ["Sepsis"],
        "YEAR": 2022,
        "reasoning_required_pred": "no",
        "final_decision": "yes",
        "LONG_ANSWER": "explicacao",
    }
    base.update(overrides)
    return base


def test_carrega_formato_objeto_indexado_por_id(tmp_path: Path) -> None:
    arquivo = tmp_path / "pq.json"
    arquivo.write_text(
        json.dumps(
            {
                "PMID-1": _entrada_obj(),
                "PMID-2": _entrada_obj(YEAR=2020, final_decision="maybe"),
            }
        ),
        encoding="utf-8",
    )
    entradas = carregar_pubmedqa(arquivo)
    ids = {e.id for e in entradas}
    assert ids == {"PMID-1", "PMID-2"}


def test_carrega_formato_lista(tmp_path: Path) -> None:
    arquivo = tmp_path / "pq.json"
    arquivo.write_text(
        json.dumps([{"id": "X1", **_entrada_obj()}, {"id": "X2", **_entrada_obj()}]),
        encoding="utf-8",
    )
    entradas = carregar_pubmedqa(arquivo)
    assert {e.id for e in entradas} == {"X1", "X2"}


def test_year_string_aceito(tmp_path: Path) -> None:
    arquivo = tmp_path / "pq.json"
    arquivo.write_text(
        json.dumps({"PMID-1": {**_entrada_obj(), "YEAR": "2021"}}),
        encoding="utf-8",
    )
    entradas = carregar_pubmedqa(arquivo)
    assert entradas[0].YEAR == 2021


def test_decisao_invalida_levanta(tmp_path: Path) -> None:
    arquivo = tmp_path / "pq.json"
    arquivo.write_text(
        json.dumps({"PMID-1": {**_entrada_obj(), "final_decision": "talvez"}}),
        encoding="utf-8",
    )
    with pytest.raises(PubMedQAInvalidoError):
        carregar_pubmedqa(arquivo)


def test_arquivo_inexistente_levanta(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        carregar_pubmedqa(tmp_path / "nope.json")


def test_json_invalido_levanta(tmp_path: Path) -> None:
    arquivo = tmp_path / "pq.json"
    arquivo.write_text("{{{", encoding="utf-8")
    with pytest.raises(PubMedQAInvalidoError):
        carregar_pubmedqa(arquivo)


def test_para_documents_metadata_completa() -> None:
    arquivo = Path(__file__).resolve().parents[2] / "data" / "pubmedqa" / "sample.json"
    entradas = carregar_pubmedqa(arquivo)
    docs = para_documents(entradas)

    assert len(docs) == len(entradas)
    doc1 = next(d for d in docs if d.metadata["id"] == "PMID-1001")
    assert doc1.metadata["tipo"] == "artigo"
    assert doc1.metadata["YEAR"] == 2022
    assert doc1.metadata["final_decision"] == "yes"
    assert doc1.metadata["reasoning_required_pred"] == "no"
    assert "Sepsis" in doc1.metadata["MESHES"]
    assert "QUESTION:" in doc1.page_content
    assert "[RESULTS]" in doc1.page_content


def test_construir_indice_e_recarregar(tmp_path: Path) -> None:
    arquivo = Path(__file__).resolve().parents[2] / "data" / "pubmedqa" / "sample.json"
    entradas = carregar_pubmedqa(arquivo)
    docs = para_documents(entradas)

    embeddings = HashEmbeddings(size=16)
    destino = tmp_path / "faiss_index"

    indice = construir_indice_faiss(docs, embeddings, destino)
    assert (destino / "index.faiss").exists()
    assert (destino / "index.pkl").exists()

    recarregado = carregar_indice_faiss(destino, embeddings)
    encontrados = recarregado.similarity_search("antibiótico empírico em sepse", k=3)
    assert len(encontrados) == 3
    for d in encontrados:
        assert d.metadata["tipo"] == "artigo"


def test_indice_aplica_filtro_por_metadata() -> None:
    arquivo = Path(__file__).resolve().parents[2] / "data" / "pubmedqa" / "sample.json"
    docs = para_documents(carregar_pubmedqa(arquivo))
    indice = construir_indice_faiss(docs, HashEmbeddings())

    encontrados = indice.similarity_search(
        "qualquer consulta",
        k=10,
        filter={"final_decision": "no"},
    )
    assert encontrados, "Esperava ao menos um documento com final_decision='no'"
    for d in encontrados:
        assert d.metadata["final_decision"] == "no"


def test_construir_indice_lista_vazia_levanta() -> None:
    with pytest.raises(ValueError):
        construir_indice_faiss([], HashEmbeddings())


def test_sample_dataset_cobre_todas_as_decisoes() -> None:
    arquivo = Path(__file__).resolve().parents[2] / "data" / "pubmedqa" / "sample.json"
    entradas = carregar_pubmedqa(arquivo)
    decisoes = {e.final_decision for e in entradas}
    reasoning = {e.reasoning_required_pred for e in entradas}
    assert {DecisaoFinal.YES, DecisaoFinal.NO, DecisaoFinal.MAYBE} <= decisoes
    assert {ReasoningRequired.YES, ReasoningRequired.NO} <= reasoning
