from datetime import date

import pytest
from pydantic import ValidationError

from app.models.domain import (
    Aviso,
    DecisaoFinal,
    EntradaPubMedQA,
    Exame,
    FonteReferencia,
    InteracaoMedicamentosa,
    Medicamento,
    Prontuario,
    Protocolo,
    RespostaClinica,
    SessaoMedico,
    SeveridadeInteracao,
    StatusExame,
    TipoAviso,
    TipoFonte,
)


def _entrada_valida(**overrides) -> dict:
    base = {
        "id": "PMID-1",
        "QUESTION": "Pneumonia em adultos requer antibiótico?",
        "CONTEXTS": ["trecho A"],
        "LABELS": ["RESULTS"],
        "MESHES": ["Pneumonia"],
        "YEAR": 2020,
        "reasoning_required_pred": "yes",
        "final_decision": "maybe",
        "LONG_ANSWER": "Depende do quadro.",
    }
    base.update(overrides)
    return base


def test_entrada_pubmedqa_aceita_dados_validos() -> None:
    entrada = EntradaPubMedQA(**_entrada_valida())
    assert entrada.final_decision == DecisaoFinal.MAYBE
    assert entrada.YEAR == 2020


def test_entrada_pubmedqa_rejeita_decision_invalida() -> None:
    with pytest.raises(ValidationError):
        EntradaPubMedQA(**_entrada_valida(final_decision="talvez"))


def test_entrada_pubmedqa_rejeita_reasoning_invalido() -> None:
    with pytest.raises(ValidationError):
        EntradaPubMedQA(**_entrada_valida(reasoning_required_pred="probably"))


def test_entrada_pubmedqa_rejeita_year_fora_de_faixa() -> None:
    with pytest.raises(ValidationError):
        EntradaPubMedQA(**_entrada_valida(YEAR=1800))


def test_entrada_pubmedqa_labels_devem_alinhar_com_contexts() -> None:
    with pytest.raises(ValidationError):
        EntradaPubMedQA(
            **_entrada_valida(CONTEXTS=["a", "b"], LABELS=["RESULTS"])
        )


def test_protocolo_padrao_e_vigente() -> None:
    protocolo = Protocolo(
        id="PROT-001",
        titulo="Manejo de Sepse",
        nivel_evidencia="A",
        condicoes_aplicaveis=["sepse"],
        contraindicacoes=["alergia a betalactâmicos"],
        termos_emergencia=["choque séptico"],
    )
    assert protocolo.vigente is True


def test_exame_pendente_so_inclui_status_pendentes() -> None:
    base = {
        "nome": "Hemograma",
        "data_solicitacao": date(2026, 5, 1),
        "solicitante": "Dr. X",
    }
    assert Exame(**base, status=StatusExame.SOLICITADO).pendente()
    assert Exame(**base, status=StatusExame.COLETADO).pendente()
    assert Exame(**base, status=StatusExame.EM_ANALISE).pendente()
    assert not Exame(**base, status=StatusExame.CONCLUIDO).pendente()
    assert not Exame(**base, status=StatusExame.CANCELADO).pendente()


def test_exame_status_invalido_rejeitado() -> None:
    with pytest.raises(ValidationError):
        Exame(
            nome="Hemograma",
            data_solicitacao=date(2026, 5, 1),
            solicitante="Dr. X",
            status="Pendente",  # type: ignore[arg-type]
        )


def test_prontuario_defaults_listas_vazias() -> None:
    prontuario = Prontuario(numero="12345")
    assert prontuario.medicamentos_em_uso == []
    assert prontuario.alergias == []
    assert prontuario.comorbidades == []
    assert prontuario.diagnostico_ativo is None


def test_fonte_protocolo_nao_pode_ter_decisao_final() -> None:
    with pytest.raises(ValidationError):
        FonteReferencia(
            tipo=TipoFonte.PROTOCOLO,
            identificador="PROT-001",
            titulo="Manejo de Sepse",
            decisao_final=DecisaoFinal.YES,
        )


