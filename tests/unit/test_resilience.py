from __future__ import annotations

import asyncio

import pytest

from app.core.exceptions import PLNTimeoutError
from app.core.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    EstadoCircuito,
    with_timeout,
)


# ---------- with_timeout ----------


@pytest.mark.asyncio
async def test_with_timeout_levanta_pln_timeout() -> None:
    @with_timeout(0.05)
    async def lenta() -> str:
        await asyncio.sleep(0.2)
        return "nunca chega"

    with pytest.raises(PLNTimeoutError):
        await lenta()


@pytest.mark.asyncio
async def test_with_timeout_retorna_dentro_do_prazo() -> None:
    @with_timeout(1.0)
    async def rapida() -> str:
        await asyncio.sleep(0.01)
        return "ok"

    assert await rapida() == "ok"


@pytest.mark.asyncio
async def test_with_timeout_preserva_metadata() -> None:
    @with_timeout(1.0)
    async def func_doc() -> int:
        """docstring importante"""
        return 1

    assert func_doc.__name__ == "func_doc"
    assert func_doc.__doc__ == "docstring importante"


def test_with_timeout_seconds_invalido_levanta() -> None:
    with pytest.raises(ValueError):
        with_timeout(0)
    with pytest.raises(ValueError):
        with_timeout(-1)


# ---------- CircuitBreaker (síncrono) ----------


class RelogioFake:
    def __init__(self, inicio: float = 0.0) -> None:
        self.agora = inicio

    def __call__(self) -> float:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


def _func_que_falha() -> int:
    raise RuntimeError("boom")


def _func_que_sucede() -> int:
    return 42


def test_circuito_inicia_fechado() -> None:
    cb = CircuitBreaker(falhas_para_abrir=3, aberto_por_seg=30.0)
    assert cb.estado is EstadoCircuito.FECHADO


def test_circuito_abre_apos_3_falhas() -> None:
    relogio = RelogioFake()
    cb = CircuitBreaker(falhas_para_abrir=3, aberto_por_seg=30.0, time_fn=relogio)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(_func_que_falha)

    assert cb.estado is EstadoCircuito.ABERTO


def test_chamada_rejeitada_quando_aberto() -> None:
    relogio = RelogioFake()
    cb = CircuitBreaker(falhas_para_abrir=2, aberto_por_seg=30.0, time_fn=relogio)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_func_que_falha)

    chamadas = {"n": 0}

    def func_que_seria_chamada():
        chamadas["n"] += 1
        return 1

    with pytest.raises(CircuitBreakerOpenError):
        cb.call(func_que_seria_chamada)
    assert chamadas["n"] == 0, "função interna não deve ser chamada quando aberto"


def test_circuito_volta_a_semi_aberto_apos_periodo() -> None:
    relogio = RelogioFake()
    cb = CircuitBreaker(falhas_para_abrir=1, aberto_por_seg=30.0, time_fn=relogio)

    with pytest.raises(RuntimeError):
        cb.call(_func_que_falha)
    assert cb.estado is EstadoCircuito.ABERTO

    relogio.avancar(31.0)
    assert cb.estado is EstadoCircuito.SEMI_ABERTO


def test_sucesso_em_semi_aberto_fecha_circuito() -> None:
    relogio = RelogioFake()
    cb = CircuitBreaker(falhas_para_abrir=1, aberto_por_seg=10.0, time_fn=relogio)

    with pytest.raises(RuntimeError):
        cb.call(_func_que_falha)
    relogio.avancar(11.0)

    assert cb.call(_func_que_sucede) == 42
    assert cb.estado is EstadoCircuito.FECHADO


def test_sucesso_zera_contador_de_falhas() -> None:
    relogio = RelogioFake()
    cb = CircuitBreaker(falhas_para_abrir=3, aberto_por_seg=30.0, time_fn=relogio)

    with pytest.raises(RuntimeError):
        cb.call(_func_que_falha)
    with pytest.raises(RuntimeError):
        cb.call(_func_que_falha)

    # Sucesso reseta — 2 falhas adicionais não devem abrir o circuito
    cb.call(_func_que_sucede)
    with pytest.raises(RuntimeError):
        cb.call(_func_que_falha)
    with pytest.raises(RuntimeError):
        cb.call(_func_que_falha)
    assert cb.estado is EstadoCircuito.FECHADO


# ---------- CircuitBreaker (async) ----------


@pytest.mark.asyncio
async def test_acall_abre_circuito_apos_falhas() -> None:
    relogio = RelogioFake()
    cb = CircuitBreaker(falhas_para_abrir=2, aberto_por_seg=30.0, time_fn=relogio)

    async def fail_async() -> None:
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.acall(fail_async)

    assert cb.estado is EstadoCircuito.ABERTO

    async def ok() -> int:
        return 1

    with pytest.raises(CircuitBreakerOpenError):
        await cb.acall(ok)


@pytest.mark.asyncio
async def test_acall_retorna_valor_quando_sucesso() -> None:
    cb = CircuitBreaker(falhas_para_abrir=3, aberto_por_seg=30.0)

    async def ok() -> str:
        return "valor"

    assert await cb.acall(ok) == "valor"
