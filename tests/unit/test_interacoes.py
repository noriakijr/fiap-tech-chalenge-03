from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.exceptions import InteractionServiceUnavailableError
from app.models.domain import InteracaoMedicamentosa, SeveridadeInteracao
from app.services.interacoes import (
    ServicoInteracoes,
    carregador_arquivo,
    servico_padrao,
)


def _carregador(interacoes: list[dict]):
    def _ler() -> list[InteracaoMedicamentosa]:
        return [InteracaoMedicamentosa(**i) for i in interacoes]

    return _ler


def _base_minima() -> list[dict]:
    return [
        {
            "medicamento_a": "Varfarina",
            "medicamento_b": "AAS",
            "severidade": "grave",
            "descricao": "Risco de sangramento grave.",
        },
        {
            "medicamento_a": "Sinvastatina",
            "medicamento_b": "Claritromicina",
            "severidade": "grave",
            "descricao": "Risco de rabdomiólise.",
        },
    ]


def test_detecta_interacao_direta() -> None:
    servico = ServicoInteracoes(_carregador(_base_minima()))
    r = servico.verificar_interacoes(
        tratamento_sugerido=["AAS 100mg"],
        medicamentos_em_uso=["Varfarina 5mg"],
    )
    assert len(r) == 1
    assert r[0].severidade is SeveridadeInteracao.GRAVE


def test_detecta_interacao_invertida_a_b() -> None:
    servico = ServicoInteracoes(_carregador(_base_minima()))
    r = servico.verificar_interacoes(
        tratamento_sugerido=["Varfarina"],
        medicamentos_em_uso=["AAS"],
    )
    assert len(r) == 1


def test_sem_interacao_retorna_vazio() -> None:
    servico = ServicoInteracoes(_carregador(_base_minima()))
    r = servico.verificar_interacoes(
        tratamento_sugerido=["Paracetamol"],
        medicamentos_em_uso=["Omeprazol"],
    )
    assert r == []


def test_tratamento_ou_medicamentos_vazios_retorna_vazio() -> None:
    servico = ServicoInteracoes(_carregador(_base_minima()))
    assert servico.verificar_interacoes([], ["Varfarina"]) == []
    assert servico.verificar_interacoes(["AAS"], []) == []
    assert servico.verificar_interacoes([], []) == []


def test_match_case_e_acento_insensitive() -> None:
    base = [
        {
            "medicamento_a": "Captopril",
            "medicamento_b": "Espironolactona",
            "severidade": "moderada",
            "descricao": "Hipercalemia.",
        }
    ]
    servico = ServicoInteracoes(_carregador(base))
    r = servico.verificar_interacoes(
        tratamento_sugerido=["CAPTOPRIL 25mg"],
        medicamentos_em_uso=["espironolactona 50mg"],
    )
    assert len(r) == 1


def test_deduplica_pares_iguais() -> None:
    servico = ServicoInteracoes(_carregador(_base_minima()))
    r = servico.verificar_interacoes(
        tratamento_sugerido=["AAS", "AAS 300mg"],
        medicamentos_em_uso=["Varfarina"],
    )
    assert len(r) == 1


def test_retry_e_falha_apos_max_tentativas() -> None:
    chamadas = {"n": 0}
    sleeps: list[float] = []

    def carregador_falha():
        chamadas["n"] += 1
        raise FileNotFoundError("não achei")

    servico = ServicoInteracoes(
        carregador=carregador_falha,
        max_tentativas=3,
        backoff_seg=(0.01, 0.02, 0.04),
        sleep_fn=sleeps.append,
    )

    with pytest.raises(InteractionServiceUnavailableError):
        servico.verificar_interacoes(["AAS"], ["Varfarina"])

    assert chamadas["n"] == 3
    # Entre tentativas: 2 sleeps com backoff = (0.01, 0.02)
    assert sleeps == [0.01, 0.02]


def test_recupera_apos_falhas_intermitentes() -> None:
    chamadas = {"n": 0}

    def carregador_intermitente():
        chamadas["n"] += 1
        if chamadas["n"] < 2:
            raise IOError("transitório")
        return [
            InteracaoMedicamentosa(
                medicamento_a="A",
                medicamento_b="B",
                severidade="leve",
                descricao="x",
            )
        ]

    servico = ServicoInteracoes(
        carregador=carregador_intermitente,
        max_tentativas=3,
        backoff_seg=(0.0, 0.0, 0.0),
        sleep_fn=lambda _s: None,
    )

    r = servico.verificar_interacoes(["A 10mg"], ["B 20mg"])
    assert len(r) == 1
    assert chamadas["n"] == 2


def test_max_tentativas_invalido_levanta() -> None:
    with pytest.raises(ValueError):
        ServicoInteracoes(_carregador([]), max_tentativas=0)


def test_carregador_arquivo_le_json_real(tmp_path: Path) -> None:
    arquivo = tmp_path / "i.json"
    arquivo.write_text(
        json.dumps(
            [
                {
                    "medicamento_a": "X",
                    "medicamento_b": "Y",
                    "severidade": "leve",
                    "descricao": "ok",
                }
            ]
        ),
        encoding="utf-8",
    )
    interacoes = carregador_arquivo(arquivo)()
    assert len(interacoes) == 1


def test_carregador_arquivo_inexistente_levanta(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        carregador_arquivo(tmp_path / "nope.json")()


def test_carregador_arquivo_json_invalido_levanta(tmp_path: Path) -> None:
    arquivo = tmp_path / "i.json"
    arquivo.write_text("{{{", encoding="utf-8")
    with pytest.raises(ValueError):
        carregador_arquivo(arquivo)()


def test_servico_padrao_le_dataset_real() -> None:
    servico = servico_padrao()
    r = servico.verificar_interacoes(
        tratamento_sugerido=["Varfarina 5mg"],
        medicamentos_em_uso=["AAS 100mg"],
    )
    assert len(r) == 1
    assert r[0].severidade is SeveridadeInteracao.GRAVE
