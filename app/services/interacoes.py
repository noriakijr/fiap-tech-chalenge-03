"""Serviço de interações medicamentosas (Requisitos 4.5–4.7, Propriedade 6).

A base de interações é um JSON local (`data/interacoes.json`) com pares de
medicamentos, severidade e descrição. A camada de carga é abstraída por um
callable para que falhas (arquivo ausente, JSON inválido) sejam testáveis.

Política de retry:
- Até 3 tentativas com backoff de 1s, 2s, 4s (configurável).
- Após exaurir, levanta `InteractionServiceUnavailableError` (Requisito 4.7).
"""

from __future__ import annotations

import json
import logging
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

from pydantic import ValidationError

from app.core.exceptions import InteractionServiceUnavailableError
from app.models.domain import InteracaoMedicamentosa

logger = logging.getLogger(__name__)


Carregador: TypeAlias = Callable[[], list[InteracaoMedicamentosa]]


def _normalizar(termo: str) -> str:
    nfkd = unicodedata.normalize("NFKD", termo)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower().strip()


def _contem(termo_alvo: str, candidato: str) -> bool:
    """True se `termo_alvo` (do banco) ocorre dentro de `candidato`."""

    a = _normalizar(termo_alvo)
    c = _normalizar(candidato)
    return bool(a and c and a in c)


def carregador_arquivo(path: str | Path) -> Carregador:
    """Cria um carregador que lê interações de um arquivo JSON."""

    caminho = Path(path)

    def _ler() -> list[InteracaoMedicamentosa]:
        if not caminho.exists():
            raise FileNotFoundError(
                f"Arquivo de interações não encontrado: {caminho}"
            )
        try:
            payload = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido em {caminho}: {exc}") from exc
        if not isinstance(payload, list):
            raise ValueError(
                f"Arquivo {caminho} deve conter uma lista de interações."
            )
        try:
            return [InteracaoMedicamentosa(**item) for item in payload]
        except ValidationError as exc:
            raise ValueError(f"Entrada inválida em {caminho}: {exc}") from exc

    return _ler


class ServicoInteracoes:
    """Orquestra a verificação de interações com retry e fallback."""

    def __init__(
        self,
        carregador: Carregador,
        max_tentativas: int = 3,
        backoff_seg: tuple[float, ...] = (1.0, 2.0, 4.0),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_tentativas < 1:
            raise ValueError("max_tentativas deve ser >= 1.")
        if len(backoff_seg) < max_tentativas - 1:
            raise ValueError(
                "backoff_seg deve ter pelo menos max_tentativas-1 elementos."
            )
        self._carregador = carregador
        self._max_tentativas = max_tentativas
        self._backoff = backoff_seg
        self._sleep = sleep_fn

    def _carregar_com_retry(self) -> list[InteracaoMedicamentosa]:
        ultima_erro: Exception | None = None
        for tentativa in range(1, self._max_tentativas + 1):
            try:
                return self._carregador()
            except Exception as exc:
                ultima_erro = exc
                logger.warning(
                    "interacoes_carga_falhou",
                    extra={
                        "tentativa": tentativa,
                        "max": self._max_tentativas,
                        "erro": str(exc),
                    },
                )
                if tentativa < self._max_tentativas:
                    self._sleep(self._backoff[tentativa - 1])
        raise InteractionServiceUnavailableError(
            detalhes={"causa_original": str(ultima_erro) if ultima_erro else "desconhecida"}
        )

    def verificar_interacoes(
        self,
        tratamento_sugerido: list[str],
        medicamentos_em_uso: list[str],
    ) -> list[InteracaoMedicamentosa]:
        """Retorna lista de interações entre tratamento e medicamentos em uso."""

        if not tratamento_sugerido or not medicamentos_em_uso:
            return []

        base = self._carregar_com_retry()

        encontradas: list[InteracaoMedicamentosa] = []
        vistos: set[tuple[str, str]] = set()

        for tratamento in tratamento_sugerido:
            if not tratamento or not tratamento.strip():
                continue
            for med_uso in medicamentos_em_uso:
                if not med_uso or not med_uso.strip():
                    continue
                for interacao in base:
                    a_match_t = _contem(interacao.medicamento_a, tratamento)
                    b_match_u = _contem(interacao.medicamento_b, med_uso)
                    a_match_u = _contem(interacao.medicamento_a, med_uso)
                    b_match_t = _contem(interacao.medicamento_b, tratamento)
                    if (a_match_t and b_match_u) or (a_match_u and b_match_t):
                        chave = (
                            _normalizar(interacao.medicamento_a),
                            _normalizar(interacao.medicamento_b),
                        )
                        chave_ord = tuple(sorted(chave))
                        if chave_ord not in vistos:
                            vistos.add(chave_ord)
                            encontradas.append(interacao)
        return encontradas


def servico_padrao() -> ServicoInteracoes:
    """Constrói o serviço com o caminho default do projeto."""

    raiz = Path(__file__).resolve().parents[2]
    return ServicoInteracoes(
        carregador=carregador_arquivo(raiz / "data" / "interacoes.json")
    )
