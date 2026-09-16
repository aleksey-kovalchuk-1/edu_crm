"""Document upload, versioning and short-lived downloads (T-093/T-094; design: docs/design/file-ingestion-plan.md
§3.3/3.4; decisions D-165, D-168, D-169, D-170).

A `Document` is a versioned, titled file library entry polymorphically linked to a `university`, `launch`
(interaction) or `contract` -- deliberately separate from the workflow `attachments` table (D-169). Each
upload becomes a `DocumentVersion` that moves through the state machine in docs/design/file-ingestion-plan.md
§5.3: `uploaded -> quarantined -> validated -> linked`, or `-> rejected` at either checkpoint. This module
only ever writes a version straight to `quarantined` (never a bare `uploaded` row -- see `store_document_upload`
docstring) and hands the scan off to `app.document_jobs.run_document_scan`; `validated`/`linked` are the scan
job's responsibility, not this module's.

Document identity rule: a new upload always creates a new `Document` UNLESS the caller passes an explicit
`document_id` naming an existing document for the same `entity_type`/`entity_id` -- in that case the upload
becomes the next `DocumentVersion` of that document. There is no implicit "same title = same document"
matching: that would silently merge unrelated uploads that happen to share a title, which is worse than
requiring the frontend to pass the id it already has when the user is adding a new version from a document's
own page.

Allowed formats: PDF and DOCX only (narrower than the workflow attachment format list in D-153/
`workflow_routes.FILE_TYPES`) -- this endpoint is specifically the brief's "PDF and DOCX upload" flow, not a
general attachment box, so there is no reason to accept images/archives/legacy Office formats here.
"""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import jobs
from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, AuthContext, require_roles
from .catalog_routes import PersonOut, contract_in_scope, university_in_scope
from .db import get_db
from .errors import AppError, ErrorCode
from .models import DOCUMENT_ENTITY_TYPES, Document, DocumentVersion, User
from .workflow_routes import clean_filename
from .workflows import launch_in_scope

router = APIRouter(prefix='/api/v1', tags=['Документы'])
any_role = require_roles(*ALL_ROLES)

