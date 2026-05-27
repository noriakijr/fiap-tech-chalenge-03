"""Resiliência para chamadas externas (Requisito 1.11, Error Handling).

- `with_timeout(seconds)` aplica `asyncio.wait_for` e converte `TimeoutError`
  em `PLNTimeoutError` (default para o serviço de PLN: 10s).
- `CircuitBreaker` implementa um circuito simples: após N falhas consecutivas,
  abre por D segundos e rejeita imediatamente novas chamadas com
  `KnowledgeBaseUnavailableError` (ou exceção customizada).

A função monotônica do relógio é injetável (`time_fn`) para testes determinísticos.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ParamSpec, TypeVar

from app.core.exceptions import BaseAppError, PLNTimeoutError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def with_timeout(
    seconds: float,
    exception: type[BaseAppError] = PLNTimeoutError,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorador async: cancela a coroutine se ultrapassar `seconds`."""

    if seconds <= 0:
        raise ValueError("seconds deve ser > 0.")

    def decorador(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError as exc:
                logger.warning(
                    "timeout_excedido",
                    extra={"limite_seg": seconds, "func": func.__qualname__},
                )
                raise exception(detalhes={"timeout_seg": seconds}) from exc

        return wrapper

    return decorador


class EstadoCircuito(str, Enum):
    FECHADO = "fechado"
    ABERTO = "aberto"
    SEMI_ABERTO = "semi_aberto"


class CircuitBreakerOpenError(BaseAppError):
    """Levantada quando o circuito está aberto e a chamada é rejeitada."""

    code = "circuit_open"
    http_status = 503
    default_message = (
        "Serviço temporariamente indisponível após falhas consecutivas. "
        "Tente novamente em instantes."
    )


@dataclass
class CircuitBreaker:
    """Circuit breaker simples — síncrono, thread-safe não é necessário aqui.

    - `falhas_para_abrir`: nº de falhas consecutivas que abrem o circuito.
    - `aberto_por_seg`: tempo que o circuito permanece aberto antes de tentar
      meio-aberto.
    - `time_fn`: relógio monotônico (injetável para testes).
    """

    falhas_para_abrir: int = 3
    aberto_por_seg: float = 30.0
    time_fn: Callable[[], float] = field(default=time.monotonic)

    _estado: EstadoCircuito = field(default=EstadoCircuito.FECHADO, init=False)
    _falhas_consecutivas: int = field(default=0, init=False)
    _aberto_ate: float = field(default=0.0, init=False)

    @property
    def estado(self) -> EstadoCircuito:
        self._atualizar_estado()
        return self._estado

    def _atualizar_estado(self) -> None:
        if self._estado is EstadoCircuito.ABERTO and self.time_fn() >= self._aberto_ate:
            self._estado = EstadoCircuito.SEMI_ABERTO

    def _registrar_sucesso(self) -> None:
        self._falhas_consecutivas = 0
        self._estado = EstadoCircuito.FECHADO

    def _registrar_falha(self) -> None:
        self._falhas_consecutivas += 1
        if self._falhas_consecutivas >= self.falhas_para_abrir:
            self._estado = EstadoCircuito.ABERTO
            self._aberto_ate = self.time_fn() + self.aberto_por_seg

    def _checar_abertura(self) -> None:
        self._atualizar_estado()
        if self._estado is EstadoCircuito.ABERTO:
            raise CircuitBreakerOpenError(
                detalhes={
                    "aberto_por_seg_restante": max(
                        0.0, self._aberto_ate - self.time_fn()
                    )
                }
            )

    def call(self, func: Callable[..., R], *args: Any, **kwargs: Any) -> R:
        self._checar_abertura()
        try:
            resultado = func(*args, **kwargs)
        except Exception:
            self._registrar_falha()
            raise
        else:
            self._registrar_sucesso()
            return resultado

    async def acall(
        self, func: Callable[..., Awaitable[R]], *args: Any, **kwargs: Any
    ) -> R:
        self._checar_abertura()
        try:
            resultado = await func(*args, **kwargs)
        except Exception:
            self._registrar_falha()
            raise
        else:
            self._registrar_sucesso()
            return resultado
