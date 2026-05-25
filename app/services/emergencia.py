"""Detecção de emergência (Requisito 2.5; Propriedade 15).

Varre os `termos_emergencia` declarados em cada protocolo vigente e identifica
se algum aparece (substring case-insensitive) no quadro clínico descrito.
"""

from __future__ import annotations

import re
import unicodedata

from app.models.domain import Protocolo


def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas para comparação tolerante."""

    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


def _bordas_palavra(termo_normalizado: str) -> re.Pattern[str]:
    """Procura o termo como palavra/expressão isolada, não substring fortuita."""

    return re.compile(rf"(?<!\w){re.escape(termo_normalizado)}(?!\w)")


def detectar_emergencia(
    quadro_clinico: str, protocolos: list[Protocolo]
) -> Protocolo | None:
    """Retorna o primeiro protocolo vigente cujo termo de emergência aparece no
    quadro clínico. Retorna None se nenhum corresponder.
    """

    if not quadro_clinico:
        return None

    texto = _normalizar(quadro_clinico)

    for protocolo in protocolos:
        if not protocolo.vigente:
            continue
        for termo in protocolo.termos_emergencia:
            termo_norm = _normalizar(termo).strip()
            if not termo_norm:
                continue
            if _bordas_palavra(termo_norm).search(texto):
                return protocolo

    return None
