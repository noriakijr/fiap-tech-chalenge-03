"""Endpoint de consulta clínica (Fase 6, Task 6.1).

POST /v1/consulta — pergunta clínica em linguagem natural.

Passa pelo orquestrador completo (NLU → handler → avisos), incluindo o ciclo
de esclarecimento de até 3 perguntas (Req 1.8).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import OrchestradorDep, SessionStoreDep
from app.api.schemas import ConsultaRequest
from app.models.domain import RespostaClinica

router = APIRouter()


@router.post(
    "/consulta",
    response_model=RespostaClinica,
    summary="Consulta clínica",
    description=(
        "Recebe uma pergunta clínica em linguagem natural, classifica a intenção "
        "via NLU e retorna uma resposta baseada em evidências (RAG). Suporta ciclo "
        "de esclarecimento de até 3 perguntas quando a intenção for ambígua."
    ),
)
async def consulta(
    body: ConsultaRequest,
    orquestrador: OrchestradorDep,
    store: SessionStoreDep,
) -> RespostaClinica:
    sessao = store.get(body.sessao_id)
    if sessao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada. Crie uma sessão via POST /v1/sessao.",
        )
    return await orquestrador.processar_pergunta(body.texto, sessao)
