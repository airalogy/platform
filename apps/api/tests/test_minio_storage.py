import asyncio
from unittest.mock import AsyncMock

from app.libs.storage.minio import MinioStorage


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.released = False

    async def read(self) -> bytes:
        return self.content

    def release(self) -> None:
        self.released = True


def test_get_file_content_awaits_response_and_releases_it(monkeypatch):
    response = FakeResponse(b"archive payload")
    storage = MinioStorage(
        endpoint="minio:9200",
        access_key="test",
        secret_key="test-secret",
        bucket="test-bucket",
    )
    storage.client.get_object = AsyncMock(return_value=response)
    monkeypatch.setattr(
        "app.libs.storage.minio.aiohttp.ClientSession",
        FakeSession,
    )

    content = asyncio.run(storage.get_file_content("records/archive.aira"))

    assert content == b"archive payload"
    assert response.released is True
    storage.client.get_object.assert_awaited_once()
    assert storage.client.get_object.await_args.args[:2] == (
        "test-bucket",
        "records/archive.aira",
    )
    assert isinstance(storage.client.get_object.await_args.args[2], FakeSession)
