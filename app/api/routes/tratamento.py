"""Endpoint de sugestão de tratamento (Fase 6, Task 6.4).

POST /v1/pacientes/{numero_prontuario}/tratamento

Fluxo completo com validações de segurança (Req 4.1–4.9):
- 404 se paciente não existir.
- Bloqueio quando campos obrigatórios ausentes no prontuário (Req 4.9).
- Bloqueio quando serviço de interações indisponível (Req 4.7) → 503.
- Contraindicações e interações incluídas no texto de resposta.
- Separação Protocolos vs Artigos nas fontes (Req 4.2).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import OrchestradorDep, SessionStoreDep
from app.api.schemas import TratamentoRequest
from app.models.domain import IntencaoClinica, NLUResult, RespostaClinica

router = APIRouter()


@router.post(
    "/pacientes/{numero_prontuario}/tratamento",
    response_model=RespostaClinica,
    summary="Sugestão de tratamento",
    description=(
        "Gera sugestão de tratamento personalizado para o paciente, validando "
        "completude do prontuário, verificando interações medicamentosas e "
        "contraindicações. Protocolos e artigos são separados nas fontes."
    ),
)
async def sugestao_tratamento(
    numero_prontuario: str,
    body: TratamentoRequest,
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
        intencao=IntencaoClinica.SUGESTAO_TRATAMENTO,
        entidades={
            "numero_prontuario": numero_prontuario,
            "medicamentos_mencionados": body.medicamentos_sugeridos,
        },
        confianca=1.0,
    )
    return await orquestrador.handle_sugestao_tratamento("", nlu)
