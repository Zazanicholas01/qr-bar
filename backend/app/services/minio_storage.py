from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.core import config


@dataclass
class MinioConfig:
    endpoint: str
    access_key: str
    secret_key: str
    secure: bool
    bucket: str


def _parse_endpoint(raw: str, secure_default: bool) -> tuple[str, bool]:
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return parsed.netloc, parsed.scheme == "https"
    return raw, secure_default


def get_minio_config() -> MinioConfig:
    endpoint, secure = _parse_endpoint(config.MINIO_ENDPOINT, config.MINIO_SECURE)
    return MinioConfig(
        endpoint=endpoint,
        access_key=config.MINIO_ACCESS_KEY,
        secret_key=config.MINIO_SECRET_KEY,
        secure=secure,
        bucket=config.MINIO_BUCKET,
    )


def get_client(minio_cfg: MinioConfig | None = None) -> Minio:
    cfg = minio_cfg or get_minio_config()
    return Minio(
        endpoint=cfg.endpoint,
        access_key=cfg.access_key,
        secret_key=cfg.secret_key,
        secure=cfg.secure,
    )


def ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket_name=bucket):
        client.make_bucket(bucket_name=bucket)


def upload_file(client: Minio, *, bucket: str, object_name: str, file_path: str, content_type: str = "application/octet-stream") -> str:
    ensure_bucket(client, bucket)
    client.fput_object(bucket_name=bucket, object_name=object_name, file_path=file_path, content_type=content_type)
    return f"{bucket}/{object_name}"


def upload_bytes(client: Minio, *, bucket: str, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    ensure_bucket(client, bucket)
    client.put_object(bucket_name=bucket, object_name=object_name, data=data, length=len(data), content_type=content_type)
    return f"{bucket}/{object_name}"
