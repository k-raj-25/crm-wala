"""Object storage abstraction: local disk (dev) or any S3-compatible service (R2, S3, MinIO).

Files are never stored in Postgres. Downloads use short-lived signed URLs.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from flask import current_app

from app.core import crypto


class Storage(Protocol):
    def put(self, key: str, data: BinaryIO, content_type: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, filename: str, expires: int = 300) -> str: ...
    def open(self, key: str) -> Path: ...


class LocalStorage:
    def __init__(self) -> None:
        self.root = Path(current_app.config["STORAGE_LOCAL_DIR"]).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("invalid key")
        return p

    def put(self, key, data, content_type):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            while chunk := data.read(1024 * 1024):
                f.write(chunk)

    def delete(self, key):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass

    def signed_url(self, key, filename, expires=300):
        exp = int(time.time()) + expires
        sig = crypto.sign(f"{key}|{exp}")
        return f"{current_app.config['WEB_ORIGIN']}/api/v1/files/local?key={key}&exp={exp}&sig={sig}&name={filename}"

    def open(self, key):
        return self._path(key)


class S3Storage:
    def __init__(self) -> None:
        import boto3

        c = current_app.config
        self.bucket = c["S3_BUCKET"]
        self.client = boto3.client("s3", endpoint_url=c["S3_ENDPOINT_URL"], region_name=c["S3_REGION"],
                                   aws_access_key_id=c["S3_ACCESS_KEY_ID"], aws_secret_access_key=c["S3_SECRET_ACCESS_KEY"])

    def put(self, key, data, content_type):
        self.client.upload_fileobj(data, self.bucket, key, ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"})

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key, filename, expires=300):
        return self.client.generate_presigned_url(
            "get_object", ExpiresIn=expires,
            Params={"Bucket": self.bucket, "Key": key, "ResponseContentDisposition": f'attachment; filename="{filename}"'})

    def open(self, key):  # pragma: no cover
        raise NotImplementedError


def get_storage() -> Storage:
    return S3Storage() if current_app.config["STORAGE_BACKEND"] == "s3" else LocalStorage()


def new_key(workspace_id, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"{workspace_id}/{uuid.uuid4().hex}{ext}"
