"""Cria o schema do banco de dados e popula dados de exemplo.

Uso:
    python -m scripts.init_db          # cria schema e insere seed se vazio
    python -m scripts.init_db --reset  # apaga tudo e recria com seed
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import Exame, Medicamento, Paciente, Prontuario
from app.db.session import AsyncSessionLocal, Base, engine
from app.models.domain import StatusExame


def _seed_data() -> list[Paciente]:
    """Define 3 pacientes representativos para uso em desenvolvimento e testes."""

    paciente1 = Paciente(
        numero_prontuario="PRT-0001",
        nome="Maria Silva",
        data_nascimento=date(1968, 4, 12),
        prontuario=Prontuario(
            diagnostico_ativo="Pneumonia adquirida na comunidade",
            alergias=["Penicilina"],
            comorbidades=["Hipertensão", "Diabetes tipo 2"],
            historico_clinico="Internação prévia por pneumonia em 2023.",
        ),
        exames=[
            Exame(
                nome="Hemograma completo",
                data_solicitacao=date(2026, 5, 20),
                solicitante="Dr. Ana Costa",
                status=StatusExame.SOLICITADO.value,
            ),
            Exame(
                nome="Raio-X de tórax",
                data_solicitacao=date(2026, 5, 21),
                solicitante="Dr. Ana Costa",
                status=StatusExame.EM_ANALISE.value,
            ),
            Exame(
                nome="Hemocultura",
                data_solicitacao=date(2026, 5, 15),
                solicitante="Dr. Ana Costa",
                status=StatusExame.CONCLUIDO.value,
            ),
        ],
        medicamentos=[
            Medicamento(
                nome_medicamento="Losartana 50mg",
                data_inicio=date(2024, 1, 10),
                ativo=True,
            ),
            Medicamento(
                nome_medicamento="Metformina 850mg",
                data_inicio=date(2023, 6, 1),
                ativo=True,
            ),
        ],
    )

    paciente2 = Paciente(
        numero_prontuario="PRT-0002",
        nome="João Pereira",
        data_nascimento=date(1985, 9, 3),
        prontuario=Prontuario(
            diagnostico_ativo="Acompanhamento ambulatorial",
            alergias=[],
            comorbidades=[],
            historico_clinico=None,
        ),
        exames=[
            Exame(
                nome="Colesterol total",
                data_solicitacao=date(2026, 4, 10),
                solicitante="Dra. Beatriz Lima",
                status=StatusExame.CONCLUIDO.value,
            ),
            Exame(
                nome="Glicemia de jejum",
                data_solicitacao=date(2026, 4, 10),
                solicitante="Dra. Beatriz Lima",
                status=StatusExame.CANCELADO.value,
            ),
        ],
        medicamentos=[],
    )

    paciente3 = Paciente(
        numero_prontuario="PRT-0003",
        nome="Carlos Souza",
        data_nascimento=date(1992, 1, 27),
        prontuario=Prontuario(
            diagnostico_ativo=None,
            alergias=["Dipirona"],
            comorbidades=["Asma leve"],
            historico_clinico="Sem internações prévias.",
        ),
        exames=[
            Exame(
                nome="Espirometria",
                data_solicitacao=date(2026, 5, 22),
                solicitante="Dr. Felipe Rocha",
                status=StatusExame.COLETADO.value,
            ),
        ],
        medicamentos=[
            Medicamento(
                nome_medicamento="Salbutamol spray",
                data_inicio=date(2022, 3, 15),
                ativo=True,
            ),
            Medicamento(
                nome_medicamento="Prednisona 5mg",
                data_inicio=date(2024, 11, 1),
                ativo=False,
            ),
        ],
    )

    return [paciente1, paciente2, paciente3]


async def _ensure_data_dir(database_url: str) -> None:
    if database_url.startswith("sqlite") and ":memory:" not in database_url:
        prefix = "sqlite+aiosqlite:///"
        if database_url.startswith(prefix):
            path = Path(database_url[len(prefix):])
            path.parent.mkdir(parents=True, exist_ok=True)


async def _populate(reset: bool) -> tuple[int, int, int]:
    from app.core.config import get_settings

    await _ensure_data_dir(get_settings().database_url)

    async with engine.begin() as conn:
        if reset:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        existente = await session.scalar(select(func.count(Paciente.numero_prontuario)))
        if existente and not reset:
            exames = await session.scalar(select(func.count(Exame.id)))
            medicamentos = await session.scalar(select(func.count(Medicamento.id)))
            return existente, exames or 0, medicamentos or 0

        session.add_all(_seed_data())
        await session.commit()

        pacientes = await session.scalar(select(func.count(Paciente.numero_prontuario)))
        exames = await session.scalar(select(func.count(Exame.id)))
        medicamentos = await session.scalar(select(func.count(Medicamento.id)))
        return pacientes or 0, exames or 0, medicamentos or 0


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Apaga e recria todas as tabelas antes do seed.",
    )
    args = parser.parse_args()

    pacientes, exames, medicamentos = await _populate(reset=args.reset)
    await engine.dispose()
    print(
        f"Seed concluído: {pacientes} pacientes, {exames} exames, "
        f"{medicamentos} medicamentos."
    )


if __name__ == "__main__":
    asyncio.run(main())
