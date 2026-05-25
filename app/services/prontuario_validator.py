"""Validação de completude do prontuário (Requisito 4.9, Propriedade 9).

Antes de sugerir tratamento, o orquestrador verifica se o prontuário contém os
três campos obrigatórios. Quando algum estiver ausente, a sugestão é bloqueada
e os campos faltantes são reportados ao médico.
"""

from __future__ import annotations

from app.models.domain import Prontuario


CAMPOS_OBRIGATORIOS: tuple[str, ...] = (
    "diagnostico_ativo",
    "medicamentos_em_uso",
    "alergias",
)


def _campo_ausente(prontuario: Prontuario, campo: str) -> bool:
    valor = getattr(prontuario, campo)
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    if isinstance(valor, (list, tuple, set)):
        return len(valor) == 0
    return False


def validar_campos_obrigatorios(prontuario: Prontuario) -> list[str]:
    """Retorna a lista de campos obrigatórios ausentes (`[]` se completo)."""

    return [campo for campo in CAMPOS_OBRIGATORIOS if _campo_ausente(prontuario, campo)]
