from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, BinaryIO


class StorageBackend(ABC):
    """存储后端的抽象基类"""

    @abstractmethod
    async def get_presigned_url(self, object_key: str, expires: int = 24) -> str:
        """获取预签名URL"""
        pass

    @abstractmethod
    async def upload_file(
        self,
        object_key: str,
        file: str | BinaryIO,
        content_type: str = "application/octet-stream",
        length: int = -1,
    ) -> Any:
        """上传文件"""
        pass

    @abstractmethod
    async def download_file(self, object_key: str, file_path: str) -> Any:
        """下载文件到本地"""
        pass

    @abstractmethod
    async def get_file_content(self, object_key: str) -> bytes:
        """获取文件内容"""
        pass

    @abstractmethod
    async def get_file_with_stream(
        self, object_key: str
    ) -> AsyncGenerator[bytes, None]:
        """获取文件流"""
        pass

    @abstractmethod
    async def copy_file(self, source_key: str, destination_key: str) -> Any:
        """复制文件"""
        pass

    @abstractmethod
    async def delete_file(self, object_key: str) -> None:
        """删除文件"""
        pass

    @abstractmethod
    async def object_exists(self, object_key: str) -> bool:
        """检查文件是否存在"""
        pass

    @abstractmethod
    async def list_dir(self, prefix: str, recursive: bool = False) -> Any:
        """列出目录内容"""
        pass

    @abstractmethod
    async def stat_object(self, object_key: str) -> Any:
        """获取文件元信息"""
        pass
