from datetime import timedelta
from typing import Any, AsyncGenerator, BinaryIO

import aiohttp
from miniopy_async import Minio
from miniopy_async.commonconfig import CopySource
from miniopy_async.error import S3Error

from .base import StorageBackend


class MinioStorage(StorageBackend):
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ):
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket = bucket

    async def get_presigned_url(self, object_key: str, expires: int = 24) -> str:
        return await self.client.get_presigned_url(
            "GET",
            self.bucket,
            object_key,
            expires=timedelta(hours=expires),
        )

    async def upload_file(
        self,
        object_key: str,
        file: str | BinaryIO,
        content_type: str = "application/octet-stream",
        length: int = -1,
    ) -> Any:
        if isinstance(file, str):
            return await self.client.fput_object(
                bucket_name=self.bucket,
                object_name=object_key,
                file_path=file,
                content_type=content_type,
            )
        else:
            return await self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_key,
                data=file,
                length=length,
                content_type=content_type,
            )

    async def download_file(self, object_key: str, file_path: str) -> Any:
        return await self.client.fget_object(self.bucket, object_key, file_path)

    async def get_file_content(self, object_key: str) -> bytes:
        response = await self.client.get_object(self.bucket, object_key, session=None)
        return response.read()

    async def get_file_with_stream(
        self, object_key: str
    ) -> AsyncGenerator[bytes, None]:
        async with aiohttp.ClientSession() as session:
            response = await self.client.get_object(self.bucket, object_key, session)
            async for chunk in response.content.iter_chunked(1024):
                yield chunk

    async def copy_file(self, source_key: str, destination_key: str) -> Any:
        return await self.client.copy_object(
            self.bucket,
            destination_key,
            CopySource(self.bucket, source_key),
        )

    async def delete_file(self, object_key: str) -> None:
        await self.client.remove_object(
            bucket_name=self.bucket,
            object_name=object_key,
        )

    async def object_exists(self, object_key: str) -> bool:
        try:
            await self.client.stat_object(self.bucket, object_key)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            else:
                raise

    async def list_dir(self, prefix: str, recursive: bool = False) -> Any:
        return await self.client.list_objects(
            bucket_name=self.bucket,
            prefix=prefix,
            recursive=recursive,
        )

    async def stat_object(self, object_key: str) -> Any:
        return await self.client.stat_object(self.bucket, object_key)
