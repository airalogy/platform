import os
from functools import lru_cache
from typing import BinaryIO

from app.config import config
from app.libs.storage import MinioStorage, OssStorage, StorageBackend

MANAGED_STORAGE_BACKENDS = {"minio", "oss"}


def default_storage_backend() -> str:
    return config.STORAGE_BACKEND


def _normalize_backend(backend: str | None = None) -> str:
    return backend or default_storage_backend()


@lru_cache(maxsize=None)
def get_storage_backend(backend: str | None = None) -> StorageBackend:
    backend = _normalize_backend(backend)
    if backend == "minio":
        return MinioStorage(
            endpoint=config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            bucket=config.MINIO_BUCKET,
            secure=False,
        )
    if backend == "oss":
        os.environ["OSS_ACCESS_KEY_ID"] = config.OSS_ACCESS_KEY_ID
        os.environ["OSS_ACCESS_KEY_SECRET"] = config.OSS_ACCESS_KEY_SECRET
        return OssStorage(
            region=config.OSS_REGION,
            endpoint=config.OSS_ENDPOINT,
            bucket=config.OSS_BUCKET,
        )
    raise ValueError(f"Unsupported managed storage backend: {backend}")


def default_storage_namespace(backend: str | None = None) -> str:
    backend = _normalize_backend(backend)
    if backend == "minio":
        return config.MINIO_BUCKET
    if backend == "oss":
        return config.OSS_BUCKET
    return ""


# Backward-compatible handle for legacy call sites that expect one active backend.
storage = get_storage_backend()


def is_managed_storage_backend(backend: str | None = None) -> bool:
    return _normalize_backend(backend) in MANAGED_STORAGE_BACKENDS


async def file_object_url(object_key, expires=24, backend: str | None = None):
    return await get_storage_backend(backend).get_presigned_url(
        object_key,
        expires=expires,
    )


async def file_local_url(object_key, expires=24, backend: str | None = None):
    backend = _normalize_backend(backend)
    url = await file_object_url(object_key, expires=expires, backend=backend)
    if backend == "minio":
        return url.replace(f"http://{config.MINIO_ENDPOINT}", config.MINIO_PROXY_PATH)
    return url


async def upload_file(
    object_key,
    file: str | BinaryIO,
    content_type="application/octet-stream",
    length=-1,
    backend: str | None = None,
):
    return await get_storage_backend(backend).upload_file(
        object_key=object_key,
        file=file,
        content_type=content_type,
        length=length,
    )


async def download_file(object_key: str, file_path: str, backend: str | None = None):
    return await get_storage_backend(backend).download_file(object_key, file_path)


async def get_file_content(object_key: str, backend: str | None = None) -> bytes:
    return await get_storage_backend(backend).get_file_content(object_key)


async def get_file_with_stream(object_key: str, backend: str | None = None):
    async for chunk in get_storage_backend(backend).get_file_with_stream(object_key):
        yield chunk


async def copy_file(
    source_key: str,
    destination_key: str,
    backend: str | None = None,
):
    return await get_storage_backend(backend).copy_file(source_key, destination_key)


async def delete_file(object_key, backend: str | None = None):
    await get_storage_backend(backend).delete_file(object_key)


async def object_exists(object_key: str, backend: str | None = None):
    return await get_storage_backend(backend).object_exists(object_key)


async def list_dir(prefix: str, recursive: bool = False, backend: str | None = None):
    return await get_storage_backend(backend).list_dir(prefix, recursive)


async def stat_object(object_key: str, backend: str | None = None):
    return await get_storage_backend(backend).stat_object(object_key)
