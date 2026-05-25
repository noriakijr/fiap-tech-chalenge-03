from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rag.ingest_protocolos import (
    ProtocoloInvalidoError,
    carregar_protocolos,
    para_documents,
)


def _escrever(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _proto_dict(id_: str = "PROT-1", vigente: bool = True, **overrides) -> dict:
    base = {
        "id": id_,
        "titulo": f"Protocolo {id_}",
        "nivel_evidencia": "A",
        "condicoes_aplicaveis": ["sepse"],
        "contraindicacoes": [],
        "termos_emergencia": ["choque séptico"],
        "vigente": vigente,
        "texto": "corpo do protocolo",
    }
    base.update(overrides)
    return base


def test_carrega_um_protocolo_simples(tmp_path: Path) -> None:
    _escrever(tmp_path / "p1.json", _proto_dict())
    resultado = carregar_protocolos(tmp_path)

    assert len(resultado) == 1
    protocolo, texto = resultado[0]
    assert protocolo.id == "PROT-1"
    assert texto == "corpo do protocolo"


def test_arquivo_com_lista_de_protocolos(tmp_path: Path) -> None:
    _escrever(
        tmp_path / "varios.json",
        [_proto_dict("PROT-A"), _proto_dict("PROT-B")],
    )
    resultado = carregar_protocolos(tmp_path)
    ids = {p.id for p, _ in resultado}
    assert ids == {"PROT-A", "PROT-B"}


def test_filtra_nao_vigentes_por_padrao(tmp_path: Path) -> None:
    _escrever(tmp_path / "v.json", _proto_dict("PROT-V", vigente=True))
    _escrever(tmp_path / "x.json", _proto_dict("PROT-X", vigente=False))
    resultado = carregar_protocolos(tmp_path)
    assert [p.id for p, _ in resultado] == ["PROT-V"]


def test_apenas_vigentes_false_retorna_todos(tmp_path: Path) -> None:
    _escrever(tmp_path / "v.json", _proto_dict("PROT-V", vigente=True))
    _escrever(tmp_path / "x.json", _proto_dict("PROT-X", vigente=False))
    resultado = carregar_protocolos(tmp_path, apenas_vigentes=False)
    assert {p.id for p, _ in resultado} == {"PROT-V", "PROT-X"}


def test_arquivo_sem_texto_levanta(tmp_path: Path) -> None:
    payload = _proto_dict()
    del payload["texto"]
    _escrever(tmp_path / "p.json", payload)
    with pytest.raises(ProtocoloInvalidoError):
        carregar_protocolos(tmp_path)


def test_json_invalido_levanta(tmp_path: Path) -> None:
    (tmp_path / "p.json").write_text("{ esto-quebrado", encoding="utf-8")
    with pytest.raises(ProtocoloInvalidoError):
        carregar_protocolos(tmp_path)


def test_protocolo_com_campos_invalidos_levanta(tmp_path: Path) -> None:
    bad = _proto_dict(nivel_evidencia="")  # min_length=1
    _escrever(tmp_path / "p.json", bad)
    with pytest.raises(ProtocoloInvalidoError):
        carregar_protocolos(tmp_path)


def test_diretorio_inexistente_levanta(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        carregar_protocolos(tmp_path / "nao-existe")


def test_para_documents_gera_metadata_completa(tmp_path: Path) -> None:
    _escrever(tmp_path / "p.json", _proto_dict("PROT-1"))
    pares = carregar_protocolos(tmp_path)
    docs = para_documents(pares)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.page_content == "corpo do protocolo"
    assert doc.metadata["tipo"] == "protocolo"
    assert doc.metadata["id"] == "PROT-1"
    assert doc.metadata["titulo"] == "Protocolo PROT-1"
    assert doc.metadata["vigente"] is True
    assert doc.metadata["termos_emergencia"] == ["choque séptico"]


def test_carrega_dataset_real_do_repo() -> None:
    raiz = Path(__file__).resolve().parents[2] / "data" / "protocolos"
    pares = carregar_protocolos(raiz)
    ids = {p.id for p, _ in pares}
    assert {"PROT-SEPSE-001", "PROT-IAM-001", "PROT-PNEU-001"}.issubset(ids)
