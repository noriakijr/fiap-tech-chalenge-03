from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from langchain_community.llms.fake import FakeListLLM
from langchain_core.embeddings import Embeddings

from app.models.domain import DecisaoFinal, TipoFonte
from app.rag.engine import MotorRAG
from app.rag.ingest_protocolos import (
    carregar_protocolos,
    para_documents as protocolos_para_documents,
)
from app.rag.ingest_pubmedqa import (
    carregar_pubmedqa,
    construir_indice_faiss,
    para_documents as pubmedqa_para_documents,
)


class HashEmbeddings(Embeddings):
    def __init__(self, size: int = 32) -> None:
        self.size = size

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.md5(text.encode("utf-8")).digest()
        return [digest[i % 16] / 255.0 for i in range(self.size)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@pytest.fixture(scope="module")
def vectorstore():
    raiz = Path(__file__).resolve().parents[2]
    artigos = pubmedqa_para_documents(
        carregar_pubmedqa(raiz / "data" / "pubmedqa" / "sample.json")
    )
    protocolos = protocolos_para_documents(
        carregar_protocolos(raiz / "data" / "protocolos")
    )
    return construir_indice_faiss(artigos + protocolos, HashEmbeddings())


@pytest.fixture()
def llm():
    return FakeListLLM(
        responses=[
            "Resposta clínica simulada citando [PMID-1001] e [PROT-SEPSE-001]."
        ]
    )


def test_recupera_documentos_e_gera_resposta(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm, confidence_threshold=0.0)
    resp = motor.recuperar_e_gerar("antibiótico empírico em sepse", limite=5)

    assert resp.resposta_texto
    assert resp.documentos
    assert 0.0 <= resp.confianca_geral <= 1.0


def test_exclui_decisao_no(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm)
    resp = motor.recuperar_e_gerar(
        "qualquer pergunta sobre tratamento",
        excluir_decisao_final=["no"],
        limite=20,
    )
    decisoes = {d.decisao_final for d in resp.documentos if d.tipo == TipoFonte.ARTIGO}
    assert DecisaoFinal.NO not in decisoes


def test_inclui_decisao_maybe(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm)
    resp = motor.recuperar_e_gerar(
        "corticosteroide em pneumonia adquirida na comunidade",
        limite=20,
    )
    decisoes = {d.decisao_final for d in resp.documentos if d.tipo == TipoFonte.ARTIGO}
    assert DecisaoFinal.MAYBE in decisoes


def test_long_answer_presente_quando_reasoning_required(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm)
    resp = motor.recuperar_e_gerar("reposição volêmica", limite=20)
    artigos = [d for d in resp.documentos if d.tipo == TipoFonte.ARTIGO]
    assert artigos
    for art in artigos:
        if art.reasoning_required:
            assert art.long_answer, (
                f"{art.identificador} marcou reasoning_required mas LONG_ANSWER vazio"
            )
        else:
            assert art.long_answer is None


def test_aviso_baixa_confianca_acima_do_limiar(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm, confidence_threshold=0.0)
    resp = motor.recuperar_e_gerar("sepse e antibiótico", limite=3)
    assert resp.aviso_baixa_confianca is False


def test_aviso_baixa_confianca_abaixo_do_limiar(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm, confidence_threshold=0.99)
    resp = motor.recuperar_e_gerar("sepse e antibiótico", limite=3)
    assert resp.aviso_baixa_confianca is True


def test_filtro_mesh_restringe_resultado(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm)
    resp = motor.recuperar_e_gerar(
        "qualquer pergunta",
        filtros_mesh=["Pneumonia"],
        limite=20,
    )
    assert resp.documentos, "esperava ao menos um documento com MeSH Pneumonia"
    for d in resp.documentos:
        if d.tipo == TipoFonte.ARTIGO:
            assert any("pneumonia" in m.lower() for m in d.meshes)


def test_consulta_vazia_levanta(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm)
    with pytest.raises(ValueError):
        motor.recuperar_e_gerar("")
    with pytest.raises(ValueError):
        motor.recuperar_e_gerar("   ")


def test_limite_invalido_levanta(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm)
    with pytest.raises(ValueError):
        motor.recuperar_e_gerar("sepse", limite=0)


def test_protocolo_recuperado_sem_decisao_final(vectorstore, llm) -> None:
    motor = MotorRAG(vectorstore, llm)
    resp = motor.recuperar_e_gerar("protocolo de sepse", limite=20)
    protocolos = [d for d in resp.documentos if d.tipo == TipoFonte.PROTOCOLO]
    assert protocolos, "esperava ao menos um protocolo recuperado"
    for p in protocolos:
        assert p.decisao_final is None
        assert p.ano is None
        assert p.long_answer is None
