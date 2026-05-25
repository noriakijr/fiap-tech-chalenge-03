from app.models.domain import Protocolo
from app.services.emergencia import detectar_emergencia


def _proto(
    id_: str,
    termos: list[str],
    vigente: bool = True,
) -> Protocolo:
    return Protocolo(
        id=id_,
        titulo=f"Protocolo {id_}",
        nivel_evidencia="A",
        condicoes_aplicaveis=["x"],
        termos_emergencia=termos,
        vigente=vigente,
    )


def test_detecta_termo_simples() -> None:
    p = _proto("P1", ["sepse grave"])
    assert detectar_emergencia("paciente com sepse grave", [p]) is p


def test_case_insensitive() -> None:
    p = _proto("P1", ["Choque Séptico"])
    assert detectar_emergencia("apresenta CHOQUE septico no atendimento", [p]) is p


def test_acento_insensitive() -> None:
    p = _proto("P1", ["arritmia maligna"])
    assert detectar_emergencia("Arritmia Maligna detectada", [p]) is p


def test_retorna_none_quando_nada_corresponde() -> None:
    p = _proto("P1", ["choque"])
    assert detectar_emergencia("paciente estável em observação", [p]) is None


def test_ignora_protocolos_nao_vigentes() -> None:
    vigente = _proto("P_velho", ["choque"], vigente=False)
    novo = _proto("P_novo", ["sepse"])
    assert detectar_emergencia("paciente com choque", [vigente, novo]) is None
    assert detectar_emergencia("paciente com sepse", [vigente, novo]) is novo


def test_retorna_primeiro_match() -> None:
    p1 = _proto("P1", ["choque"])
    p2 = _proto("P2", ["choque"])
    assert detectar_emergencia("choque hipovolemico", [p1, p2]) is p1


def test_substring_parcial_nao_dispara() -> None:
    p = _proto("P1", ["aido"])
    assert detectar_emergencia("paciente apresenta cuidado domiciliar", [p]) is None


def test_quadro_vazio_retorna_none() -> None:
    p = _proto("P1", ["choque"])
    assert detectar_emergencia("", [p]) is None
    assert detectar_emergencia("   ", [p]) is None


def test_lista_vazia_retorna_none() -> None:
    assert detectar_emergencia("choque", []) is None


def test_termo_emergencia_vazio_e_ignorado() -> None:
    p = _proto("P1", ["", "  ", "sepse"])
    assert detectar_emergencia("paciente com sepse", [p]) is p
