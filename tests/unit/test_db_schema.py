import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Exame, Medicamento, Paciente, Prontuario  # noqa: F401
from app.db.session import Base


@pytest.mark.asyncio
async def test_schema_cria_todas_as_tabelas() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        tabelas = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

    assert {"pacientes", "prontuarios", "exames", "medicamentos"}.issubset(set(tabelas))
    await engine.dispose()


@pytest.mark.asyncio
async def test_schema_tem_indice_em_exames_status() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        indices = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_indexes("exames")
        )

    nomes = {idx["name"] for idx in indices}
    assert "ix_exames_prontuario_status" in nomes
    await engine.dispose()
