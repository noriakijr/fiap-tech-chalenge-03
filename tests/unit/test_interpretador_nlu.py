from __future__ import annotations

import json

import pytest
from langchain_community.llms.fake import FakeListLLM

from app.models.domain import IntencaoClinica
from app.nlu.interpretador import InterpretadorNLU


def _llm(responses: list[dict | str]) -> FakeListLLM:
    strs = [json.dumps(r) if isinstance(r, dict) else r for r in responses]
    return FakeListLLM(responses=strs)


def test_classifica_consulta_clinica() -> None:
    payload = {
        "intencao": "CONSULTA_CLINICA",
        "entidades": {"condicao": "pneumonia"},
        "confianca": 0.92,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_llm([payload]))
    r = interp.interpretar_pergunta("Antibiótico empírico em pneumonia adquirida na comunidade?")
    assert r.intencao is IntencaoClinica.CONSULTA_CLINICA
    assert r.entidades == {"condicao": "pneumonia"}
    assert r.confianca == pytest.approx(0.92)
    assert r.requer_esclarecimento is False


def test_classifica_sugestao_conduta() -> None:
    payload = {
        "intencao": "SUGESTAO_CONDUTA",
        "entidades": {"condicao": "choque séptico"},
        "confianca": 0.85,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_llm([payload]))
    r = interp.interpretar_pergunta("Paciente com hipotensão e febre alta, qual conduta?")
    assert r.intencao is IntencaoClinica.SUGESTAO_CONDUTA


def test_classifica_verificacao_exames_com_prontuario() -> None:
    payload = {
        "intencao": "VERIFICACAO_EXAMES",
        "entidades": {"numero_prontuario": "PRT-0001"},
        "confianca": 0.97,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_llm([payload]))
    r = interp.interpretar_pergunta("Quais exames pendentes do paciente PRT-0001?")
    assert r.intencao is IntencaoClinica.VERIFICACAO_EXAMES
    assert r.entidades["numero_prontuario"] == "PRT-0001"


def test_classifica_sugestao_tratamento_com_meds() -> None:
    payload = {
        "intencao": "SUGESTAO_TRATAMENTO",
        "entidades": {
            "numero_prontuario": "PRT-0003",
            "medicamentos_mencionados": ["Salbutamol", "Prednisona"],
        },
        "confianca": 0.88,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_llm([payload]))
    r = interp.interpretar_pergunta("Sugerir tratamento para o paciente PRT-0003")
    assert r.intencao is IntencaoClinica.SUGESTAO_TRATAMENTO
    assert r.entidades["medicamentos_mencionados"] == ["Salbutamol", "Prednisona"]


def test_intencao_desconhecida_forca_esclarecimento() -> None:
    payload = {
        "intencao": "INTENCAO_DESCONHECIDA",
        "entidades": {},
        "confianca": 0.3,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_llm([payload]))
    r = interp.interpretar_pergunta("ahn?")
    assert r.intencao is IntencaoClinica.INTENCAO_DESCONHECIDA
    assert r.requer_esclarecimento is True


def test_json_invalido_cai_para_desconhecida() -> None:
    interp = InterpretadorNLU(_llm(["isso não é json"]))
    r = interp.interpretar_pergunta("qualquer coisa")
    assert r.intencao is IntencaoClinica.INTENCAO_DESCONHECIDA
    assert r.requer_esclarecimento is True
    assert r.confianca == 0.0


def test_intencao_invalida_cai_para_desconhecida() -> None:
    payload = {"intencao": "FOO_BAR", "confianca": 0.9, "idioma_detectado": "pt-BR"}
    interp = InterpretadorNLU(_llm([payload]))
    r = interp.interpretar_pergunta("teste")
    assert r.intencao is IntencaoClinica.INTENCAO_DESCONHECIDA


def test_confianca_abaixo_do_minimo_cai_para_desconhecida() -> None:
    payload = {
        "intencao": "CONSULTA_CLINICA",
        "entidades": {},
        "confianca": 0.2,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_llm([payload]), confianca_minima=0.5)
    r = interp.interpretar_pergunta("pergunta vaga")
    assert r.intencao is IntencaoClinica.INTENCAO_DESCONHECIDA
    assert r.requer_esclarecimento is True


def test_aceita_resposta_com_cerca_markdown() -> None:
    raw = '```json\n{"intencao": "CONSULTA_CLINICA", "confianca": 0.9, "idioma_detectado": "pt-BR"}\n```'
    interp = InterpretadorNLU(_llm([raw]))
    r = interp.interpretar_pergunta("teste")
    assert r.intencao is IntencaoClinica.CONSULTA_CLINICA


def test_aceita_json_embutido_em_texto() -> None:
    raw = 'Aqui está: {"intencao": "VERIFICACAO_EXAMES", "confianca": 0.8, "idioma_detectado": "pt-BR"} ok?'
    interp = InterpretadorNLU(_llm([raw]))
    r = interp.interpretar_pergunta("teste")
    assert r.intencao is IntencaoClinica.VERIFICACAO_EXAMES


def test_entidades_invalidas_sao_descartadas() -> None:
    payload = {
        "intencao": "SUGESTAO_TRATAMENTO",
        "entidades": {
            "numero_prontuario": "  ",
            "condicao": 123,  # tipo errado
            "medicamentos_mencionados": ["", "  ", "Aspirina"],
        },
        "confianca": 0.9,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_llm([payload]))
    r = interp.interpretar_pergunta("teste")
    assert r.entidades == {"medicamentos_mencionados": ["Aspirina"]}


def test_texto_vazio_levanta() -> None:
    interp = InterpretadorNLU(_llm([{"intencao": "X"}]))
    with pytest.raises(ValueError):
        interp.interpretar_pergunta("")
    with pytest.raises(ValueError):
        interp.interpretar_pergunta("   ")


def test_falha_do_llm_cai_para_desconhecida() -> None:
    class LLMQuebrado:
        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    interp = InterpretadorNLU(LLMQuebrado())  # type: ignore[arg-type]
    r = interp.interpretar_pergunta("qualquer coisa")
    assert r.intencao is IntencaoClinica.INTENCAO_DESCONHECIDA
    assert r.requer_esclarecimento is True
