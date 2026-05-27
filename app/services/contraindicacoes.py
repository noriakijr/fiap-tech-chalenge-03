"""Verificação de contraindicações (Requisito 4.8; Propriedade 6).

Para cada item do tratamento sugerido, cruza com:
- `prontuario.alergias`
- `prontuario.comorbidades`
- `prontuario.historico_clinico` (texto livre)
- `protocolo.contraindicacoes` dos protocolos aplicáveis

Retorna uma lista de strings descrevendo cada contraindicação identificada, em
pt-BR, prontas para serem exibidas ao médico.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from app.models.domain import Prontuario, Protocolo


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower().strip()


def _contem_palavra(haystack: str, agulha: str) -> bool:
    """Match com fronteiras de palavra, case/acento-insensitive."""

    h = _normalizar(haystack)
    a = _normalizar(agulha)
    if not h or not a:
        return False
    return re.search(rf"(?<!\w){re.escape(a)}(?!\w)", h) is not None


def _verificar_contra_lista(
    item: str,
    fonte: Iterable[str],
    rotulo: str,
) -> list[str]:
    alertas: list[str] = []
    for entrada in fonte:
        if not entrada or not entrada.strip():
            continue
        if _contem_palavra(entrada, item) or _contem_palavra(item, entrada):
            alertas.append(
                f"Contraindicação: '{item}' colide com {rotulo} '{entrada.strip()}'."
            )
    return alertas


def _verificar_contra_historico(item: str, historico: str | None) -> list[str]:
    if not historico:
        return []
    if _contem_palavra(historico, item):
        return [
            f"Contraindicação: '{item}' mencionado no histórico clínico do paciente."
        ]
    return []


def verificar_contraindicacoes(
    tratamento: list[str],
    prontuario: Prontuario,
    protocolos_aplicaveis: list[Protocolo] | None = None,
) -> list[str]:
    """Retorna lista de contraindicações identificadas (vazia se nenhuma)."""

    protocolos_aplicaveis = protocolos_aplicaveis or []
    alertas: list[str] = []

    for item in tratamento:
        if not item or not item.strip():
            continue
        item_clean = item.strip()

        alertas.extend(_verificar_contra_lista(item_clean, prontuario.alergias, "alergia"))
        alertas.extend(
            _verificar_contra_lista(item_clean, prontuario.comorbidades, "comorbidade")
        )
        alertas.extend(_verificar_contra_historico(item_clean, prontuario.historico_clinico))

        for protocolo in protocolos_aplicaveis:
            alertas.extend(
                _verificar_contra_lista(
                    item_clean,
                    protocolo.contraindicacoes,
                    f"contraindicação do protocolo {protocolo.id}",
                )
            )

    # Deduplica preservando ordem
    vistos: set[str] = set()
    resultado: list[str] = []
    for alerta in alertas:
        if alerta not in vistos:
            vistos.add(alerta)
            resultado.append(alerta)
    return resultado
