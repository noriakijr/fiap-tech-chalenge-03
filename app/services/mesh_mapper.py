"""Mapeamento de termos clínicos para descritores MeSH (Fase 5, Task 5.3).

Cache local em memória por chave de termos normalizados (Req 1.5, Propriedade 13).
Quando o LLM não retorna lista válida, devolve [] com log de warning.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

_PROMPT_PADRAO = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "Você é especialista em Medical Subject Headings (MeSH). "
                "Converta os termos clínicos fornecidos para descritores MeSH "
                "padronizados em inglês. Retorne SOMENTE um array JSON de strings, "
                "sem texto adicional. "
                'Exemplo: ["Hypertension", "Diabetes Mellitus, Type 2"]\n'
                "Se nenhum termo for reconhecido, sugira ao menos uma especialidade médica."
            ),
        ),
        ("human", "Termos clínicos: {termos}"),
    ]
)

_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _extrair_texto(saida: Any) -> str:
    if isinstance(saida, BaseMessage):
        content = saida.content
        return content if isinstance(content, str) else str(content)
    return saida if isinstance(saida, str) else str(saida)


def _parse_lista(raw: str) -> list[str] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if str(t).strip()]
    except json.JSONDecodeError:
        match = _JSON_ARRAY_RE.search(raw)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return [str(t).strip() for t in parsed if str(t).strip()]
            except json.JSONDecodeError:
                pass
    return None


class MapadorMeSH:
    """Mapeia termos clínicos em português para descritores MeSH.

    Resultados são cacheados por conjunto de termos normalizados.
    """

    def __init__(
        self,
        llm: BaseLanguageModel,
        prompt: ChatPromptTemplate | None = None,
    ) -> None:
        self._llm = llm
        self._prompt = prompt or _PROMPT_PADRAO
        self._cache: dict[str, list[str]] = {}

    def mapear_para_mesh(self, termos_clinicos: list[str]) -> list[str]:
        """Retorna descritores MeSH. Resultado cacheado por conjunto de termos."""
        termos_limpos = [t.strip() for t in termos_clinicos if t and t.strip()]
        if not termos_limpos:
            return []

        chave = "|".join(sorted(t.lower() for t in termos_limpos))
        if chave in self._cache:
            return list(self._cache[chave])

        mensagens = self._prompt.format_messages(termos=", ".join(termos_limpos))
        try:
            saida = self._llm.invoke(mensagens)
        except Exception:
            logger.exception("falha_mapeamento_mesh")
            self._cache[chave] = []
            return []

        bruto = _extrair_texto(saida)
        resultado = _parse_lista(bruto) or []
        if not resultado:
            logger.warning("mesh_mapper_sem_resultado", extra={"termos": termos_limpos})

        self._cache[chave] = resultado
        return list(resultado)
