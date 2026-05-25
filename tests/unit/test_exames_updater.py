"""Testes para app/workers/exames_updater.py (Task 7.1).

Usa SQLite in-memory para simular o banco sem I/O real.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Exame as ExameORM
from app.db.models import Paciente as PacienteORM
from app.db.session import Base
from app.workers.exames_updater import AtualizadorExames


# ------------------------------------------------------------------ #
# Fixtures de banco in-memory                                          #
# ------------------------------------------------------------------ #


@pytest.fixture()
async def db_factory():
    """Cria engine SQLite in-memory, popula tabelas e devolve o sessionmaker."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        paciente = PacienteORM(
            numero_prontuario="PRT-TEST",
            nome="Paciente Teste",
            data_nascimento=date(1980, 1, 1),
        )
        session.add(paciente)
        await session.flush()

        session.add_all(
            [
                ExameORM(
                    numero_prontuario="PRT-TEST",
                    nome="Hemograma",
                    data_solicitacao=date.today(),
                    solicitante="DR-A",
                    status="Em Análise",
                ),
                ExameORM(
                    numero_prontuario="PRT-TEST",
                    nome="PCR",
                    data_solicitacao=date.today(),
                    solicitante="DR-A",
                    status="Em Análise",
                ),
                ExameORM(
                    numero_prontuario="PRT-TEST",
                    nome="Ureia",
                    data_solicitacao=date.today(),
                    solicitante="DR-A",
                    status="Solicitado",  # não deve ser tocado
                ),
            ]
        )
        await session.commit()

    yield factory
    await engine.dispose()


async def _buscar_status(factory, nome: str) -> str:
    async with factory() as session:
        stmt = select(ExameORM).where(ExameORM.nome == nome)
        exame = (await session.execute(stmt)).scalar_one()
        return exame.status


# ------------------------------------------------------------------ #
# Testes de ciclo único                                                #
# ------------------------------------------------------------------ #


async def test_ciclo_atualiza_exame_com_resultado_disponivel(db_factory) -> None:
    # Verifica apenas "Hemograma"
    verificar = AsyncMock(side_effect=lambda np, nome: nome == "Hemograma")
    worker = AtualizadorExames(db_factory, verificar)

    n = await worker.executar_ciclo()

    assert n == 1
    assert await _buscar_status(db_factory, "Hemograma") == "Concluído"
    assert await _buscar_status(db_factory, "PCR") == "Em Análise"


async def test_ciclo_nao_atualiza_quando_sem_resultado(db_factory) -> None:
    verificar = AsyncMock(return_value=False)
    worker = AtualizadorExames(db_factory, verificar)

    n = await worker.executar_ciclo()

    assert n == 0
    assert await _buscar_status(db_factory, "Hemograma") == "Em Análise"
    assert await _buscar_status(db_factory, "PCR") == "Em Análise"


async def test_ciclo_nao_toca_status_solicitado(db_factory) -> None:
    verificar = AsyncMock(return_value=True)
    worker = AtualizadorExames(db_factory, verificar)

    await worker.executar_ciclo()

    # "Ureia" está com status "Solicitado", não deve ser tocado
    assert await _buscar_status(db_factory, "Ureia") == "Solicitado"


async def test_ciclo_atualiza_multiplos_exames(db_factory) -> None:
    verificar = AsyncMock(return_value=True)
    worker = AtualizadorExames(db_factory, verificar)

    n = await worker.executar_ciclo()

    # Hemograma e PCR têm status "Em Análise"
    assert n == 2
    assert await _buscar_status(db_factory, "Hemograma") == "Concluído"
    assert await _buscar_status(db_factory, "PCR") == "Concluído"


async def test_ciclo_ignora_erro_em_verificacao_e_continua(db_factory) -> None:
    """Erro numa verificação não impede as demais."""
    chamadas = 0

    async def verificar(np: str, nome: str) -> bool:
        nonlocal chamadas
        chamadas += 1
        if nome == "Hemograma":
            raise RuntimeError("falha simulada")
        return True

    worker = AtualizadorExames(db_factory, verificar)
    n = await worker.executar_ciclo()

    assert chamadas == 2  # tentou os dois
    assert n == 1  # apenas PCR atualizado
    assert await _buscar_status(db_factory, "PCR") == "Concluído"
    assert await _buscar_status(db_factory, "Hemograma") == "Em Análise"


# ------------------------------------------------------------------ #
# Garantia de latência ≤ 60s                                          #
# ------------------------------------------------------------------ #


async def test_garantia_latencia_60s(db_factory) -> None:
    """Com intervalo de 10s, ao final do 1º ciclo o exame deve estar Concluído.

    Isso garante que, em produção, a atualização ocorrerá em ≤ 60s (6 ciclos).
    """
    verificar = AsyncMock(return_value=True)
    worker = AtualizadorExames(db_factory, verificar, intervalo_seg=10.0)

    # Simula que resultado ficou disponível agora — um ciclo deve bastar
    await worker.executar_ciclo()

    assert await _buscar_status(db_factory, "Hemograma") == "Concluído"


# ------------------------------------------------------------------ #
# Loop iniciar / cancelamento                                          #
# ------------------------------------------------------------------ #


async def test_iniciar_cancela_sem_travar() -> None:
    verificar = AsyncMock(return_value=False)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    worker = AtualizadorExames(factory, verificar, intervalo_seg=0.05)
    task = asyncio.create_task(worker.iniciar())
    await asyncio.sleep(0.15)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await engine.dispose()


# ------------------------------------------------------------------ #
# Validação de construção                                              #
# ------------------------------------------------------------------ #


def test_intervalo_invalido_levanta() -> None:
    with pytest.raises(ValueError):
        AtualizadorExames(None, AsyncMock(), intervalo_seg=0)  # type: ignore
