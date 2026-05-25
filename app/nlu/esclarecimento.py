"""Ciclo de esclarecimento de intenção (Requisito 1.8; Propriedade 11).

Quando o `InterpretadorNLU` retorna `INTENCAO_DESCONHECIDA`, o orquestrador
chama `GeradorEsclarecimento.gerar_pergunta(...)` para emitir uma pergunta
objetiva ao médico. O contador na `SessaoMedico` impede ultrapassar 3 ciclos.

A função utilitária `passo_esclarecimento` encapsula esse fluxo em um único
método, devolvendo um `ResultadoEsclarecimento` que o orquestrador consome.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from app.models.domain import IntencaoClinica, NLUResult, SessaoMedico
from app.nlu.interpretador import InterpretadorNLU

logger = logging.getLogger(__name__)


MAX_ESCLARECIMENTOS = 3

MENSAGEM_FALLBACK = (
    "Não consegui identificar uma intenção clínica clara após algumas tentativas. "
    "Reformule a pergunta indicando, por exemplo: condição clínica, número de "
    "prontuário do paciente ou o tipo de suporte desejado (consulta, conduta, "
    "exames, tratamento)."
)


_PROMPT_ESCLARECIMENTO = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "Você é um assistente médico hospitalar. O médico fez uma pergunta "
                "ambígua e você precisa elaborar UMA pergunta objetiva, curta e em "
                "português do Brasil para esclarecer a intenção. Não invente "
                "diagnóstico. Responda SOMENTE com a pergunta, sem comentários, "
                "sem listas, sem prefixos."
            ),
        ),
        (
            "human",
            (
                "Pergunta original do médico:\n{pergunta}\n\n"
                "Perguntas de esclarecimento já feitas nesta sessão "
                "(podem estar vazias):\n{historico}\n\n"
                "Gere a próxima pergunta de esclarecimento."
            ),
        ),
    ]
)


def _extrair_texto(saida: Any) -> str:
    if isinstance(saida, BaseMessage):
        content = saida.content
        if isinstance(content, str):
            return content
        return str(content)
    return str(saida)


@dataclass(frozen=True)
class ResultadoEsclarecimento:
    """Resultado de um único passo do ciclo de esclarecimento."""

    nlu: NLUResult
    pergunta_esclarecimento: str | None
    encerrado: bool
    mensagem_fallback: str | None = None

    @property
    def precisa_continuar(self) -> bool:
        """True se há uma pergunta para enviar ao médico."""

        return self.pergunta_esclarecimento is not None and not self.encerrado


class GeradorEsclarecimento:
    """Gera perguntas objetivas para desambiguar intenções."""

    def __init__(
        self,
        llm: BaseLanguageModel,
        prompt: ChatPromptTemplate | None = None,
    ) -> None:
        self._llm = llm
        self._prompt = prompt or _PROMPT_ESCLARECIMENTO

    def gerar_pergunta(
        self,
        pergunta_original: str,
        historico_esclarecimentos: list[str] | None = None,
    ) -> str:
        historico = historico_esclarecimentos or []
        historico_txt = "\n".join(f"- {p}" for p in historico) if historico else "(nenhuma)"

        mensagens = self._prompt.format_messages(
            pergunta=pergunta_original.strip(),
            historico=historico_txt,
        )
        try:
            saida = self._llm.invoke(mensagens)
        except Exception:
            logger.exception("falha_gerando_esclarecimento")
            return "Você quer uma consulta clínica, sugestão de conduta, verificação de exames ou sugestão de tratamento?"

        texto = _extrair_texto(saida).strip()
        if not texto:
            return "Pode reformular sua pergunta, por favor?"
        return texto


def passo_esclarecimento(
    pergunta: str,
    sessao: SessaoMedico,
    interpretador: InterpretadorNLU,
    gerador: GeradorEsclarecimento,
) -> ResultadoEsclarecimento:
    """Executa um único passo do ciclo de esclarecimento.

    - Interpreta a pergunta com o NLU.
    - Se a intenção foi reconhecida, devolve o NLUResult sem perguntar nada.
    - Se a intenção for desconhecida e o limite de 3 esclarecimentos ainda
      não foi atingido, gera uma pergunta de esclarecimento e incrementa
      `sessao.contador_esclarecimentos`. O histórico recebe a pergunta gerada.
    - Se o limite foi atingido, devolve `encerrado=True` com mensagem de fallback.
    """

    nlu = interpretador.interpretar_pergunta(pergunta)

    if nlu.intencao is not IntencaoClinica.INTENCAO_DESCONHECIDA:
        return ResultadoEsclarecimento(
            nlu=nlu, pergunta_esclarecimento=None, encerrado=False
        )

    if not sessao.pode_pedir_esclarecimento():
        return ResultadoEsclarecimento(
            nlu=nlu,
            pergunta_esclarecimento=None,
            encerrado=True,
            mensagem_fallback=MENSAGEM_FALLBACK,
        )

    pergunta_esc = gerador.gerar_pergunta(
        pergunta_original=pergunta,
        historico_esclarecimentos=sessao.historico_perguntas,
    )
    sessao.historico_perguntas.append(pergunta_esc)
    sessao.contador_esclarecimentos += 1

    return ResultadoEsclarecimento(
        nlu=nlu,
        pergunta_esclarecimento=pergunta_esc,
        encerrado=False,
    )
