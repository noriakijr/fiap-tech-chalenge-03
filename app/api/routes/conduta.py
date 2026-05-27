"""Endpoint de sugestão de conduta (Fase 6, Task 6.2).

POST /v1/conduta — descreve quadro clínico e recebe conduta ordenada.

Chama diretamente handle_sugestao_conduta (sem reclassificação NLU), garantindo:
- Protocolos ordenados, no máximo 5 (Req 2.6, Propriedade 5).
- Artigos por YEAR desc.
- Flag de emergência via aviso EMERGENCIA quando detectado (Req 2.5).
- Artigos com final_decision="no" excluídos (Req 4.3).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import OrchestradorDep, SessionStoreDep
from app.api.schemas import CondutaRequest
from app.models.domain import IntencaoClinica, NLUResult, RespostaClinica

router = APIRouter()


@router.post(
    "/conduta",
    response_model=RespostaClinica,
    summary="Sugestão de conduta",
    description=(
        "Recebe a descrição de um quadro clínico e retorna conduta ordenada: "
        "protocolos internos vigentes (até 5) seguidos de artigos PubMedQA "
        "por ano decrescente. Detecta emergências automaticamente."
    ),
)
async def sugestao_conduta(
    body: CondutaRequest,
    orquestrador: OrchestradorDep,
    store: SessionStoreDep,
) -> RespostaClinica:
    sessao = store.get(body.sessao_id)
    if sessao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada. Crie uma sessão via POST /v1/sessao.",
        )

    nlu = NLUResult(
        intencao=IntencaoClinica.SUGESTAO_CONDUTA,
        entidades={"condicao": body.quadro_clinico},
        confianca=1.0,
    )
    return orquestrador.handle_sugestao_conduta(body.quadro_clinico, nlu)
