"""Testes de contrato para POST /v1/conduta (Task 6.2)."""

from __future__ import annotations

from app.models.domain import (
    Aviso,
    DecisaoFinal,
    FonteReferencia,
    RespostaClinica,
    TipoAviso,
    TipoFonte,
)
from tests.integration.conftest import SESSAO_ID, make_mock_orq


def _fonte(id_: str, tipo: TipoFonte, ano: int | None = None) -> FonteReferencia:
    return FonteReferencia(
        tipo=tipo,
        identificador=id_,
        titulo=f"Fonte {id_}",
        ano=ano,
        decisao_final=DecisaoFinal.YES if tipo == TipoFonte.ARTIGO else None,
    )


def test_conduta_retorna_200(client) -> None:
    response = client.post(
        "/v1/conduta",
        json={"quadro_clinico": "sepse grave", "sessao_id": SESSAO_ID},
    )
    assert response.status_code == 200


def test_conduta_retorna_estrutura_resposta_clinica(client) -> None:
    response = client.post(
        "/v1/conduta",
        json={"quadro_clinico": "sepse", "sessao_id": SESSAO_ID},
    )
    body = response.json()
    assert "texto_resposta" in body
    assert "fontes" in body
    assert "avisos" in body
    assert "confianca" in body


def test_conduta_quadro_clinico_vazio_retorna_422(client) -> None:
    response = client.post(
        "/v1/conduta",
        json={"quadro_clinico": "", "sessao_id": SESSAO_ID},
    )
    assert response.status_code == 422


def test_conduta_sessao_inexistente_retorna_404(client) -> None:
    response = client.post(
        "/v1/conduta",
        json={"quadro_clinico": "sepse", "sessao_id": "invalida"},
    )
    assert response.status_code == 404


def test_conduta_chama_handle_sugestao_conduta(client, mock_orq) -> None:
    client.post(
        "/v1/conduta",
        json={"quadro_clinico": "choque séptico", "sessao_id": SESSAO_ID},
    )
    mock_orq.handle_sugestao_conduta.assert_called_once()


def test_conduta_protocolo_na_resposta(client, test_store, mock_orq) -> None:
    from app.main import create_app
    from app.api.deps import get_orchestrador, get_session_store

    resposta_com_protocolo = RespostaClinica(
        texto_resposta="Protocolo de sepse.",
        fontes=[
            _fonte("PROT-SEPSE-001", TipoFonte.PROTOCOLO),
            _fonte("PMID-001", TipoFonte.ARTIGO, ano=2023),
        ],
        avisos=[Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False)],
        confianca=0.9,
    )
    app = create_app()
    orq = make_mock_orq(handle_conduta=resposta_com_protocolo)
    app.dependency_overrides[get_orchestrador] = lambda: orq
    app.dependency_overrides[get_session_store] = lambda: test_store

    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as tc:
        response = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "sepse", "sessao_id": SESSAO_ID},
        )

    body = response.json()
    tipos_fontes = [f["tipo"] for f in body["fontes"]]
    assert "protocolo" in tipos_fontes
    assert "artigo" in tipos_fontes


def test_conduta_emergencia_na_resposta(client, test_store, mock_orq) -> None:
    from app.main import create_app
    from app.api.deps import get_orchestrador, get_session_store

    resposta_emergencia = RespostaClinica(
        texto_resposta="Emergência detectada.",
        fontes=[],
        avisos=[
            Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="apoio", destaque=False),
            Aviso(tipo=TipoAviso.EMERGENCIA, mensagem="EMERGÊNCIA!", destaque=True),
        ],
        confianca=0.9,
    )
    app = create_app()
    orq = make_mock_orq(handle_conduta=resposta_emergencia)
    app.dependency_overrides[get_orchestrador] = lambda: orq
    app.dependency_overrides[get_session_store] = lambda: test_store

    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as tc:
        response = tc.post(
            "/v1/conduta",
            json={"quadro_clinico": "parada cardiorrespiratória", "sessao_id": SESSAO_ID},
        )

    tipos_avisos = [a["tipo"] for a in response.json()["avisos"]]
    assert "emergencia" in tipos_avisos


def test_conduta_sem_rag_retorna_503(client_no_orq) -> None:
    response = client_no_orq.post(
        "/v1/conduta",
        json={"quadro_clinico": "teste", "sessao_id": SESSAO_ID},
    )
    assert response.status_code == 503
