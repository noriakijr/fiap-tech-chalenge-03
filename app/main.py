from fastapi import FastAPI

from app.api.deps import lifespan
from app.api.routes import conduta, consulta, exames, sessao, tratamento
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Assistente Virtual Médico Hospitalar",
        version="0.1.0",
        description=(
            "API de suporte à decisão clínica baseada em RAG sobre PubMedQA "
            "e protocolos internos do hospital."
        ),
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    app.include_router(sessao.router, prefix="/v1", tags=["sessão"])
    app.include_router(consulta.router, prefix="/v1", tags=["consulta"])
    app.include_router(conduta.router, prefix="/v1", tags=["conduta"])
    app.include_router(exames.router, prefix="/v1", tags=["exames"])
    app.include_router(tratamento.router, prefix="/v1", tags=["tratamento"])

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
