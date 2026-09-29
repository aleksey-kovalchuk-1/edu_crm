"""Demo policy documents for «Настройки → Персональные данные» (owner request 2026-09-29, D-242).

The .docx files ship with the API image (app/policy_documents, provenance and checksums in SOURCES.md), so downloads
stay stable if the Google documents change. Only signed-in CRM users may download them.
"""
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from .auth import ALL_ROLES, require_roles
from .errors import AppError, ErrorCode

router = APIRouter(prefix='/api/v1/documents', tags=['documents'])
FOLDER = Path(__file__).parent / 'policy_documents'
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


@dataclass(frozen=True)
class PolicyDocument:
    file: str
    filename: str


DOCUMENTS = {
    'personal-data-policy': PolicyDocument(
        'personal-data-policy.docx', 'UniCRM_Политика_обработки_персональных_данных_демо.docx'),
    'information-security-policy': PolicyDocument(
        'information-security-policy.docx', 'UniCRM_Политика_информационной_безопасности_демо.docx'),
}


@router.get('/{slug}', summary='Скачать демонстрационную версию политики (.docx)',
            dependencies=[Depends(require_roles(*ALL_ROLES))], response_class=FileResponse)
def download_policy(slug: str):
    document = DOCUMENTS.get(slug)
    if document is None:
        raise AppError(ErrorCode.NOT_FOUND, 'Документ не найден')
    return FileResponse(FOLDER / document.file, media_type=DOCX, filename=document.filename,
                        headers={'Cache-Control': 'private, no-store'})
