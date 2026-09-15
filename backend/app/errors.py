"""Error-code catalogue and exception handlers.

Every error response has the same JSON shape: {"code": str, "message": str, "details": list | null}.
Codes are stable identifiers for clients and support; messages are Russian text for users.
"""
import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    BAD_REQUEST = 'BAD_REQUEST'
    UNAUTHENTICATED = 'UNAUTHENTICATED'
    FORBIDDEN = 'FORBIDDEN'
    CSRF_INVALID = 'CSRF_INVALID'
    NOT_FOUND = 'NOT_FOUND'
    RECORD_NOT_FOUND = 'RECORD_NOT_FOUND'
    METHOD_NOT_ALLOWED = 'METHOD_NOT_ALLOWED'
    CONFLICT = 'CONFLICT'
    PAYLOAD_TOO_LARGE = 'PAYLOAD_TOO_LARGE'
    UNSUPPORTED_MEDIA_TYPE = 'UNSUPPORTED_MEDIA_TYPE'
    VALIDATION_ERROR = 'VALIDATION_ERROR'
    RATE_LIMITED = 'RATE_LIMITED'
    INTERNAL_ERROR = 'INTERNAL_ERROR'
    SERVICE_UNAVAILABLE = 'SERVICE_UNAVAILABLE'


# code -> (HTTP status, default user-facing message)
CATALOGUE = {
    ErrorCode.BAD_REQUEST: (400, 'Некорректный запрос'),
    ErrorCode.UNAUTHENTICATED: (401, 'Требуется вход в систему'),
    ErrorCode.FORBIDDEN: (403, 'Недостаточно прав для этого действия'),
    ErrorCode.CSRF_INVALID: (403, 'Страница устарела: обновите её и повторите действие'),
    ErrorCode.NOT_FOUND: (404, 'Ресурс не найден'),
    ErrorCode.RECORD_NOT_FOUND: (404, 'Запись не найдена'),
    ErrorCode.METHOD_NOT_ALLOWED: (405, 'Метод не поддерживается'),
    ErrorCode.CONFLICT: (409, 'Конфликт данных: запись изменена или уже существует'),
    ErrorCode.PAYLOAD_TOO_LARGE: (413, 'Слишком большой объём данных'),
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: (415, 'Неподдерживаемый формат данных'),
    ErrorCode.VALIDATION_ERROR: (422, 'Проверьте заполненные поля'),
    ErrorCode.RATE_LIMITED: (429, 'Слишком много запросов, повторите позже'),
    ErrorCode.INTERNAL_ERROR: (500, 'Внутренняя ошибка сервера'),
    ErrorCode.SERVICE_UNAVAILABLE: (503, 'Сервис временно недоступен'),
}

STATUS_TO_CODE = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str
    type: str | None = None


class ErrorResponse(BaseModel):
    code: ErrorCode
    message: str
    details: list[ErrorDetail] | None = None


class AppError(Exception):
    def __init__(self, code, message=None, details=None):
        status, default_message = CATALOGUE[code]
        super().__init__(message or default_message)
        self.code = code
        self.status = status
        self.message = message or default_message
        self.details = details


def error_response(code, message=None, details=None, headers=None, status=None):
    default_status, default_message = CATALOGUE[code]
    body = {'code': code.value, 'message': message or default_message, 'details': details}
    return JSONResponse(status_code=status or default_status, content=jsonable_encoder(body), headers=headers)


def _validation_details(errors):
    details = []
    for error in errors:
        # Drop the leading location marker ("body", "query", "path") so the field name matches the form field.
        location = [str(part) for part in error.get('loc', ())]
        if location and location[0] in {'body', 'query', 'path', 'header', 'cookie'}:
            location = location[1:]
        details.append({'field': '.'.join(location) or None, 'message': error.get('msg', ''), 'type': error.get('type')})
    return details


def install_error_handlers(app: FastAPI):
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return error_response(exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return error_response(ErrorCode.VALIDATION_ERROR, details=_validation_details(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        code = STATUS_TO_CODE.get(exc.status_code)
        if code is None:
            code = ErrorCode.INTERNAL_ERROR if exc.status_code >= 500 else ErrorCode.BAD_REQUEST
        message = exc.detail if isinstance(exc.detail, str) and exc.detail not in {'Not Found', 'Method Not Allowed'} else None
        return error_response(code, message, headers=getattr(exc, 'headers', None), status=exc.status_code)

    @app.exception_handler(OperationalError)
    async def handle_database_unavailable(request: Request, exc: OperationalError):
        logger.error('Database unavailable: %s', exc.orig)
        return error_response(ErrorCode.SERVICE_UNAVAILABLE)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        # Internal details stay in the server log; the client only gets a stable code.
        logger.exception('Unhandled error on %s %s', request.method, request.url.path)
        return error_response(ErrorCode.INTERNAL_ERROR)
