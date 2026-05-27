"""Dependências FastAPI — Fase 6.

Política de estado (documentada):
- Session store: dict em memória (`_session_store`). Adequado para instância
  única. Para múltiplas instâncias ou necessidade de persistência, substituir
  por um backend externo (ex.: Redis).
- Orquestrador: componentes pesados (LLM, vectorstore, MapadorMeSH) são
  inicializados no lifespan e armazenados em `app.state`. O objeto
  OrquestradorClinico é montado por requisição (leve), pois o
  RepositorioPacientes requer uma AsyncSession por request.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import KnowledgeBaseUnavailableError
from app.db.repositories.pacientes import RepositorioPacientes
from app.db.session import get_session
from app.models.domain import SessaoMedico
from app.orchestrator.fluxo import OrquestradorClinico

logger = logging.getLogger(__name__)

# In-memory session store (override via dependency_overrides in tests)
_session_store: dict[str, SessaoMedico] = {}


def get_session_store() -> dict[str, SessaoMedico]:
    """Retorna o store de sessões em memória.

    Override via ``app.dependency_overrides`` para testes.
    """
    return _session_store


def get_orchestrador(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> OrquestradorClinico:
    """Monta o OrquestradorClinico com dependências do ``app.state``.

    Levanta ``KnowledgeBaseUnavailableError`` (503) se o vectorstore não foi
    carregado no startup.

    Override via ``app.dependency_overrides`` para testes.
    """
    state = request.app.state
    if not getattr(state, "vectorstore", None):
        raise KnowledgeBaseUnavailableError()

    from app.nlu.esclarecimento import GeradorEsclarecimento
    from app.nlu.interpretador import InterpretadorNLU
    from app.rag.engine import MotorRAG

    settings = get_settings()
    return OrquestradorClinico(
        interpretador=InterpretadorNLU(state.llm),
        motor_rag=MotorRAG(
            vectorstore=state.vectorstore,
            llm=state.llm,
            confidence_threshold=settings.confidence_threshold,
        ),
        repo_pacientes=RepositorioPacientes(db),
        servico_interacoes=state.servico_interacoes,
        mapador_mesh=state.mesh_mapper,
        gerador_esclarecimento=GeradorEsclarecimento(state.llm),
        protocolos_vigentes=state.protocolos,
        confidence_threshold=settings.confidence_threshold,
    )


# Typed aliases for use in route signatures
OrchestradorDep = Annotated[OrquestradorClinico, Depends(get_orchestrador)]
SessionStoreDep = Annotated[dict[str, SessaoMedico], Depends(get_session_store)]


@asynccontextmanager
async def lifespan(app):
    """Inicializa componentes pesados no startup; libera no shutdown."""
    app.state.vectorstore = None  # garantir atributo sempre definido
    settings = get_settings()

    if not settings.openai_api_key:
        logger.warning(
            "openai_api_key_ausente — RAG desabilitado; "
            "configure OPENAI_API_KEY para habilitar."
        )
        yield
        return

    try:
        from langchain_community.vectorstores import FAISS
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings

        from app.rag.ingest_protocolos import carregar_protocolos
        from app.services.interacoes import servico_padrao
        from app.services.mesh_mapper import MapadorMeSH

        llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
        )
        embeddings = OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            model=settings.embeddings_model,
        )

        faiss_path = Path(settings.faiss_index_path)
        if faiss_path.exists():
            vectorstore = FAISS.load_local(
                str(faiss_path),
                embeddings,
                allow_dangerous_deserialization=True,
            )
            logger.info("faiss_loaded", extra={"path": str(faiss_path)})
        else:
            vectorstore = None
            logger.warning("faiss_nao_encontrado", extra={"path": str(faiss_path)})

        try:
            pares = carregar_protocolos("data/protocolos")
            protocolos = [p for p, _ in pares]
            logger.info("protocolos_carregados", extra={"total": len(protocolos)})
        except Exception:
            logger.exception("protocolos_carga_falhou")
            protocolos = []

        app.state.llm = llm
        app.state.vectorstore = vectorstore
        app.state.protocolos = protocolos
        app.state.mesh_mapper = MapadorMeSH(llm)
        app.state.servico_interacoes = servico_padrao()

    except Exception:
        logger.exception("startup_falhou — app iniciará sem RAG")

    yield
    logger.info("app_encerrado")
