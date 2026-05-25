from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StatusExame(str, Enum):
    SOLICITADO = "Solicitado"
    COLETADO = "Coletado"
    EM_ANALISE = "Em Análise"
    CONCLUIDO = "Concluído"
    CANCELADO = "Cancelado"


STATUS_EXAME_PENDENTE: frozenset[StatusExame] = frozenset(
    {StatusExame.SOLICITADO, StatusExame.COLETADO, StatusExame.EM_ANALISE}
)


class DecisaoFinal(str, Enum):
    YES = "yes"
    NO = "no"
    MAYBE = "maybe"


class ReasoningRequired(str, Enum):
    YES = "yes"
    NO = "no"


class TipoFonte(str, Enum):
    ARTIGO = "artigo"
    PROTOCOLO = "protocolo"


class TipoAviso(str, Enum):
    BAIXA_CONFIANCA = "baixa_confianca"
    EVIDENCIA_INCONCLUSIVA = "evidencia_inconclusiva"
    RACIOCINIO_NECESSARIO = "raciocinio_necessario"
    EMERGENCIA = "emergencia"
    APOIO_DECISAO = "apoio_decisao"
    FORA_PROTOCOLO = "fora_protocolo"


class SeveridadeInteracao(str, Enum):
    LEVE = "leve"
    MODERADA = "moderada"
    GRAVE = "grave"


class EntradaPubMedQA(BaseModel):
    """Entrada da Base_de_Conhecimento no formato PubMedQA."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    QUESTION: str = Field(min_length=1)
    CONTEXTS: list[str] = Field(default_factory=list)
    LABELS: list[str] = Field(default_factory=list)
    MESHES: list[str] = Field(default_factory=list)
    YEAR: int = Field(ge=1900, le=2100)
    reasoning_required_pred: ReasoningRequired
    final_decision: DecisaoFinal
    LONG_ANSWER: str = ""

    @field_validator("LABELS")
    @classmethod
    def _labels_match_contexts(cls, v: list[str], info) -> list[str]:
        contexts = info.data.get("CONTEXTS")
        if contexts is not None and len(v) not in (0, len(contexts)):
            raise ValueError(
                "LABELS deve estar vazio ou ter o mesmo tamanho de CONTEXTS."
            )
        return v


class Protocolo(BaseModel):
    """Protocolo clínico interno do hospital."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    titulo: str = Field(min_length=1)
    nivel_evidencia: str = Field(min_length=1)
    condicoes_aplicaveis: list[str] = Field(default_factory=list)
    contraindicacoes: list[str] = Field(default_factory=list)
    termos_emergencia: list[str] = Field(default_factory=list)
    vigente: bool = True


class Medicamento(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1)
    data_inicio: date | None = None
    ativo: bool = True


class Exame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1)
    data_solicitacao: date
    solicitante: str = Field(min_length=1)
    status: StatusExame

    def pendente(self) -> bool:
        return self.status in STATUS_EXAME_PENDENTE


class Prontuario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero: str = Field(min_length=1)
    diagnostico_ativo: str | None = None
    medicamentos_em_uso: list[str] = Field(default_factory=list)
    alergias: list[str] = Field(default_factory=list)
    comorbidades: list[str] = Field(default_factory=list)
    historico_clinico: str | None = None


class FonteReferencia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoFonte
    identificador: str = Field(min_length=1)
    titulo: str = Field(min_length=1)
    ano: int | None = Field(default=None, ge=1900, le=2100)
    decisao_final: DecisaoFinal | None = None

    @field_validator("decisao_final")
    @classmethod
    def _protocolo_nao_tem_decisao(
        cls, v: DecisaoFinal | None, info
    ) -> DecisaoFinal | None:
        if v is not None and info.data.get("tipo") == TipoFonte.PROTOCOLO:
            raise ValueError("Protocolo não possui decisao_final.")
        return v


class Aviso(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoAviso
    mensagem: str = Field(min_length=1)
    destaque: bool = False


class RespostaClinica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto_resposta: str
    fontes: list[FonteReferencia] = Field(default_factory=list)
    avisos: list[Aviso] = Field(default_factory=list)
    confianca: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentoRecuperado(BaseModel):
    """Documento retornado pelo motor RAG (artigo ou protocolo)."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoFonte
    identificador: str = Field(min_length=1)
    titulo: str = Field(min_length=1)
    ano: int | None = Field(default=None, ge=1900, le=2100)
    decisao_final: DecisaoFinal | None = None
    reasoning_required: bool = False
    contextos: list[str] = Field(default_factory=list)
    meshes: list[str] = Field(default_factory=list)
    long_answer: str | None = None
    score_relevancia: float = Field(ge=0.0, le=1.0)

    @field_validator("decisao_final")
    @classmethod
    def _protocolo_nao_tem_decisao(
        cls, v: DecisaoFinal | None, info
    ) -> DecisaoFinal | None:
        if v is not None and info.data.get("tipo") == TipoFonte.PROTOCOLO:
            raise ValueError("Protocolo não possui decisao_final.")
        return v


class RespostaRAG(BaseModel):
    """Resultado da chamada ao motor RAG."""

    model_config = ConfigDict(extra="forbid")

    resposta_texto: str
    documentos: list[DocumentoRecuperado] = Field(default_factory=list)
    confianca_geral: float = Field(ge=0.0, le=1.0)
    aviso_baixa_confianca: bool = False


class InteracaoMedicamentosa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medicamento_a: str = Field(min_length=1)
    medicamento_b: str = Field(min_length=1)
    severidade: SeveridadeInteracao
    descricao: str = Field(min_length=1)


class IntencaoClinica(str, Enum):
    CONSULTA_CLINICA = "CONSULTA_CLINICA"
    SUGESTAO_CONDUTA = "SUGESTAO_CONDUTA"
    VERIFICACAO_EXAMES = "VERIFICACAO_EXAMES"
    SUGESTAO_TRATAMENTO = "SUGESTAO_TRATAMENTO"
    INTENCAO_DESCONHECIDA = "INTENCAO_DESCONHECIDA"


class NLUResult(BaseModel):
    """Resultado da interpretação de uma pergunta clínica."""

    model_config = ConfigDict(extra="forbid")

    intencao: IntencaoClinica
    entidades: dict[str, Any] = Field(default_factory=dict)
    confianca: float = Field(default=0.0, ge=0.0, le=1.0)
    idioma_detectado: str = Field(default="pt-BR")
    requer_esclarecimento: bool = False

    @field_validator("requer_esclarecimento", mode="before")
    @classmethod
    def _forca_esclarecimento_em_desconhecida(cls, v, info):
        if info.data.get("intencao") == IntencaoClinica.INTENCAO_DESCONHECIDA:
            return True
        return bool(v)


class SessaoMedico(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_sessao: str = Field(min_length=1)
    id_medico: str = Field(min_length=1)
    historico_perguntas: list[str] = Field(default_factory=list)
    contador_esclarecimentos: int = Field(default=0, ge=0, le=3)
    idioma: str = "pt-BR"
    timestamp_inicio: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def pode_pedir_esclarecimento(self) -> bool:
        return self.contador_esclarecimentos < 3
