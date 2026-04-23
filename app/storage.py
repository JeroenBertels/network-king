from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.settings import Settings


@dataclass
class StoredFile:
    content: bytes
    content_type: str


class LocalStorageBackend:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, content: bytes, filename: str) -> str:
        suffix = Path(filename).suffix.lower() or ".bin"
        key = f"profiles/{uuid.uuid4().hex}{suffix}"
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return key

    def read_bytes(self, key: str) -> StoredFile:
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise FileNotFoundError("Invalid media key")
        content_type, _ = mimetypes.guess_type(path.name)
        return StoredFile(content=path.read_bytes(), content_type=content_type or "application/octet-stream")


class GCSStorageBackend:
    def __init__(self, bucket_name: str):
        if not bucket_name:
            raise RuntimeError("GCS bucket name is required when STORAGE_BACKEND=gcs.")
        try:
            from google.cloud import storage
        except ImportError as exc:  # pragma: no cover - exercised in deployment only.
            raise RuntimeError("Install the gcp extra to use Google Cloud Storage.") from exc
        client = storage.Client()
        self.bucket = client.bucket(bucket_name)

    def save_bytes(self, content: bytes, filename: str) -> str:
        suffix = Path(filename).suffix.lower() or ".bin"
        key = f"profiles/{uuid.uuid4().hex}{suffix}"
        blob = self.bucket.blob(key)
        content_type, _ = mimetypes.guess_type(filename)
        blob.upload_from_string(content, content_type=content_type or "application/octet-stream")
        return key

    def read_bytes(self, key: str) -> StoredFile:
        blob = self.bucket.blob(key)
        content = blob.download_as_bytes()
        return StoredFile(content=content, content_type=blob.content_type or "application/octet-stream")


class StorageService:
    def __init__(self, settings: Settings):
        if settings.storage_backend == "gcs":
            self.backend = GCSStorageBackend(settings.gcs_bucket_name)
        else:
            self.backend = LocalStorageBackend(settings.local_media_root)

    def save_bytes(self, content: bytes, filename: str) -> str:
        return self.backend.save_bytes(content, filename)

    def read_bytes(self, key: str) -> StoredFile:
        return self.backend.read_bytes(key)

