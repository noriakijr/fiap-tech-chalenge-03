"""Worker de atualização de status de exames (Fase 7, Task 7.1).

Executa ciclos periódicos (padrão 10s) consultando exames com status
"Em Análise" e atualizando para "Concluído" quando resultado disponível.

Garantia: atualização ocorre em no máximo 60s após disponibilização (Req 3.5,
Propriedade 14) — com intervalo de 10s, no máximo 6 ciclos (= 60s) bastam.

Uso em produção: criar a task no lifespan da aplicação via asyncio.create_task.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Exame as ExameORM

logger = logging.getLogger(__name__)

# (numero_prontuario, nome_exame) → True se resultado disponível
VerificadorResultado = Callable[[str, str], Awaitable[bool]]

_STATUS_EM_ANALISE = "Em Análise"
_STATUS_CONCLUIDO = "Concluído"


class AtualizadorExames:
    """Verifica resultados disponíveis e promove exames Em Análise → Concluído."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        verificar_resultado: VerificadorResultado,
        intervalo_seg: float = 10.0,
    ) -> None:
        if intervalo_seg <= 0:
            raise ValueError("intervalo_seg deve ser > 0.")
        self._factory = session_factory
        self._verificar = verificar_resultado
        self._intervalo = intervalo_seg

    async def executar_ciclo(self) -> int:
        """Executa um ciclo de verificação.

        Retorna o número de exames atualizados para Concluído neste ciclo.
        """
        async with self._factory() as session:
            stmt = select(ExameORM).where(ExameORM.status == _STATUS_EM_ANALISE)
            exames = (await session.execute(stmt)).scalars().all()

            atualizados = 0
            for exame in exames:
                try:
                    disponivel = await self._verificar(exame.numero_prontuario, exame.nome)
                except Exception:
                    logger.exception(
                        "erro_verificando_resultado_exame",
                        extra={"exame_id": exame.id, "nome": exame.nome},
                    )
                    continue

                if disponivel:
                    exame.status = _STATUS_CONCLUIDO
                    atualizados += 1
                    logger.info(
                        "exame_concluido",
                        extra={"exame_id": exame.id, "nome": exame.nome},
                    )

            if atualizados > 0:
                await session.commit()

        return atualizados

    async def iniciar(self) -> None:
        """Loop periódico até cancelamento externo (asyncio.CancelledError)."""
        logger.info("worker_exames_iniciado", extra={"intervalo_seg": self._intervalo})
        try:
            while True:
                try:
                    n = await self.executar_ciclo()
                    if n:
                        logger.info("worker_ciclo_concluiu", extra={"atualizados": n})
                except Exception:
                    logger.exception("worker_ciclo_falhou")
                await asyncio.sleep(self._intervalo)
        except asyncio.CancelledError:
            logger.info("worker_exames_encerrado")
            raise
