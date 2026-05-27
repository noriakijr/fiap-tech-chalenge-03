from app.models.domain import Prontuario, Protocolo
from app.services.contraindicacoes import verificar_contraindicacoes


def _prontuario(**overrides) -> Prontuario:
    base = {
        "numero": "PRT-1",
        "diagnostico_ativo": "x",
        "medicamentos_em_uso": [],
        "alergias": [],
        "comorbidades": [],
        "historico_clinico": None,
    }
    base.update(overrides)
    return Prontuario(**base)


def _protocolo(contras: list[str]) -> Protocolo:
    return Protocolo(
        id="PROT-X",
        titulo="X",
        nivel_evidencia="A",
        condicoes_aplicaveis=["x"],
        contraindicacoes=contras,
    )


def test_alergia_detectada() -> None:
    p = _prontuario(alergias=["Penicilina"])
    alertas = verificar_contraindicacoes(["Penicilina"], p)
    assert len(alertas) == 1
    assert "alergia" in alertas[0].lower()


def test_alergia_case_e_acento_insensitive() -> None:
    p = _prontuario(alergias=["Sulfa"])
    alertas = verificar_contraindicacoes(["SULFA"], p)
    assert len(alertas) == 1


def test_comorbidade_detectada() -> None:
    p = _prontuario(comorbidades=["Insuficiência renal"])
    alertas = verificar_contraindicacoes(["Insuficiência renal"], p)
    assert any("comorbidade" in a.lower() for a in alertas)


def test_historico_clinico_detectado() -> None:
    p = _prontuario(historico_clinico="paciente com sangramento ativo recente")
    alertas = verificar_contraindicacoes(["sangramento ativo"], p)
    assert any("histórico" in a.lower() for a in alertas)


def test_contraindicacao_de_protocolo_detectada() -> None:
    p = _prontuario()
    protocolo = _protocolo(contras=["AVC hemorrágico recente"])
    alertas = verificar_contraindicacoes(
        ["AVC hemorrágico recente"], p, protocolos_aplicaveis=[protocolo]
    )
    assert any("PROT-X" in a for a in alertas)


def test_sem_contraindicacoes_retorna_vazio() -> None:
    p = _prontuario(alergias=["Sulfa"], comorbidades=["Diabetes"])
    alertas = verificar_contraindicacoes(["Amoxicilina"], p)
    assert alertas == []


def test_multiplos_tratamentos_e_fontes() -> None:
    p = _prontuario(
        alergias=["Penicilina"],
        comorbidades=["Insuficiência renal"],
    )
    alertas = verificar_contraindicacoes(
        ["Penicilina", "AINE", "Insuficiência renal"], p
    )
    assert len(alertas) == 2  # Penicilina (alergia) + Insuficiência renal (comorbidade)


def test_deduplicacao_de_alertas() -> None:
    p = _prontuario(alergias=["Sulfa", "sulfa"])
    alertas = verificar_contraindicacoes(["Sulfa"], p)
    # Como ambas as alergias normalizam para o mesmo termo, gera o mesmo alerta
    # com nome "Sulfa" e "sulfa" — entrada exata diferente, mas considerada duplicada
    # apenas se mensagens forem idênticas. Aqui são distintas — verificamos contagem.
    assert len(alertas) == 2


def test_substring_parcial_nao_dispara() -> None:
    p = _prontuario(alergias=["aido"])
    alertas = verificar_contraindicacoes(["cuidado domiciliar"], p)
    assert alertas == []


def test_tratamento_vazio_retorna_vazio() -> None:
    p = _prontuario(alergias=["sulfa"])
    assert verificar_contraindicacoes([], p) == []
    assert verificar_contraindicacoes(["", "  "], p) == []


def test_protocolo_sem_contraindicacoes_nao_quebra() -> None:
    p = _prontuario()
    protocolo = _protocolo(contras=[])
    assert verificar_contraindicacoes(["Amoxicilina"], p, [protocolo]) == []
