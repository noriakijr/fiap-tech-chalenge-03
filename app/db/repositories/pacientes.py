from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exame as ExameORM
from app.db.models import Medicamento as MedicamentoORM
from app.db.models import Paciente as PacienteORM
from app.models.domain import (
    STATUS_EXAME_PENDENTE,
    Exame,
    Prontuario,
    StatusExame,
)

_STATUS_PENDENTES_VALORES: list[str] = [s.value for s in STATUS_EXAME_PENDENTE]


class RepositorioPacientes:
    """Acesso aos dados de pacientes no banco interno.

    Falhas de conexão propagam SQLAlchemyError; o orquestrador (Fase 5) converte
    para DatabaseUnavailableError (cf. app.core.exceptions).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_prontuario(self, numero_prontuario: str) -> Prontuario | None:
        """Retorna o Prontuario do paciente ou None se não cadastrado."""

        stmt = select(PacienteORM).where(
            PacienteORM.numero_prontuario == numero_prontuario
        )
        paciente = (await self._session.execute(stmt)).scalar_one_or_none()
        if paciente is None or paciente.prontuario is None:
            return None

        medicamentos_em_uso = [
            m.nome_medicamento for m in paciente.medicamentos if m.ativo
        ]

        return Prontuario(
            numero=paciente.numero_prontuario,
            diagnostico_ativo=paciente.prontuario.diagnostico_ativo,
            medicamentos_em_uso=medicamentos_em_uso,
            alergias=list(paciente.prontuario.alergias or []),
            comorbidades=list(paciente.prontuario.comorbidades or []),
            historico_clinico=paciente.prontuario.historico_clinico,
        )

    async def listar_exames_pendentes(self, numero_prontuario: str) -> list[Exame]:
        """Exames com status Solicitado, Coletado ou Em Análise (Propriedade 7)."""

        stmt = (
            select(ExameORM)
            .where(ExameORM.numero_prontuario == numero_prontuario)
            .where(ExameORM.status.in_(_STATUS_PENDENTES_VALORES))
            .order_by(ExameORM.data_solicitacao.asc(), ExameORM.id.asc())
        )
        resultado = (await self._session.execute(stmt)).scalars().all()

        return [
            Exame(
                nome=row.nome,
                data_solicitacao=row.data_solicitacao,
                solicitante=row.solicitante,
                status=StatusExame(row.status),
            )
            for row in resultado
        ]

    async def buscar_medicamentos_em_uso(self, numero_prontuario: str) -> list[str]:
        """Retorna apenas os nomes dos medicamentos com `ativo == True`."""

        stmt = (
            select(MedicamentoORM.nome_medicamento)
            .where(MedicamentoORM.numero_prontuario == numero_prontuario)
            .where(MedicamentoORM.ativo.is_(True))
            .order_by(MedicamentoORM.id.asc())
        )
        resultado = await self._session.execute(stmt)
        return list(resultado.scalars().all())
