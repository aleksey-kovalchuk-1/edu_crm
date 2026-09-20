"""Shared file-upload validation and storage, used by workflow status changes and task comments
(decisions D-153; docs/design/tasks.md). Files are checked by content signature and extension, then
streamed to the attachments volume under a random key; the caller decides which row type to attach
the resulting metadata to.
"""
import hashlib
import secrets
import unicodedata

from .errors import AppError, ErrorCode

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENTS = 5
CHUNK_BYTES = 1024 * 1024

ZIP = (b'PK\x03\x04', b'PK\x05\x06')
OLE = (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1',)
# extension -> (accepted leading bytes, content type sent on download); the extension and the content must agree.
FILE_TYPES = {
    'png': ((b'\x89PNG\r\n\x1a\n',), 'image/png'),
    'jpg': ((b'\xff\xd8\xff',), 'image/jpeg'),
    'jpeg': ((b'\xff\xd8\xff',), 'image/jpeg'),
    'pdf': ((b'%PDF-',), 'application/pdf'),
    'zip': (ZIP, 'application/zip'),
    'gz': ((b'\x1f\x8b',), 'application/gzip'),
    'gzip': ((b'\x1f\x8b',), 'application/gzip'),
    'rar': ((b'Rar!\x1a\x07',), 'application/vnd.rar'),
    'doc': (OLE, 'application/msword'),
    'xls': (OLE, 'application/vnd.ms-excel'),
    'docx': (ZIP, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    'xlsx': (ZIP, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
}
ALLOWED_TYPES_TEXT = 'png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx'


def field_error(code, field, message):
    return AppError(code, message, [{'field': field, 'message': message, 'type': 'value_error'}])


def clean_filename(raw):
    name = (raw or 'file').replace('\\', '/').rsplit('/', 1)[-1]
    name = ''.join(ch for ch in name if not unicodedata.category(ch).startswith('C')).strip() or 'file'
    if len(name) > 255:
        stem, dot, extension = name.rpartition('.')
        name = (stem[:255 - len(extension) - 1] + dot + extension) if dot and len(extension) < 20 else name[:255]
    return name


def store_upload(upload, directory, *, field='files'):
    """Checks one uploaded file and streams it to disk under a random key.

    Returns (filename, content_type, size_bytes, sha256_hex, storage_key, path); the caller builds
    whichever ORM row (Attachment or TaskAttachment) it needs from these.
    """
    filename = clean_filename(upload.filename)
    extension = filename.rpartition('.')[2].lower() if '.' in filename else ''
    if extension not in FILE_TYPES:
        raise field_error(ErrorCode.UNSUPPORTED_MEDIA_TYPE, field, f'Файл «{filename}»: допустимые форматы — {ALLOWED_TYPES_TEXT}')
    signatures, content_type = FILE_TYPES[extension]
    head = upload.file.read(8)
    if not head.startswith(signatures):
        raise field_error(ErrorCode.UNSUPPORTED_MEDIA_TYPE, field, f'Файл «{filename}»: содержимое не соответствует расширению .{extension}')
    key = secrets.token_hex(16)
    path = directory / key
    digest = hashlib.sha256(head)
    size = len(head)
    try:
        with open(path, 'xb') as target:
            target.write(head)
            while chunk := upload.file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_ATTACHMENT_BYTES:
                    raise field_error(ErrorCode.PAYLOAD_TOO_LARGE, field, f'Файл «{filename}» больше 20 МБ')
                digest.update(chunk)
                target.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return filename, content_type, size, digest.hexdigest(), key, path
