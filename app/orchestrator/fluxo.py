"""Orquestrador de Fluxo Clínico (Fase 5, Task 5.1).

processar_pergunta:
  1. Interpreta a pergunta via NLU.
  2. Trata ciclo de esclarecimento (até 3 perguntas, Req 1.8).
  3. Despacha para o handler adequado por intenção.
  4. Aplica avisos padronizados ao resultado.

Handlers:
  - handle_consulta_clinica:  consulta geral via RAG.
  - handle_sugestao_conduta:  conduta com MeSH, ordenação e emergência.
  - handle_verificacao_exames: exames pendentes do paciente (async, DB).
  - handle_sugestao_tratamento: tratamento com validação de prontuário (async, DB).
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import DatabaseUnavailableError, PatientNotFoundError
from app.db.repositories.pacientes import RepositorioPacientes
from app.models.domain import (
    FonteReferencia,
    IntencaoClinica,
    NLUResult,
    Protocolo,
    RespostaClinica,
    RespostaRAG,
    SessaoMedico,
    TipoAviso,
    TipoFonte,
    Aviso,
)
from app.nlu.esclarecimento import GeradorEsclarecimento, MENSAGEM_FALLBACK
from app.nlu.interpretador import InterpretadorNLU
from app.orchestrator.avisos import ContextoAvisos, aplicar_avisos
from app.rag.engine import MotorRAG
from app.services.contraindicacoes import verificar_contraindicacoes
from app.services.emergencia import detectar_emergencia
from app.services.interacoes import ServicoInteracoes
from app.services.mesh_mapper import MapadorMeSH
from app.services.ordenacao import ordenar_condutas
from app.services.prontuario_validator import validar_campos_obrigatorios

logger = logging.getLogger(__name__)

_AVISO_APOIO_DECISAO = Aviso(
    tipo=TipoAviso.APOIO_DECISAO,
    mensagem=(
        "Este sistema é um auxílio à decisão clínica. "
        "O julgamento final é de responsabilidade exclusiva do médico."
    ),
)


def _doc_para_fonte(doc) -> FonteReferencia:
    return FonteReferencia(
        tipo=doc.tipo,
        identificador=doc.identificador,
        titulo=doc.titulo,
        ano=doc.ano,
        decisao_final=doc.decisao_final,
    )


class OrquestradorClinico:
    def __init__(
        self,
        interpretador: InterpretadorNLU,
        motor_rag: MotorRAG,
        repo_pacientes: RepositorioPacientes,
        servico_interacoes: ServicoInteracoes,
        mapador_mesh: MapadorMeSH,
        gerador_esclarecimento: GeradorEsclarecimento | None = None,
        protocolos_vigentes: list[Protocolo] | None = None,
        confidence_threshold: float = 0.65,
    ) -> None:
        self._interpretador = interpretador
        self._motor_rag = motor_rag
        self._repo = repo_pacientes
        self._interacoes = servico_interacoes
        self._mapador = mapador_mesh
        self._esclarecimento = gerador_esclarecimento
        self._protocolos = protocolos_vigentes or []
        self._threshold = confidence_threshold

    async def processar_pergunta(
        self, texto: str, sessao: SessaoMedico
    ) -> RespostaClinica:
        """Ponto de entrada principal. Interpreta, esclarece se necessário e despacha."""
        nlu = self._interpretador.interpretar_pergunta(texto)

        if nlu.requer_esclarecimento:
            if not sessao.pode_pedir_esclarecimento():
                return self._resposta_simples(MENSAGEM_FALLBACK)

            pergunta_esc = self._gerar_esclarecimento(texto, sessao)
            sessao.historico_perguntas.append(pergunta_esc)
            sessao.contador_esclarecimentos += 1
            return self._resposta_simples(pergunta_esc)

        sessao.historico_perguntas.append(texto)
        return await self._despachar(texto, nlu)

    async def _despachar(self, texto: str, nlu: NLUResult) -> RespostaClinica:
        intencao = nlu.intencao
        if intencao == IntencaoClinica.CONSULTA_CLINICA:
            return self.handle_consulta_clinica(texto, nlu)
        if intencao == IntencaoClinica.SUGESTAO_CONDUTA:
            return self.handle_sugestao_conduta(texto, nlu)
        if intencao == IntencaoClinica.VERIFICACAO_EXAMES:
            return await self.handle_verificacao_exames(nlu)
        if intencao == IntencaoClinica.SUGESTAO_TRATAMENTO:
            return await self.handle_sugestao_tratamento(texto, nlu)
        return self._resposta_simples(
            "Não foi possível processar sua solicitação. Tente reformular a pergunta."
        )

    # ------------------------------------------------------------------ #
    # Handlers                                                             #
    # ------------------------------------------------------------------ #

    def handle_consulta_clinica(self, texto: str, nlu: NLUResult) -> RespostaClinica:
        """Consulta clínica geral via RAG (Req 1.1, 1.2)."""
        rag = self._motor_rag.recuperar_e_gerar(texto)
        resposta = self._rag_para_clinica(rag)
        return aplicar_avisos(
            resposta,
            ContextoAvisos(resposta_rag=rag, confidence_threshold=self._threshold),
        )

    def handle_sugestao_conduta(self, texto: str, nlu: NLUResult) -> RespostaClinica:
        """Sugestão de conduta com MeSH, ordenação e detecção de emergência (Req 2.1–2.7)."""
        condicao: str = nlu.entidades.get("condicao") or texto
        termos_mesh = self._mapador.mapear_para_mesh([condicao])

        rag = self._motor_rag.recuperar_e_gerar(
            consulta=condicao,
            filtros_mesh=termos_mesh or None,
            excluir_decisao_final=["no"],  # Req 4.3
        )

        protocolos_docs = [d for d in rag.documentos if d.tipo == TipoFonte.PROTOCOLO]
        artigos_docs = [d for d in rag.documentos if d.tipo == TipoFonte.ARTIGO]
        ordenados = ordenar_condutas(
            protocolos_docs, artigos_docs, quadro_clinico=condicao
        )

        protocolo_emergencia = detectar_emergencia(condicao, self._protocolos)

        resposta = RespostaClinica(
            texto_resposta=rag.resposta_texto,
            fontes=[_doc_para_fonte(d) for d in ordenados],
            avisos=[],
            confianca=rag.confianca_geral,
        )
        return aplicar_avisos(
            resposta,
            ContextoAvisos(
                resposta_rag=rag,
                emergencia_detectada=protocolo_emergencia is not None,
                fora_protocolo=len(protocolos_docs) == 0,
                confidence_threshold=self._threshold,
            ),
        )

    async def handle_verificacao_exames(self, nlu: NLUResult) -> RespostaClinica:
        """Exames pendentes de um paciente (Req 3.1–3.5)."""
        numero = nlu.entidades.get("numero_prontuario")
        if not numero:
            return self._resposta_simples(
                "Por favor, informe o número do prontuário do paciente."
            )

        try:
            prontuario = await self._repo.buscar_prontuario(numero)
            if prontuario is None:
                raise PatientNotFoundError(
                    f"Paciente com prontuário '{numero}' não encontrado."
                )
            exames = await self._repo.listar_exames_pendentes(numero)
        except PatientNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError() from exc

        if not exames:
            texto = f"Não há exames pendentes para o paciente {numero}."
        else:
            linhas = [f"Exames pendentes para o paciente {numero}:"]
            for exame in exames:
                linhas.append(
                    f"  • {exame.nome} — {exame.status.value} "
                    f"(solicitado em {exame.data_solicitacao}, por {exame.solicitante})"
                )
            texto = "\n".join(linhas)

        resposta = RespostaClinica(
            texto_resposta=texto,
            fontes=[],
            avisos=[],
            confianca=1.0,
        )
        return aplicar_avisos(
            resposta,
            ContextoAvisos(confidence_threshold=self._threshold),
        )

    async def handle_sugestao_tratamento(
        self, texto: str, nlu: NLUResult
    ) -> RespostaClinica:
        """Tratamento personalizado com validação de prontuário (Req 4.1–4.9)."""
        numero = nlu.entidades.get("numero_prontuario")
        if not numero:
            return self._resposta_simples(
                "Por favor, informe o número do prontuário do paciente "
                "para sugestão de tratamento."
            )

        try:
            prontuario = await self._repo.buscar_prontuario(numero)
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError() from exc

        if prontuario is None:
            raise PatientNotFoundError(
                f"Paciente com prontuário '{numero}' não encontrado."
            )

        # Req 4.9: bloqueia quando campos obrigatórios ausentes
        campos_ausentes = validar_campos_obrigatorios(prontuario)
        if campos_ausentes:
            return self._resposta_simples(
                f"Prontuário incompleto. Campos obrigatórios ausentes: "
                f"{', '.join(campos_ausentes)}. "
                "Complete o prontuário antes de solicitar sugestão de tratamento."
            )

        condicao = prontuario.diagnostico_ativo or nlu.entidades.get("condicao") or texto
        termos_mesh = self._mapador.mapear_para_mesh([condicao])

        consulta_rag = (
            f"Tratamento para {condicao}. "
            f"Comorbidades: {', '.join(prontuario.comorbidades) or 'nenhuma'}. "
            f"Alergias: {', '.join(prontuario.alergias) or 'nenhuma'}."
        )
        rag = self._motor_rag.recuperar_e_gerar(
            consulta=consulta_rag,
            filtros_mesh=termos_mesh or None,
        )

        # Req 4.5–4.7: interações medicamentosas (propaga InteractionServiceUnavailableError)
        tratamento_sugerido: list[str] = list(
            nlu.entidades.get("medicamentos_mencionados") or []
        )
        interacoes = self._interacoes.verificar_interacoes(
            tratamento_sugerido, prontuario.medicamentos_em_uso
        )

        # Req 4.8: contraindicações
        contraindicacoes = verificar_contraindicacoes(
            tratamento_sugerido, prontuario, self._protocolos
        )

        # Append interaction and contraindication findings to response text
        texto_resposta = rag.resposta_texto
        if interacoes:
            texto_resposta += "\n\n**Interações medicamentosas detectadas:**"
            for ia in interacoes:
                texto_resposta += (
                    f"\n- [{ia.severidade.value.upper()}] "
                    f"{ia.medicamento_a} ✕ {ia.medicamento_b}: {ia.descricao}"
                )
        if contraindicacoes:
            texto_resposta += "\n\n**Contraindicações detectadas:**"
            for ci in contraindicacoes:
                texto_resposta += f"\n- {ci}"

        # If safety issues found, force baixa_confianca warning
        rag_para_avisos = (
            rag.model_copy(update={"aviso_baixa_confianca": True})
            if (interacoes or contraindicacoes)
            else rag
        )

        protocolo_docs = [d for d in rag.documentos if d.tipo == TipoFonte.PROTOCOLO]
        resposta = RespostaClinica(
            texto_resposta=texto_resposta,
            fontes=[_doc_para_fonte(d) for d in rag.documentos],
            avisos=[],
            confianca=rag.confianca_geral,
        )
        return aplicar_avisos(
            resposta,
            ContextoAvisos(
                resposta_rag=rag_para_avisos,
                fora_protocolo=len(protocolo_docs) == 0,
                confidence_threshold=self._threshold,
            ),
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _gerar_esclarecimento(self, texto: str, sessao: SessaoMedico) -> str:
        if self._esclarecimento is not None:
            try:
                return self._esclarecimento.gerar_pergunta(
                    pergunta_original=texto,
                    historico_esclarecimentos=list(sessao.historico_perguntas),
                )
            except Exception:
                logger.exception("falha_gerando_esclarecimento")
        n = sessao.contador_esclarecimentos + 1
        return (
            f"Esclarecimento {n}/3: poderia descrever com mais detalhes sua solicitação? "
            "Indique a condição clínica, número de prontuário ou tipo de apoio desejado."
        )

    def _resposta_simples(self, texto: str) -> RespostaClinica:
        resposta = RespostaClinica(
            texto_resposta=texto,
            fontes=[],
            avisos=[],
            confianca=0.0,
        )
        return aplicar_avisos(
            resposta,
            ContextoAvisos(confidence_threshold=self._threshold),
        )

    @staticmethod
    def _rag_para_clinica(rag: RespostaRAG) -> RespostaClinica:
        return RespostaClinica(
            texto_resposta=rag.resposta_texto,
            fontes=[_doc_para_fonte(d) for d in rag.documentos],
            avisos=[],
            confianca=rag.confianca_geral,
        )
