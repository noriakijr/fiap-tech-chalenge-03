"""Endpoint de verificação de exames (Fase 6, Task 6.3).

GET /v1/pacientes/{numero_prontuario}/exames-pendentes

Retorna exames com status Solicitado, Coletado ou Em Análise (Req 3.1–3.5).
- 404 se paciente não existir (PatientNotFoundError → handler global).
- Mensagem explícita quando não há exames pendentes (Req 3.4).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import OrchestradorDep
from app.models.domain import IntencaoClinica, NLUResult, RespostaClinica

router = APIRouter()


@router.get(
    "/pacientes/{numero_prontuario}/exames-pendentes",
    response_model=RespostaClinica,
    summary="Verificar exames pendentes",
    description=(
        "Lista os exames com status Solicitado, Coletado ou Em Análise "
        "do paciente informado. Retorna 404 se o prontuário não existir."
    ),
)
async def exames_pendentes(
    numero_prontuario: str,
    orquestrador: OrchestradorDep,
) -> RespostaClinica:
    nlu = NLUResult(
        intencao=IntencaoClinica.VERIFICACAO_EXAMES,
        entidades={"numero_prontuario": numero_prontuario},
        confianca=1.0,
    )
    return await orquestrador.handle_verificacao_exames(nlu)
