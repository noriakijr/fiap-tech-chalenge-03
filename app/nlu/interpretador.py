"""Interpretador NLU — classifica perguntas clínicas em intenções.

A LLM recebe a pergunta e devolve um JSON aderente ao schema do NLUResult.
A produção monta com `ChatOpenAI(temperature=0)`; testes injetam um FakeListLLM
com respostas pré-definidas em JSON.

Quando o JSON é inválido ou a confiança é baixa, o resultado cai para
`INTENCAO_DESCONHECIDA` com `requer_esclarecimento=True` (Requisito 1.8).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from app.models.domain import IntencaoClinica, NLUResult

logger = logging.getLogger(__name__)


_PROMPT_PADRAO = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "Você é um classificador de intenções clínicas para um assistente "
                "médico hospitalar. Toda interação é em português do Brasil.\n\n"
                "Intenções possíveis (use EXATAMENTE um destes rótulos):\n"
                "- CONSULTA_CLINICA: pergunta clínica geral sobre evidências, "
                "diagnóstico, doenças.\n"
                "- SUGESTAO_CONDUTA: o médico descreve um quadro clínico e quer "
                "conduta/manejo.\n"
                "- VERIFICACAO_EXAMES: o médico pede status de exames de um "
                "paciente identificado por número de prontuário.\n"
                "- SUGESTAO_TRATAMENTO: o médico pede tratamento personalizado "
                "para um paciente identificado.\n"
                "- INTENCAO_DESCONHECIDA: nada acima se aplica ou a mensagem é "
                "ambígua.\n\n"
                "Entidades possíveis (omita as ausentes):\n"
                "- numero_prontuario (string)\n"
                "- condicao (string em pt-BR)\n"
                "- medicamentos_mencionados (lista de strings)\n\n"
                "Responda SOMENTE com um objeto JSON neste formato (sem texto "
                "antes ou depois, sem cercas Markdown):\n"
                '{{"intencao": "<rótulo>", "entidades": {{...}}, '
                '"confianca": <0.0-1.0>, "idioma_detectado": "<código BCP-47>"}}'
            ),
        ),
        ("human", "{pergunta}"),
    ]
)


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extrair_texto(saida: Any) -> str:
    if isinstance(saida, BaseMessage):
        content = saida.content
        if isinstance(content, str):
            return content
        return str(content)
    if isinstance(saida, str):
        return saida
    return str(saida)


def _extrair_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    if not raw:
        return None
    # Remove cercas Markdown ```json ... ```
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_OBJ_RE.search(raw)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _normalizar_entidades(entidades: Any) -> dict[str, Any]:
    if not isinstance(entidades, dict):
        return {}
    saida: dict[str, Any] = {}
    if isinstance(entidades.get("numero_prontuario"), str):
        valor = entidades["numero_prontuario"].strip()
        if valor:
            saida["numero_prontuario"] = valor
    if isinstance(entidades.get("condicao"), str):
        valor = entidades["condicao"].strip()
        if valor:
            saida["condicao"] = valor
    meds = entidades.get("medicamentos_mencionados")
    if isinstance(meds, list):
        normalizados = [m.strip() for m in meds if isinstance(m, str) and m.strip()]
        if normalizados:
            saida["medicamentos_mencionados"] = normalizados
    return saida


def _fallback_desconhecida(idioma: str = "pt-BR") -> NLUResult:
    return NLUResult(
        intencao=IntencaoClinica.INTENCAO_DESCONHECIDA,
        entidades={},
        confianca=0.0,
        idioma_detectado=idioma,
        requer_esclarecimento=True,
    )


class InterpretadorNLU:
    """Classificador de intenção clínica baseado em LLM."""

    def __init__(
        self,
        llm: BaseLanguageModel,
        prompt: ChatPromptTemplate | None = None,
        confianca_minima: float = 0.5,
    ) -> None:
        self._llm = llm
        self._prompt = prompt or _PROMPT_PADRAO
        self._confianca_minima = confianca_minima

    def interpretar_pergunta(self, texto: str) -> NLUResult:
        if not texto or not texto.strip():
            raise ValueError("Texto da pergunta vazio.")

        mensagens = self._prompt.format_messages(pergunta=texto.strip())
        try:
            saida = self._llm.invoke(mensagens)
        except Exception:
            logger.exception("falha_invocando_llm_nlu")
            return _fallback_desconhecida()

        bruto = _extrair_texto(saida)
        payload = _extrair_json(bruto)
        if payload is None:
            logger.warning("nlu_json_invalido", extra={"saida_bruta": bruto[:200]})
            return _fallback_desconhecida()

        intencao_raw = str(payload.get("intencao") or "").strip().upper()
        try:
            intencao = IntencaoClinica(intencao_raw)
        except ValueError:
            return _fallback_desconhecida(
                idioma=str(payload.get("idioma_detectado") or "pt-BR")
            )

        confianca_raw = payload.get("confianca", 0.0)
        try:
            confianca = max(0.0, min(1.0, float(confianca_raw)))
        except (TypeError, ValueError):
            confianca = 0.0

        idioma = str(payload.get("idioma_detectado") or "pt-BR")
        entidades = _normalizar_entidades(payload.get("entidades"))

        if (
            intencao is not IntencaoClinica.INTENCAO_DESCONHECIDA
            and confianca < self._confianca_minima
        ):
            return _fallback_desconhecida(idioma=idioma)

        requer_esclarecimento = (
            intencao is IntencaoClinica.INTENCAO_DESCONHECIDA
        )

        return NLUResult(
            intencao=intencao,
            entidades=entidades,
            confianca=confianca,
            idioma_detectado=idioma,
            requer_esclarecimento=requer_esclarecimento,
        )
