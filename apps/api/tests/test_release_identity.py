from pathlib import Path

from app.routers import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_runtime_version_endpoint_is_publicly_registered():
    paths = {route.path for route in app.routes}
    assert "/system/version" in paths


def test_release_workflow_builds_the_complete_component_set():
    workflow = (REPOSITORY_ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )

    assert 'tags:\n      - "v*.*.*"' in workflow
    for component in ("api", "web", "protocol-executor", "postgres"):
        assert f"- component: {component}" in workflow
    for package, job_name in (
        ("instrument-gateway", "gateway-package"),
        ("compute-runner", "compute-runner-package"),
    ):
        assert f"{job_name}:" in workflow
        assert f"uv --directory apps/{package} lock --check" in workflow
        assert f"uv --directory apps/{package} build" in workflow
        assert f"{package}-package/*" in workflow
    assert "release-manifest.json" in workflow
    assert "attest-build-provenance" in workflow


def test_single_lab_release_identity_is_versioned_and_not_customer_named():
    environment = (
        REPOSITORY_ROOT / "deploy/single-lab/.env.example"
    ).read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "deploy/single-lab/compose.yml").read_text(
        encoding="utf-8"
    )
    support_script = (
        REPOSITORY_ROOT / "deploy/single-lab/scripts/support-bundle.sh"
    ).read_text(encoding="utf-8")

    assert "PLATFORM_VERSION=0.1.0" in environment
    assert "AIRALOGY_DEPLOYMENT_ID=dep_00000000000000000000000000000000" in environment
    assert "AIRALOGY_RELEASE_METADATA_REQUIRED=false" in environment
    assert "AIRALOGY_PROTOCOL_EXECUTOR_IMAGE" in compose
    assert "release-identity" in support_script
    assert '"image_id"' in support_script
    assert '"image"' not in support_script
    for excluded in (".env", "logs", "database contents", "customer names"):
        assert excluded in support_script
