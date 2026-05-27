from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Exame as ExameORM
from app.db.models import Medicamento as MedicamentoORM
from app.db.models import Paciente as PacienteORM
from app.db.models import Prontuario as ProntuarioORM
from app.db.repositories.pacientes import RepositorioPacientes
from app.db.session import Base
from app.models.domain import StatusExame


@pytest_asyncio.fixture()
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        _seed(s)
        await s.commit()
        yield s

    await engine.dispose()


def _seed(session: AsyncSession) -> None:
    session.add_all(
        [
            PacienteORM(
                numero_prontuario="PRT-MIX",
                nome="Mix de Status",
                data_nascimento=date(1970, 1, 1),
                prontuario=ProntuarioORM(
                    diagnostico_ativo="Sepse",
                    alergias=["Sulfa"],
                    comorbidades=["DM2"],
                    historico_clinico="Histórico relevante.",
                ),
                exames=[
                    ExameORM(
                        nome="Exame Solicitado",
                        data_solicitacao=date(2026, 5, 1),
                        solicitante="Dr. A",
                        status=StatusExame.SOLICITADO.value,
                    ),
                    ExameORM(
                        nome="Exame Coletado",
                        data_solicitacao=date(2026, 5, 2),
                        solicitante="Dr. A",
                        status=StatusExame.COLETADO.value,
                    ),
                    ExameORM(
                        nome="Exame Em Analise",
                        data_solicitacao=date(2026, 5, 3),
                        solicitante="Dr. A",
                        status=StatusExame.EM_ANALISE.value,
                    ),
                    ExameORM(
                        nome="Exame Concluido",
                        data_solicitacao=date(2026, 4, 1),
                        solicitante="Dr. A",
                        status=StatusExame.CONCLUIDO.value,
                    ),
                    ExameORM(
                        nome="Exame Cancelado",
                        data_solicitacao=date(2026, 4, 2),
                        solicitante="Dr. A",
                        status=StatusExame.CANCELADO.value,
                    ),
                ],
                medicamentos=[
                    MedicamentoORM(nome_medicamento="Med Ativo 1", ativo=True),
                    MedicamentoORM(nome_medicamento="Med Ativo 2", ativo=True),
                    MedicamentoORM(nome_medicamento="Med Inativo", ativo=False),
                ],
            ),
            PacienteORM(
                numero_prontuario="PRT-SEM-PENDENTES",
                nome="Sem Pendentes",
                data_nascimento=date(1980, 5, 5),
                prontuario=ProntuarioORM(
                    alergias=[],
                    comorbidades=[],
                ),
                exames=[
                    ExameORM(
                        nome="Apenas Concluido",
                        data_solicitacao=date(2026, 3, 1),
                        solicitante="Dr. B",
                        status=StatusExame.CONCLUIDO.value,
                    ),
                ],
                medicamentos=[],
            ),
            PacienteORM(
                numero_prontuario="PRT-SEM-MEDS-ATIVOS",
                nome="So Inativos",
                data_nascimento=date(1990, 7, 7),
                prontuario=ProntuarioORM(alergias=[], comorbidades=[]),
                exames=[],
                medicamentos=[
                    MedicamentoORM(nome_medicamento="Antigo 1", ativo=False),
                    MedicamentoORM(nome_medicamento="Antigo 2", ativo=False),
                ],
            ),
        ]
    )


@pytest.mark.asyncio
async def test_buscar_prontuario_existente(session: AsyncSession) -> None:
    repo = RepositorioPacientes(session)
    prontuario = await repo.buscar_prontuario("PRT-MIX")

    assert prontuario is not None
    assert prontuario.numero == "PRT-MIX"
    assert prontuario.diagnostico_ativo == "Sepse"
    assert prontuario.alergias == ["Sulfa"]
    assert prontuario.comorbidades == ["DM2"]
    assert prontuario.historico_clinico == "Histórico relevante."
    assert sorted(prontuario.medicamentos_em_uso) == ["Med Ativo 1", "Med Ativo 2"]


@pytest.mark.asyncio
async def test_buscar_prontuario_inexistente_retorna_none(session: AsyncSession) -> None:
    repo = RepositorioPacientes(session)
    assert await repo.buscar_prontuario("PRT-NAO-EXISTE") is None


@pytest.mark.asyncio
async def test_listar_exames_pendentes_mix_de_status(session: AsyncSession) -> None:
    repo = RepositorioPacientes(session)
    pendentes = await repo.listar_exames_pendentes("PRT-MIX")

    assert len(pendentes) == 3
    nomes = {e.nome for e in pendentes}
    assert nomes == {"Exame Solicitado", "Exame Coletado", "Exame Em Analise"}

    for exame in pendentes:
        assert exame.status in {
            StatusExame.SOLICITADO,
            StatusExame.COLETADO,
            StatusExame.EM_ANALISE,
        }
        assert exame.nome
        assert exame.solicitante
        assert exame.data_solicitacao is not None


@pytest.mark.asyncio
async def test_listar_exames_pendentes_sem_pendentes_retorna_vazio(
    session: AsyncSession,
) -> None:
    repo = RepositorioPacientes(session)
    assert await repo.listar_exames_pendentes("PRT-SEM-PENDENTES") == []


@pytest.mark.asyncio
async def test_listar_exames_pendentes_paciente_inexistente_retorna_vazio(
    session: AsyncSession,
) -> None:
    repo = RepositorioPacientes(session)
    assert await repo.listar_exames_pendentes("PRT-FANTASMA") == []


@pytest.mark.asyncio
async def test_buscar_medicamentos_em_uso_somente_ativos(session: AsyncSession) -> None:
    repo = RepositorioPacientes(session)
    medicamentos = await repo.buscar_medicamentos_em_uso("PRT-MIX")
    assert medicamentos == ["Med Ativo 1", "Med Ativo 2"]


@pytest.mark.asyncio
async def test_buscar_medicamentos_em_uso_vazio_quando_nenhum_ativo(
    session: AsyncSession,
) -> None:
    repo = RepositorioPacientes(session)
    assert await repo.buscar_medicamentos_em_uso("PRT-SEM-MEDS-ATIVOS") == []
