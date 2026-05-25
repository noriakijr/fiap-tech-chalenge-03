from app.models.domain import Prontuario
from app.services.prontuario_validator import (
    CAMPOS_OBRIGATORIOS,
    validar_campos_obrigatorios,
)


def test_prontuario_completo_retorna_vazio() -> None:
    p = Prontuario(
        numero="PRT-1",
        diagnostico_ativo="sepse",
        medicamentos_em_uso=["med"],
        alergias=["sulfa"],
    )
    assert validar_campos_obrigatorios(p) == []


def test_diagnostico_ativo_ausente_quando_none() -> None:
    p = Prontuario(
        numero="PRT-1",
        diagnostico_ativo=None,
        medicamentos_em_uso=["m"],
        alergias=["a"],
    )
    assert validar_campos_obrigatorios(p) == ["diagnostico_ativo"]


def test_diagnostico_ativo_ausente_quando_string_em_branco() -> None:
    p = Prontuario(
        numero="PRT-1",
        diagnostico_ativo="   ",
        medicamentos_em_uso=["m"],
        alergias=["a"],
    )
    assert validar_campos_obrigatorios(p) == ["diagnostico_ativo"]


def test_medicamentos_em_uso_vazio_e_ausente() -> None:
    p = Prontuario(
        numero="PRT-1",
        diagnostico_ativo="x",
        medicamentos_em_uso=[],
        alergias=["a"],
    )
    assert validar_campos_obrigatorios(p) == ["medicamentos_em_uso"]


def test_alergias_vazias_e_ausente() -> None:
    p = Prontuario(
        numero="PRT-1",
        diagnostico_ativo="x",
        medicamentos_em_uso=["m"],
        alergias=[],
    )
    assert validar_campos_obrigatorios(p) == ["alergias"]


def test_todos_os_campos_ausentes() -> None:
    p = Prontuario(numero="PRT-1")
    assert validar_campos_obrigatorios(p) == list(CAMPOS_OBRIGATORIOS)


def test_ordem_de_campos_eh_a_definida() -> None:
    assert CAMPOS_OBRIGATORIOS == (
        "diagnostico_ativo",
        "medicamentos_em_uso",
        "alergias",
    )
