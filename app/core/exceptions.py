import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class BaseAppError(Exception):
    """Erro base da aplicação. Mapeia para resposta HTTP estruturada."""

    code: str = "internal_error"
    http_status: int = 500
    default_message: str = "Erro interno inesperado."

    def __init__(self, message: str | None = None, **detalhes: Any) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.detalhes = detalhes


class KnowledgeBaseUnavailableError(BaseAppError):
    code = "knowledge_base_unavailable"
    http_status = 503
    default_message = (
        "O serviço de base de conhecimento está temporariamente indisponível. "
        "Tente novamente em instantes."
    )


class PLNTimeoutError(BaseAppError):
    code = "pln_timeout"
    http_status = 504
    default_message = (
        "O serviço de processamento de linguagem natural não respondeu no tempo esperado. "
        "Tente novamente."
    )


class PatientNotFoundError(BaseAppError):
    code = "patient_not_found"
    http_status = 404
    default_message = (
        "Paciente não encontrado. Verifique e corrija o número de prontuário informado."
    )


class InteractionServiceUnavailableError(BaseAppError):
    code = "interaction_service_unavailable"
    http_status = 503
    default_message = (
        "A verificação de interações medicamentosas não pôde ser realizada. "
        "Tente novamente mais tarde."
    )


class DatabaseUnavailableError(BaseAppError):
    code = "database_unavailable"
    http_status = 503
    default_message = (
        "O banco de dados está temporariamente indisponível. Tente novamente em instantes."
    )


def _build_payload(exc: BaseAppError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": exc.code,
            "message": exc.message,
        }
    }
    if exc.detalhes:
        payload["error"]["detalhes"] = exc.detalhes
    return payload


async def _app_error_handler(request: Request, exc: BaseAppError) -> JSONResponse:
    logger.warning(
        "application_error",
        extra={
            "code": exc.code,
            "http_status": exc.http_status,
            "path": request.url.path,
            "detalhes": exc.detalhes,
        },
    )
    return JSONResponse(status_code=exc.http_status, content=_build_payload(exc))


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_error",
        extra={"path": request.url.path, "exception_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Erro interno inesperado. Tente novamente.",
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BaseAppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error_handler)
