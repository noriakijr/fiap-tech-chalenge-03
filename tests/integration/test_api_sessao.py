"""Testes de contrato para POST /v1/sessao (Task 6.5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_session_store
from app.main import create_app
from app.models.domain import SessaoMedico


@pytest.fixture()
def client_sessao() -> TestClient:
    """TestClient sem orquestrador (sessão não precisa dele)."""
    app = create_app()
    store: dict[str, SessaoMedico] = {}
    app.dependency_overrides[get_session_store] = lambda: store
    # Retorna (client, store) para inspecionar o estado
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc, store


def test_criar_sessao_retorna_201(client_sessao) -> None:
    client, _ = client_sessao
    response = client.post("/v1/sessao", json={"id_medico": "DR-001"})
    assert response.status_code == 201


def test_criar_sessao_retorna_sessao_id(client_sessao) -> None:
    client, _ = client_sessao
    response = client.post("/v1/sessao", json={"id_medico": "DR-001"})
    body = response.json()
    assert "sessao_id" in body
    assert len(body["sessao_id"]) > 0


def test_criar_sessao_persiste_no_store(client_sessao) -> None:
    client, store = client_sessao
    response = client.post("/v1/sessao", json={"id_medico": "DR-002"})
    sessao_id = response.json()["sessao_id"]
    assert sessao_id in store
    assert store[sessao_id].id_medico == "DR-002"


def test_criar_sessao_ids_unicos(client_sessao) -> None:
    client, _ = client_sessao
    r1 = client.post("/v1/sessao", json={"id_medico": "DR-001"})
    r2 = client.post("/v1/sessao", json={"id_medico": "DR-001"})
    assert r1.json()["sessao_id"] != r2.json()["sessao_id"]


def test_criar_sessao_sem_id_medico_retorna_422(client_sessao) -> None:
    client, _ = client_sessao
    response = client.post("/v1/sessao", json={})
    assert response.status_code == 422


def test_criar_sessao_id_medico_vazio_retorna_422(client_sessao) -> None:
    client, _ = client_sessao
    response = client.post("/v1/sessao", json={"id_medico": ""})
    assert response.status_code == 422


def test_criar_sessao_contador_zerado(client_sessao) -> None:
    client, store = client_sessao
    response = client.post("/v1/sessao", json={"id_medico": "DR-003"})
    sessao_id = response.json()["sessao_id"]
    assert store[sessao_id].contador_esclarecimentos == 0


def test_criar_sessao_idioma_pt_br(client_sessao) -> None:
    client, store = client_sessao
    response = client.post("/v1/sessao", json={"id_medico": "DR-004"})
    sessao_id = response.json()["sessao_id"]
    assert store[sessao_id].idioma == "pt-BR"
