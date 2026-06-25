import asyncio
from datetime import timedelta
from typing import Any, AsyncGenerator, BinaryIO

import alibabacloud_oss_v2 as oss
import alibabacloud_oss_v2.aio as oss_aio

from .base import StorageBackend


class OssStorage(StorageBackend):
    def __init__(self, region: str, endpoint: str, bucket: str):
        credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

        cfg = oss.config.load_default()
        cfg.credentials_provider = credentials_provider
        cfg.region = region
        cfg.endpoint = endpoint
        self.client = oss.Client(cfg)
        self.async_client = oss_aio.AsyncClient(cfg)
        self.bucket = bucket

    async def _run_sync(self, func, *args, **kwargs):
        """将同步操作包装为异步"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def get_presigned_url(self, object_key: str, expires: int = 24) -> str:
        request = oss.GetObjectRequest(
            bucket=self.bucket,
            key=object_key,
        )
        res = await self._run_sync(
            self.client.presign,
            request,
            expires=timedelta(hours=expires),
        )
        return res.url

    async def upload_file(
        self,
        object_key: str,
        file: str | BinaryIO,
        content_type: str = "application/octet-stream",
        length: int = -1,
    ) -> Any:
        if isinstance(file, str):
            """from file path"""
            with open(file, "rb") as f:
                request = oss.PutObjectRequest(
                    bucket=self.bucket,
                    key=object_key,
                    body=f,
                    content_type=content_type,
                )
                return await self.async_client.put_object(request)
        else:
            """from IO bytes"""
            request = oss.PutObjectRequest(
                bucket=self.bucket,
                key=object_key,
                body=file,
                content_type=content_type,
            )
            return await self.async_client.put_object(request)

    async def download_file(self, object_key: str, file_path: str) -> Any:
        request = oss.GetObjectRequest(
            bucket=self.bucket,
            key=object_key,
        )
        result = await self.async_client.get_object(request)
        if result.body is None:
            raise ValueError("Failed to download file: No data received.")
        with open(file_path, "wb") as f:
            data = await result.body.read()
            f.write(data)

    async def get_file_content(self, object_key: str) -> bytes:
        request = oss.GetObjectRequest(
            bucket=self.bucket,
            key=object_key,
        )
        result = await self.async_client.get_object(request)
        return await result.body.read()

    async def get_file_with_stream(
        self, object_key: str
    ) -> AsyncGenerator[bytes, None]:
        request = oss.GetObjectRequest(
            bucket=self.bucket,
            key=object_key,
        )
        result = await self.async_client.get_object(request)
        chunks = await result.body.iter_bytes()
        async for chunk in chunks:
            yield chunk

    async def copy_file(self, source_key: str, destination_key: str) -> Any:
        request = oss.CopyObjectRequest(
            bucket=self.bucket,
            key=destination_key,
            source_bucket=self.bucket,
            source_key=source_key,
        )
        return await self.async_client.copy_object(request)

    async def delete_file(self, object_key: str) -> None:
        request = oss.DeleteObjectRequest(
            bucket=self.bucket,
            key=object_key,
        )
        await self.async_client.delete_object(request)

    async def object_exists(self, object_key: str) -> bool:
        return await self.async_client.is_object_exist(
            bucket=self.bucket, key=object_key
        )

    async def list_dir(self, prefix: str, recursive: bool = False) -> Any:
        """TODO: 需要实现"""
        raise NotImplementedError

    async def stat_object(self, object_key: str) -> Any:
        """TODO: 需要实现"""
        raise NotImplementedError
