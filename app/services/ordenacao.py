"""Ordenação de condutas clínicas (Requisitos 2.4, 2.6; Propriedade 5).

Regra:
- Protocolos vigentes vêm antes de qualquer artigo.
- Protocolos são ordenados pelo nº de condições aplicáveis que correspondem ao
  quadro clínico (desc); empate desfeito pelo identificador.
- Artigos vêm em seguida, ordenados por YEAR desc; empate desfeito pelo
  identificador.
- No máximo `max_protocolos` protocolos são exibidos.
"""

from __future__ import annotations

from app.models.domain import DocumentoRecuperado, TipoFonte


def _normalizar(termos: list[str]) -> set[str]:
    return {t.strip().lower() for t in termos if t and t.strip()}


def _cobertura(protocolo: DocumentoRecuperado, quadro: set[str]) -> int:
    """Quantas condições aplicáveis do protocolo aparecem no quadro clínico."""

    cond = _normalizar(protocolo.meshes)
    return sum(1 for termo in cond if termo in quadro)


def ordenar_condutas(
    protocolos: list[DocumentoRecuperado],
    artigos: list[DocumentoRecuperado],
    quadro_clinico: str = "",
    max_protocolos: int = 5,
) -> list[DocumentoRecuperado]:
    """Aplica a regra de ordenação. Não filtra por `vigente` — o caller já deve
    ter feito isso (quem ingere protocolos é a fonte da verdade).
    """

    if max_protocolos < 0:
        raise ValueError("max_protocolos deve ser >= 0.")

    for p in protocolos:
        if p.tipo != TipoFonte.PROTOCOLO:
            raise ValueError(
                f"Documento {p.identificador!r} em `protocolos` não é protocolo."
            )
    for a in artigos:
        if a.tipo != TipoFonte.ARTIGO:
            raise ValueError(
                f"Documento {a.identificador!r} em `artigos` não é artigo."
            )

    quadro = _normalizar(quadro_clinico.split())

    protocolos_ordenados = sorted(
        protocolos,
        key=lambda p: (-_cobertura(p, quadro), p.identificador),
    )[:max_protocolos]

    artigos_ordenados = sorted(
        artigos,
        key=lambda a: (-(a.ano or 0), a.identificador),
    )

    return protocolos_ordenados + artigos_ordenados