ZIP = (b'PK\x03\x04', b'PK\x05\x06')
DOCUMENT_FILE_TYPES = {
    'pdf': ((b'%PDF-',), 'application/pdf'),
    'docx': (ZIP, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
}
ALLOWED_DOCUMENT_TYPES_TEXT = 'pdf, docx'
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024  # TODO T-095: move to an admin-configurable size policy
CHUNK_BYTES = 1024 * 1024
DOWNLOAD_LINK_TTL_SECONDS = 300  # 5 minutes (D-170)

TITLE_MAX, DOC_TYPE_MAX, YEAR_MAX, SOURCE_MAX = 300, 50, 20, 200


# ---------- schemas ----------

class DocumentUploadOut(BaseModel):
    document_id: int
    version_id: int
    version_number: int
    state: str
    scan_result: str
    job_id: int


class DocumentVersionOut(BaseModel):
    id: int
    document_id: int
    version_number: int
    filename: str
    content_type: str
    size_bytes: int
    state: str
    scan_result: str
    uploaded_by: PersonOut | None
    created_at: datetime


class DocumentOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    title: str
    doc_type: str
    academic_year: str
    source: str
    owner: PersonOut | None
    created_at: datetime
    latest_version: DocumentVersionOut | None


class DownloadLinkOut(BaseModel):
    url: str
    expires_at: datetime


# ---------- helpers ----------

def field_error(code, field, message):
    return AppError(code, message, [{'field': field, 'message': message, 'type': 'value_error'}])


def bounded(value, max_length, field, label):
    value = (value or '').strip()
    if len(value) > max_length:
        raise field_error(ErrorCode.VALIDATION_ERROR, field, f'{label}: не длиннее {max_length} символов')
    return value


def entity_in_scope(db, user, entity_type, entity_id):
    """Existence + scope check for the three polymorphic link targets; each helper already answers
    RECORD_NOT_FOUND (404) rather than FORBIDDEN for an out-of-scope id, matching this codebase's
    "don't reveal existence" convention (catalog_routes.py, workflows.py)."""
    if entity_type == 'university':
        return university_in_scope(db, user, entity_id)
    if entity_type == 'launch':
        return launch_in_scope(db, user, entity_id)
    return contract_in_scope(db, user, entity_id)  # entity_type is pre-validated against DOCUMENT_ENTITY_TYPES


def store_document_upload(upload, quarantine_dir):
    """Checks one uploaded file (extension+signature, size cap) and streams it to `quarantine_dir` under a
    random key -- the same mechanics as `workflow_routes.store_upload` (D-153), generalized to the narrower
    PDF/DOCX set. An empty file never passes: no PDF/DOCX signature can start with zero bytes, so it falls
    out through the same signature-mismatch branch as any other malformed upload.

    Returns (filename, content_type, storage_key, sha256_hex, size_bytes). The file on disk after a
    successful call has already passed every synchronous check, so callers create the `DocumentVersion` row
    directly in state `quarantined` -- there is no separate `uploaded` row ever persisted; on any failure the
    partial file is removed and nothing is stored (§5.3: `Rejected` at this checkpoint leaves no trace).
    """
    filename = clean_filename(upload.filename)
    extension = filename.rpartition('.')[2].lower() if '.' in filename else ''
    if extension not in DOCUMENT_FILE_TYPES:
        raise field_error(ErrorCode.UNSUPPORTED_MEDIA_TYPE, 'file', f'Файл «{filename}»: допустимые форматы — {ALLOWED_DOCUMENT_TYPES_TEXT}')
    signatures, content_type = DOCUMENT_FILE_TYPES[extension]
    head = upload.file.read(8)
    if not head.startswith(signatures):
        raise field_error(ErrorCode.UNSUPPORTED_MEDIA_TYPE, 'file', f'Файл «{filename}»: содержимое не соответствует расширению .{extension}')
    key = secrets.token_hex(16)
    path = quarantine_dir / key
    digest = hashlib.sha256(head)
    size = len(head)
    try:
        with open(path, 'xb') as target:
            target.write(head)
            while chunk := upload.file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_DOCUMENT_BYTES:
                    raise field_error(ErrorCode.PAYLOAD_TOO_LARGE, 'file', f'Файл «{filename}» больше {MAX_DOCUMENT_BYTES // (1024 * 1024)} МБ')
                digest.update(chunk)
                target.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return filename, content_type, key, digest.hexdigest(), size


def load_users(db, ids):
    ids = {i for i in ids if i}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def person(users, user_id):
    return PersonOut(id=users[user_id].id, full_name=users[user_id].full_name) if user_id in users else None


def version_out(version, users):
    return DocumentVersionOut(
        id=version.id, document_id=version.document_id, version_number=version.version_number,
        filename=version.filename, content_type=version.content_type, size_bytes=version.size_bytes,
        state=version.state, scan_result=version.scan_result,
        uploaded_by=person(users, version.uploaded_by_user_id), created_at=version.created_at,
    )


def document_out(document, users):
    versions = document.versions  # relationship is ordered by version_number ascending
    latest = versions[-1] if versions else None
    return DocumentOut(
        id=document.id, entity_type=document.entity_type, entity_id=document.entity_id, title=document.title,
        doc_type=document.doc_type, academic_year=document.academic_year, source=document.source,
        owner=person(users, document.owner_user_id), created_at=document.created_at,
        latest_version=version_out(latest, users) if latest else None,
    )


def sign_download_token(settings, version_id, expires):
    message = f'{version_id}:{expires}'.encode()
    return hmac.new(settings.download_link_key.encode(), message, hashlib.sha256).hexdigest()


def verify_download_token(settings, version_id, token, expires):
    if expires < int(time.time()):
        return False
    return hmac.compare_digest(sign_download_token(settings, version_id, expires), token or '')


def linked_version_in_scope(db, user, version_id):
    """Only a `linked` version is ever downloadable (§5.3); any other state -- including `rejected` -- answers
    the same RECORD_NOT_FOUND as "version does not exist", so a rejected file's existence is never hinted at."""
    version = db.get(DocumentVersion, version_id)
    if version is None or version.state != 'linked':
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    document = db.get(Document, version.document_id)
    if document is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    entity_in_scope(db, user, document.entity_type, document.entity_id)  # re-checked at issue AND download time
    return version, document


def admin_access_payload(user, base):
    # D-168: every administrator read of document content is flagged separately in the audit payload so a
    # later access-hardening phase can restrict crm-admin without a data-model change.
    if ROLE_ADMIN in user.roles:
        return {**base, 'admin_access': True}
    return base


# ---------- upload ----------

@router.post(
    '/documents', response_model=DocumentUploadOut, status_code=202, summary='Загрузить документ (PDF/DOCX)',
    description=(
        f'`multipart/form-data`. Форматы: {ALLOWED_DOCUMENT_TYPES_TEXT}; не больше {MAX_DOCUMENT_BYTES // (1024 * 1024)} МБ. '
        'Файл уходит в карантин и на антивирусную проверку фоновой задачей; ответ 202 отражает промежуточное '
        'состояние (`quarantined`), не окончательное. Передайте `document_id`, чтобы добавить новую версию '
        'существующего документа; без него всегда создаётся новый документ.'
    ),
)
def upload_document(
    request: Request,
    entity_type: Annotated[str, Form()],
    entity_id: Annotated[int, Form()],
    title: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[str, Form()] = '',
    academic_year: Annotated[str, Form()] = '',
    source: Annotated[str, Form()] = '',
    document_id: Annotated[int | None, Form()] = None,
    auth: AuthContext = Depends(any_role),
    db: Session = Depends(get_db),
):
    entity_type = entity_type.strip()
    if entity_type not in DOCUMENT_ENTITY_TYPES:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'entity_type', 'Недопустимый тип объекта: university, launch или contract')
    entity_in_scope(db, auth.user, entity_type, entity_id)

    title = bounded(title, TITLE_MAX, 'title', 'Название документа')
    if not title:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'title', 'Укажите название документа')
    doc_type = bounded(doc_type, DOC_TYPE_MAX, 'doc_type', 'Тип документа')
    academic_year = bounded(academic_year, YEAR_MAX, 'academic_year', 'Учебный год')
    source = bounded(source, SOURCE_MAX, 'source', 'Источник')

    existing_document = None
    if document_id is not None:
        # Locked for the rest of this transaction so two concurrent uploads of the same document cannot
        # compute the same next version_number (the unique constraint would also catch it, but the lock
        # avoids a wasted file write and a 409 the caller has to retry).
        existing_document = db.scalar(
            select(Document).where(Document.id == document_id, Document.entity_type == entity_type, Document.entity_id == entity_id)
            .with_for_update()
        )
        if existing_document is None:
            raise AppError(ErrorCode.RECORD_NOT_FOUND)

    quarantine_dir = Path(request.app.state.settings.documents_dir) / 'quarantine'
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    filename, content_type, key, sha256_hex, size = store_document_upload(file, quarantine_dir)
    path = quarantine_dir / key

    try:
        if existing_document is not None:
            document = existing_document
            next_version = (db.scalar(
                select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id)
            ) or 0) + 1
        else:
            document = Document(
                entity_type=entity_type, entity_id=entity_id, title=title, doc_type=doc_type,
                academic_year=academic_year, source=source, owner_user_id=auth.user.id,
            )
            db.add(document)
            db.flush()
            next_version = 1

        version = DocumentVersion(
            document_id=document.id, version_number=next_version, storage_key=key, sha256=sha256_hex, size_bytes=size,
            content_type=content_type, filename=filename, state='quarantined', scan_result='pending',
            uploaded_by_user_id=auth.user.id,
        )
        db.add(version)
        db.flush()
        record_event(
            db, request, auth.user, 'document.upload', entity_type='document', entity_id=document.id,
            summary=f'Загружен файл «{filename}» (документ «{document.title}», версия {next_version})',
            payload={'entity_type': entity_type, 'entity_id': entity_id, 'version_id': version.id, 'size_bytes': size, 'sha256': sha256_hex},
        )
        job = jobs.enqueue(
            db, 'document_scan', {'document_version_id': version.id},
            correlation_id=getattr(request.state, 'correlation_id', None), user_id=auth.user.id,
        )
        db.commit()
    except BaseException:
        db.rollback()
        path.unlink(missing_ok=True)
        raise

    return DocumentUploadOut(
        document_id=document.id, version_id=version.id, version_number=next_version,
        state=version.state, scan_result=version.scan_result, job_id=job.id,
    )


