import pytest

from app.models.domain import DecisaoFinal, DocumentoRecuperado, TipoFonte
from app.services.ordenacao import ordenar_condutas


def _protocolo(id_: str, meshes: list[str], score: float = 0.5) -> DocumentoRecuperado:
    return DocumentoRecuperado(
        tipo=TipoFonte.PROTOCOLO,
        identificador=id_,
        titulo=f"Protocolo {id_}",
        meshes=meshes,
        score_relevancia=score,
    )


def _artigo(
    id_: str, ano: int, decisao: DecisaoFinal = DecisaoFinal.YES, score: float = 0.5
) -> DocumentoRecuperado:
    return DocumentoRecuperado(
        tipo=TipoFonte.ARTIGO,
        identificador=id_,
        titulo=f"Artigo {id_}",
        ano=ano,
        decisao_final=decisao,
        score_relevancia=score,
    )


def test_protocolos_aparecem_antes_de_artigos() -> None:
    resultado = ordenar_condutas(
        protocolos=[_protocolo("P1", ["sepse"])],
        artigos=[_artigo("A1", 2024)],
        quadro_clinico="paciente com sepse grave",
    )

    assert [d.identificador for d in resultado] == ["P1", "A1"]


def test_artigos_ordenados_por_ano_desc() -> None:
    resultado = ordenar_condutas(
        protocolos=[],
        artigos=[
            _artigo("A1", 2018),
            _artigo("A2", 2024),
            _artigo("A3", 2021),
        ],
        quadro_clinico="",
    )

    assert [d.identificador for d in resultado] == ["A2", "A3", "A1"]


def test_protocolos_ordenados_por_cobertura_desc() -> None:
    resultado = ordenar_condutas(
        protocolos=[
            _protocolo("P_pouco", ["asma"]),
            _protocolo("P_muito", ["sepse", "choque", "hipotensao"]),
            _protocolo("P_medio", ["sepse", "asma"]),
        ],
        artigos=[],
        quadro_clinico="paciente com sepse choque e hipotensao",
    )

    assert [d.identificador for d in resultado] == ["P_muito", "P_medio", "P_pouco"]


def test_empate_de_cobertura_desfeito_por_identificador() -> None:
    resultado = ordenar_condutas(
        protocolos=[
            _protocolo("PB", ["x"]),
            _protocolo("PA", ["x"]),
            _protocolo("PC", ["x"]),
        ],
        artigos=[],
        quadro_clinico="paciente com x",
    )

    assert [d.identificador for d in resultado] == ["PA", "PB", "PC"]


def test_limite_de_5_protocolos() -> None:
    protocolos = [_protocolo(f"P{i:02d}", ["sepse"]) for i in range(10)]
    resultado = ordenar_condutas(
        protocolos=protocolos,
        artigos=[],
        quadro_clinico="sepse",
    )

    assert len(resultado) == 5
    assert [d.identificador for d in resultado] == [f"P{i:02d}" for i in range(5)]


def test_max_protocolos_customizado() -> None:
    protocolos = [_protocolo(f"P{i}", ["x"]) for i in range(4)]
    resultado = ordenar_condutas(
        protocolos=protocolos,
        artigos=[],
        quadro_clinico="x",
        max_protocolos=2,
    )

    assert len(resultado) == 2


def test_listas_vazias_retornam_vazio() -> None:
    assert ordenar_condutas(protocolos=[], artigos=[], quadro_clinico="x") == []


def test_artigo_em_protocolos_falha_validacao() -> None:
    with pytest.raises(ValueError):
        ordenar_condutas(
            protocolos=[_artigo("A1", 2024)],  # tipo errado
            artigos=[],
        )


def test_protocolo_em_artigos_falha_validacao() -> None:
    with pytest.raises(ValueError):
        ordenar_condutas(
            protocolos=[],
            artigos=[_protocolo("P1", ["x"])],
        )


def test_artigo_sem_ano_vai_para_o_final() -> None:
    resultado = ordenar_condutas(
        protocolos=[],
        artigos=[
            DocumentoRecuperado(
                tipo=TipoFonte.ARTIGO,
                identificador="A_sem_ano",
                titulo="Sem Ano",
                decisao_final=DecisaoFinal.YES,
                score_relevancia=0.4,
            ),
            _artigo("A1", 2020),
        ],
        quadro_clinico="",
    )

    assert [d.identificador for d in resultado] == ["A1", "A_sem_ano"]
