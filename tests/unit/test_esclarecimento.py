from __future__ import annotations

import json

import pytest
from langchain_community.llms.fake import FakeListLLM

from app.models.domain import IntencaoClinica, SessaoMedico
from app.nlu.esclarecimento import (
    MAX_ESCLARECIMENTOS,
    GeradorEsclarecimento,
    passo_esclarecimento,
)
from app.nlu.interpretador import InterpretadorNLU


def _nlu_llm(responses: list[dict]) -> FakeListLLM:
    return FakeListLLM(responses=[json.dumps(r) for r in responses])


def _gerador_llm(perguntas: list[str]) -> FakeListLLM:
    return FakeListLLM(responses=perguntas)


def _sessao() -> SessaoMedico:
    return SessaoMedico(id_sessao="s1", id_medico="m1")


def test_intencao_reconhecida_nao_pede_esclarecimento() -> None:
    interp = InterpretadorNLU(
        _nlu_llm(
            [{"intencao": "CONSULTA_CLINICA", "confianca": 0.9, "idioma_detectado": "pt-BR"}]
        )
    )
    gerador = GeradorEsclarecimento(_gerador_llm([]))
    sessao = _sessao()

    resultado = passo_esclarecimento(
        "Antibiótico em sepse?", sessao, interp, gerador
    )

    assert resultado.nlu.intencao is IntencaoClinica.CONSULTA_CLINICA
    assert resultado.pergunta_esclarecimento is None
    assert resultado.encerrado is False
    assert sessao.contador_esclarecimentos == 0


def test_intencao_desconhecida_emite_uma_pergunta() -> None:
    interp = InterpretadorNLU(
        _nlu_llm(
            [{"intencao": "INTENCAO_DESCONHECIDA", "confianca": 0.2, "idioma_detectado": "pt-BR"}]
        )
    )
    gerador = GeradorEsclarecimento(
        _gerador_llm(["Você quer consulta clínica ou verificação de exames?"])
    )
    sessao = _sessao()

    resultado = passo_esclarecimento("ahn?", sessao, interp, gerador)

    assert resultado.pergunta_esclarecimento == (
        "Você quer consulta clínica ou verificação de exames?"
    )
    assert resultado.encerrado is False
    assert sessao.contador_esclarecimentos == 1
    assert sessao.historico_perguntas == [resultado.pergunta_esclarecimento]
    assert resultado.precisa_continuar is True


def test_loop_de_3_ciclos_encerra_no_quarto() -> None:
    desconhecida = {
        "intencao": "INTENCAO_DESCONHECIDA",
        "confianca": 0.1,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_nlu_llm([desconhecida] * 4))
    gerador = GeradorEsclarecimento(
        _gerador_llm(["pergunta 1", "pergunta 2", "pergunta 3"])
    )
    sessao = _sessao()

    perguntas_emitidas: list[str] = []
    encerrado_em = None
    for i in range(1, 5):
        resultado = passo_esclarecimento("mensagem ambígua", sessao, interp, gerador)
        if resultado.precisa_continuar:
            perguntas_emitidas.append(resultado.pergunta_esclarecimento)
        if resultado.encerrado:
            encerrado_em = i
            break

    assert len(perguntas_emitidas) == MAX_ESCLARECIMENTOS == 3
    assert encerrado_em == 4
    assert sessao.contador_esclarecimentos == 3
    assert resultado.mensagem_fallback is not None
    assert "Reformule" in resultado.mensagem_fallback


def test_limite_nunca_excede_3() -> None:
    """Propriedade 11: nº de perguntas de esclarecimento <= 3."""

    desconhecida = {
        "intencao": "INTENCAO_DESCONHECIDA",
        "confianca": 0.1,
        "idioma_detectado": "pt-BR",
    }
    interp = InterpretadorNLU(_nlu_llm([desconhecida] * 10))
    gerador = GeradorEsclarecimento(_gerador_llm([f"q{i}" for i in range(10)]))
    sessao = _sessao()

    perguntas = 0
    for _ in range(10):
        resultado = passo_esclarecimento("ambígua", sessao, interp, gerador)
        if resultado.pergunta_esclarecimento is not None:
            perguntas += 1
        if resultado.encerrado:
            break

    assert perguntas <= MAX_ESCLARECIMENTOS


def test_reconhece_intencao_apos_esclarecimento() -> None:
    interp = InterpretadorNLU(
        _nlu_llm(
            [
                {"intencao": "INTENCAO_DESCONHECIDA", "confianca": 0.2, "idioma_detectado": "pt-BR"},
                {
                    "intencao": "VERIFICACAO_EXAMES",
                    "entidades": {"numero_prontuario": "PRT-0001"},
                    "confianca": 0.95,
                    "idioma_detectado": "pt-BR",
                },
            ]
        )
    )
    gerador = GeradorEsclarecimento(_gerador_llm(["Qual o número do prontuário?"]))
    sessao = _sessao()

    r1 = passo_esclarecimento("verifica aí", sessao, interp, gerador)
    assert r1.pergunta_esclarecimento == "Qual o número do prontuário?"
    assert sessao.contador_esclarecimentos == 1

    r2 = passo_esclarecimento("PRT-0001", sessao, interp, gerador)
    assert r2.nlu.intencao is IntencaoClinica.VERIFICACAO_EXAMES
    assert r2.pergunta_esclarecimento is None
    assert sessao.contador_esclarecimentos == 1


def test_gerador_lida_com_falha_do_llm() -> None:
    class LLMQuebrado:
        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("offline")

    gerador = GeradorEsclarecimento(LLMQuebrado())  # type: ignore[arg-type]
    pergunta = gerador.gerar_pergunta("texto", historico_esclarecimentos=[])
    assert "consulta" in pergunta.lower() or "exames" in pergunta.lower()


def test_gerador_lida_com_resposta_vazia() -> None:
    gerador = GeradorEsclarecimento(_gerador_llm(["   "]))
    pergunta = gerador.gerar_pergunta("texto", historico_esclarecimentos=[])
    assert pergunta.strip()
