"""Uploaded-file storage on a shared volume (backend writes, worker reads)."""

from __future__ import annotations

import os
import shutil
import uuid

from app.config import get_settings

_settings = get_settings()


def safe_filename(filename: str) -> str:
    """Client filenames are untrusted: strip any path components (both
    separators) so a name like `../../evil` cannot escape the document dir."""
    name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in (".", ".."):
        return "upload.bin"
    return name


def document_dir(document_id: uuid.UUID) -> str:
    return os.path.join(_settings.storage_dir, str(document_id))


def save_document(document_id: uuid.UUID, filename: str, data: bytes) -> str:
    d = document_dir(document_id)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, safe_filename(filename))
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def read_document(document_id: uuid.UUID, filename: str) -> bytes:
    path = os.path.join(document_dir(document_id), safe_filename(filename))
    with open(path, "rb") as fh:
        return fh.read()


def delete_document_files(document_id: uuid.UUID) -> None:
    shutil.rmtree(document_dir(document_id), ignore_errors=True)
