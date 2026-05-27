"""Testes para app/services/mesh_mapper.py (Task 5.3)."""

from __future__ import annotations

import json

import pytest
from langchain_community.llms.fake import FakeListLLM

from app.services.mesh_mapper import MapadorMeSH


def _llm(responses: list[str]) -> FakeListLLM:
    return FakeListLLM(responses=responses)


def _mapper(responses: list[str]) -> MapadorMeSH:
    return MapadorMeSH(_llm(responses))


# ------------------------------------------------------------------ #
# Mapeamento básico                                                    #
# ------------------------------------------------------------------ #


def test_mapeia_termos_para_mesh() -> None:
    resposta = json.dumps(["Hypertension", "Diabetes Mellitus, Type 2"])
    mapper = _mapper([resposta])
    resultado = mapper.mapear_para_mesh(["hipertensão", "diabetes tipo 2"])
    assert resultado == ["Hypertension", "Diabetes Mellitus, Type 2"]


def test_aceita_resposta_com_cerca_markdown() -> None:
    resposta = '```json\n["Sepsis"]\n```'
    mapper = _mapper([resposta])
    resultado = mapper.mapear_para_mesh(["sepse"])
    assert resultado == ["Sepsis"]


def test_aceita_array_embutido_em_texto() -> None:
    resposta = 'Os descritores MeSH são: ["Pneumonia"] para sua consulta.'
    mapper = _mapper([resposta])
    resultado = mapper.mapear_para_mesh(["pneumonia"])
    assert resultado == ["Pneumonia"]


def test_retorna_vazio_para_lista_vazia() -> None:
    mapper = _mapper([])
    assert mapper.mapear_para_mesh([]) == []


def test_retorna_vazio_para_termos_apenas_espacos() -> None:
    mapper = _mapper([])
    assert mapper.mapear_para_mesh(["  ", "", "\t"]) == []


# ------------------------------------------------------------------ #
# Cache determinístico                                                 #
# ------------------------------------------------------------------ #


def test_cache_retorna_mesmo_resultado() -> None:
    resposta = json.dumps(["Heart Failure"])
    mapper = _mapper([resposta])  # LLM só tem 1 resposta

    r1 = mapper.mapear_para_mesh(["insuficiência cardíaca"])
    r2 = mapper.mapear_para_mesh(["insuficiência cardíaca"])  # deve vir do cache

    assert r1 == r2 == ["Heart Failure"]


def test_cache_insensivel_a_ordem_dos_termos() -> None:
    resposta = json.dumps(["Asthma", "Hypertension"])
    mapper = _mapper([resposta])

    r1 = mapper.mapear_para_mesh(["asma", "hipertensão"])
    r2 = mapper.mapear_para_mesh(["hipertensão", "asma"])  # ordem invertida

    assert r1 == r2


def test_cache_diferente_para_termos_distintos() -> None:
    r1 = json.dumps(["Asthma"])
    r2 = json.dumps(["Hypertension"])
    mapper = _mapper([r1, r2])

    res1 = mapper.mapear_para_mesh(["asma"])
    res2 = mapper.mapear_para_mesh(["hipertensão"])

    assert res1 == ["Asthma"]
    assert res2 == ["Hypertension"]


# ------------------------------------------------------------------ #
# Resiliência                                                          #
# ------------------------------------------------------------------ #


def test_retorna_vazio_quando_llm_falha() -> None:
    class LLMQuebrado:
        def invoke(self, *_, **__):
            raise RuntimeError("sem rede")

    mapper = MapadorMeSH(LLMQuebrado())  # type: ignore[arg-type]
    resultado = mapper.mapear_para_mesh(["sepse"])
    assert resultado == []


def test_retorna_vazio_quando_resposta_nao_e_json() -> None:
    mapper = _mapper(["isso não é JSON e nem array"])
    resultado = mapper.mapear_para_mesh(["condicao"])
    assert resultado == []


def test_filtra_strings_vazias_do_resultado() -> None:
    resposta = json.dumps(["Sepsis", "", "  ", "Pneumonia"])
    mapper = _mapper([resposta])
    resultado = mapper.mapear_para_mesh(["sepse pneumonia"])
    assert resultado == ["Sepsis", "Pneumonia"]
