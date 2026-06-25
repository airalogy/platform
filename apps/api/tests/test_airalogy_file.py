import uuid

from app.models.airalogy_file import AiralogyFile
from app.routers.airalogy_files import _normalize_airalogy_file_id


def _file(**kwargs) -> AiralogyFile:
    data = {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "filename": "result.csv",
        "protocol_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "project_id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "user_id": uuid.UUID("00000000-0000-0000-0000-000000000004"),
    }
    data.update(kwargs)
    return AiralogyFile(**data)


def test_airalogy_file_id_is_stable_and_parseable():
    file = _file()

    assert file.airalogy_id == (
        "airalogy.id.file.00000000-0000-0000-0000-000000000001.csv"
    )
    assert _normalize_airalogy_file_id(file.airalogy_id) == str(file.id)


def test_managed_storage_location_is_explicit_mapping():
    file = _file()
    file.set_managed_storage_location(
        backend="oss",
        namespace="research-bucket",
        object_key="protocols/custom/files/result.csv",
    )

    assert file.storage_backend == "oss"
    assert file.storage_namespace == "research-bucket"
    assert file.storage_object_key == "protocols/custom/files/result.csv"
    assert file.object_key == "protocols/custom/files/result.csv"
    assert file.external_uri is None


def test_default_object_key_remains_backward_compatible():
    file = _file()

    assert file.storage_object_key is None
    assert file.object_key == (
        "protocols/00000000-0000-0000-0000-000000000002/files/"
        "00000000-0000-0000-0000-000000000001.csv"
    )


def test_external_storage_location_keeps_file_id_independent_from_url():
    file = _file(filename="large-image.tiff")
    file.set_external_storage_location(
        external_uri="https://files.example.org/datasets/large-image.tiff",
        backend="central_http",
        namespace="instrument-data-center",
        metadata={"instrument": "microscope-1"},
    )

    assert file.airalogy_id.endswith(".tiff")
    assert file.is_external_reference is True
    assert file.object_key == file.default_object_key
    assert file.storage_location() == {
        "backend": "central_http",
        "namespace": "instrument-data-center",
        "object_key": None,
        "external_uri": "https://files.example.org/datasets/large-image.tiff",
        "metadata": {"instrument": "microscope-1"},
    }
    assert file.reference_payload(url=file.external_uri)["storage_backend"] == (
        "central_http"
    )