# ---------- listing ----------

@router.get('/documents', response_model=list[DocumentOut], summary='Документы объекта (вуз, взаимодействие или договор)')
def list_documents(entity_type: str, entity_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    entity_type = entity_type.strip()
    if entity_type not in DOCUMENT_ENTITY_TYPES:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'entity_type', 'Недопустимый тип объекта: university, launch или contract')
    entity_in_scope(db, auth.user, entity_type, entity_id)
    documents = db.scalars(
        select(Document).where(Document.entity_type == entity_type, Document.entity_id == entity_id)
        .options(selectinload(Document.versions))
        .order_by(Document.created_at.desc(), Document.id.desc())
    ).all()
    user_ids = {d.owner_user_id for d in documents if d.owner_user_id}
    for d in documents:
        user_ids |= {v.uploaded_by_user_id for v in d.versions if v.uploaded_by_user_id}
    users = load_users(db, user_ids)
    return [document_out(d, users) for d in documents]


@router.get('/documents/{document_id}/versions', response_model=list[DocumentVersionOut], summary='История версий документа')
def list_document_versions(document_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    entity_in_scope(db, auth.user, document.entity_type, document.entity_id)
    versions = db.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == document_id).order_by(DocumentVersion.version_number)
    ).all()
    users = load_users(db, {v.uploaded_by_user_id for v in versions if v.uploaded_by_user_id})
    return [version_out(v, users) for v in versions]


