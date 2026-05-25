"""Endpoint de sessão (Fase 6, Task 6.5).

POST /v1/sessao — cria uma SessaoMedico nova e retorna seu ID.

O estado da sessão (contador de esclarecimentos, histórico, idioma) é mantido
em memória via ``get_session_store``. Ciclo de até 3 perguntas de esclarecimento
é gerido pelo OrquestradorClinico no endpoint /v1/consulta.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import SessionStoreDep
from app.api.schemas import CriarSessaoRequest, CriarSessaoResponse
from app.models.domain import SessaoMedico

router = APIRouter()


@router.post(
    "/sessao",
    response_model=CriarSessaoResponse,
    status_code=201,
    summary="Criar sessão",
    description="Cria uma nova SessaoMedico e retorna o sessao_id para uso nas demais chamadas.",
)
async def criar_sessao(
    body: CriarSessaoRequest,
    store: SessionStoreDep,
) -> CriarSessaoResponse:
    sessao_id = str(uuid.uuid4())
    sessao = SessaoMedico(id_sessao=sessao_id, id_medico=body.id_medico)
    store[sessao_id] = sessao
    return CriarSessaoResponse(sessao_id=sessao_id)
