"""Schemas Pydantic para request bodies da API (Fase 6)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CriarSessaoRequest(BaseModel):
    id_medico: str = Field(min_length=1, description="Identificador do médico.")


class CriarSessaoResponse(BaseModel):
    sessao_id: str = Field(description="UUID da sessão criada.")


class ConsultaRequest(BaseModel):
    texto: str = Field(min_length=1, description="Pergunta clínica em linguagem natural.")
    sessao_id: str = Field(min_length=1, description="UUID da sessão ativa.")


class CondutaRequest(BaseModel):
    quadro_clinico: str = Field(
        min_length=1,
        description="Descrição do quadro clínico para sugestão de conduta.",
    )
    sessao_id: str = Field(min_length=1, description="UUID da sessão ativa.")


class TratamentoRequest(BaseModel):
    sessao_id: str = Field(min_length=1, description="UUID da sessão ativa.")
    medicamentos_sugeridos: list[str] = Field(
        default_factory=list,
        description="Medicamentos a avaliar para interações (opcional).",
    )