# ---------- short-lived downloads (D-170) ----------

@router.get('/documents/versions/{version_id}/download-link', response_model=DownloadLinkOut, summary='Выдать короткоживущую ссылку на скачивание')
def create_download_link(version_id: int, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    version, document = linked_version_in_scope(db, auth.user, version_id)
    settings = request.app.state.settings
    expires = int(time.time()) + DOWNLOAD_LINK_TTL_SECONDS
    token = sign_download_token(settings, version_id, expires)
    record_event(
        db, request, auth.user, 'document.download_link', entity_type='document_version', entity_id=version.id,
        summary=f'Выдана ссылка на скачивание файла «{version.filename}»',
        payload=admin_access_payload(auth.user, {'document_id': document.id, 'expires': expires}),
    )
    db.commit()
    return DownloadLinkOut(
        url=f'/api/v1/documents/versions/{version_id}/download?token={token}&expires={expires}',
        expires_at=datetime.fromtimestamp(expires, tz=timezone.utc),
    )


@router.get('/documents/versions/{version_id}/download', response_class=FileResponse, summary='Скачать файл по короткоживущей ссылке',
            responses={200: {'content': {'application/octet-stream': {}}}})
def download_document_version(
    version_id: int, token: str, expires: int, request: Request,
    auth: AuthContext = Depends(any_role), db: Session = Depends(get_db),
):
    settings = request.app.state.settings
    if not verify_download_token(settings, version_id, token, expires):
        # Same response as "no such version": an expired/forged token must not distinguish a real,
        # rejected, or nonexistent version from one another.
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    # D-170: the token proves the link was legitimately issued, not that access is still valid -- scope is
    # re-checked here, independently of whatever it was at issue time.
    version, document = linked_version_in_scope(db, auth.user, version_id)
    path = Path(settings.documents_dir) / 'documents' / version.storage_key
    if not path.is_file():
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    record_event(
        db, request, auth.user, 'document.download', entity_type='document_version', entity_id=version.id,
        summary=f'Скачан файл «{version.filename}»', payload=admin_access_payload(auth.user, {'document_id': document.id}),
    )
    db.commit()
    return FileResponse(path, media_type=version.content_type, filename=version.filename,
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})