def test_fonte_artigo_pode_ter_decisao_final_e_ano() -> None:
    fonte = FonteReferencia(
        tipo=TipoFonte.ARTIGO,
        identificador="PMID-1",
        titulo="Pneumonia em adultos",
        ano=2021,
        decisao_final=DecisaoFinal.YES,
    )
    assert fonte.decisao_final == DecisaoFinal.YES
    assert fonte.ano == 2021


def test_aviso_tipo_invalido_rejeitado() -> None:
    with pytest.raises(ValidationError):
        Aviso(tipo="urgente", mensagem="x")  # type: ignore[arg-type]


def test_resposta_clinica_confianca_fora_de_faixa() -> None:
    with pytest.raises(ValidationError):
        RespostaClinica(texto_resposta="ok", confianca=1.2)


def test_resposta_clinica_aceita_avisos_e_fontes() -> None:
    resposta = RespostaClinica(
        texto_resposta="texto",
        confianca=0.9,
        fontes=[
            FonteReferencia(
                tipo=TipoFonte.PROTOCOLO,
                identificador="PROT-001",
                titulo="Manejo de Sepse",
            )
        ],
        avisos=[Aviso(tipo=TipoAviso.APOIO_DECISAO, mensagem="aviso fixo")],
    )
    assert len(resposta.fontes) == 1
    assert resposta.avisos[0].tipo == TipoAviso.APOIO_DECISAO


def test_interacao_medicamentosa_severidade_validada() -> None:
    interacao = InteracaoMedicamentosa(
        medicamento_a="A",
        medicamento_b="B",
        severidade=SeveridadeInteracao.GRAVE,
        descricao="descricao",
    )
    assert interacao.severidade == SeveridadeInteracao.GRAVE

    with pytest.raises(ValidationError):
        InteracaoMedicamentosa(
            medicamento_a="A",
            medicamento_b="B",
            severidade="critica",  # type: ignore[arg-type]
            descricao="descricao",
        )


def test_medicamento_default_ativo_true() -> None:
    m = Medicamento(nome="Amoxicilina")
    assert m.ativo is True


def test_documento_recuperado_protocolo_nao_aceita_decisao() -> None:
    from app.models.domain import DocumentoRecuperado

    with pytest.raises(ValidationError):
        DocumentoRecuperado(
            tipo=TipoFonte.PROTOCOLO,
            identificador="PROT-1",
            titulo="X",
            decisao_final=DecisaoFinal.YES,
            score_relevancia=0.9,
        )


def test_documento_recuperado_artigo_aceita_decisao_e_reasoning() -> None:
    from app.models.domain import DocumentoRecuperado

    doc = DocumentoRecuperado(
        tipo=TipoFonte.ARTIGO,
        identificador="PMID-1",
        titulo="Pneumonia",
        ano=2024,
        decisao_final=DecisaoFinal.MAYBE,
        reasoning_required=True,
        contextos=["c1"],
        meshes=["Pneumonia"],
        long_answer="explicação",
        score_relevancia=0.75,
    )
    assert doc.reasoning_required is True
    assert doc.score_relevancia == 0.75


def test_resposta_rag_confianca_fora_de_faixa() -> None:
    from app.models.domain import RespostaRAG

    with pytest.raises(ValidationError):
        RespostaRAG(resposta_texto="x", confianca_geral=1.5)


def test_sessao_medico_limite_de_esclarecimentos() -> None:
    sessao = SessaoMedico(id_sessao="s1", id_medico="m1")
    assert sessao.pode_pedir_esclarecimento()
    sessao.contador_esclarecimentos = 3
    assert not sessao.pode_pedir_esclarecimento()

    with pytest.raises(ValidationError):
        SessaoMedico(id_sessao="s1", id_medico="m1", contador_esclarecimentos=4)
