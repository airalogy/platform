import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.routers import instrument_packages as routes
from app.services.instrument_package_matching import (
    AdapterMatchRequest,
    AdapterTargetProfile,
    compare_package,
)
from fastapi import HTTPException
from pydantic import ValidationError


def fixture():
    combination = {
        "manufacturer": "Synthetic",
        "model": "Reader",
        "firmware": "F1",
        "application": "Reader App",
        "application_version": "2.0",
        "os": "test-os",
        "architecture": "arm64",
    }
    manifest = {
        "compatibility": {
            "declared": [combination],
            "gateway_versions": ["0.1.0"],
            "python_versions": ["3.12"],
            "tested": [
                {
                    "combination_index": 0,
                    "reference": "Package-supplied claim",
                    "simulation_only": False,
                }
            ],
        }
    }
    profile = AdapterTargetProfile(
        **combination, gateway_version="0.1.0", python_version="3.12"
    )
    return manifest, profile


def test_exact_declarations_never_become_qualification_or_installation_authority():
    manifest, profile = fixture()
    original = deepcopy(manifest)
    result = compare_package(manifest, profile)
    assert result["status"] == "declaration_match"
    assert not result["hardware_authorized"]
    assert not result["installation_authorized"]
    assert not result["qualification_checked"]
    assert len(result["combinations"][0]["checks"]) == 9
    assert all(
        item["status"] == "matches" for item in result["combinations"][0]["checks"]
    )
    assert (
        result["combinations"][0]["test_declarations"]
        == manifest["compatibility"]["tested"]
    )
    assert manifest == original


def test_unknown_target_and_broad_declarations_require_review_not_wildcards():
    manifest, profile = fixture()
    incomplete = AdapterTargetProfile(manufacturer=" Synthetic ", model="Reader")
    result = compare_package(manifest, incomplete)
    assert result["status"] == "needs_information"
    assert (
        sum(
            item["status"] == "not_supplied"
            for item in result["combinations"][0]["checks"]
        )
        == 7
    )
    for word in ("*", "any", "UNKNOWN", "unspecified", "all"):
        manifest["compatibility"]["declared"][0]["architecture"] = word
        result = compare_package(manifest, profile)
        assert result["status"] == "needs_information"
        assert (
            next(
                item
                for item in result["combinations"][0]["checks"]
                if item["field"] == "architecture"
            )["status"]
            == "unresolved_declaration"
        )


def test_matching_does_not_mix_combinations_or_infer_version_ranges():
    manifest, profile = fixture()
    original = deepcopy(manifest["compatibility"]["declared"][0])
    manifest["compatibility"]["declared"] = [
        {**original, "firmware": "F2"},
        {**original, "application_version": "3.0"},
    ]
    result = compare_package(manifest, profile)
    assert result["status"] == "conflicts"
    assert all(item["status"] == "conflicts" for item in result["combinations"])
    manifest["compatibility"]["declared"].append(original)
    result = compare_package(manifest, profile)
    assert result["status"] == "declaration_match"
    assert result["combinations"][2]["test_declarations"] == []
    for field, value in (("application_version", ">=2.0"), ("model", "reader")):
        changed = deepcopy(manifest)
        changed["compatibility"]["declared"] = [{**original, field: value}]
        assert compare_package(changed, profile)["status"] != "declaration_match"


def test_runtime_versions_and_equipment_family_are_literal():
    manifest, profile = fixture()
    for change in ({"gateway_version": "0.1.1"}, {"python_version": "3.13"}):
        assert (
            compare_package(manifest, profile.model_copy(update=change))["status"]
            == "conflicts"
        )
    manifest["compatibility"]["declared"] = [
        {**manifest["compatibility"]["declared"][0], "model": "Other"},
        {**manifest["compatibility"]["declared"][0], "manufacturer": "Other"},
    ]
    assert compare_package(manifest, profile)["combinations"] == []


def test_outer_unicode_spaces_are_consistent_without_changing_inner_model_names():
    manifest, profile = fixture()
    declaration = manifest["compatibility"]["declared"][0]
    declaration["manufacturer"] = "\u00a0Synthetic\u3000"
    target = AdapterTargetProfile(
        **{**profile.model_dump(), "manufacturer": "\ufeffSynthetic\u2007"}
    )
    assert compare_package(manifest, target)["status"] == "declaration_match"
    declaration["model"] = "Read er"
    assert compare_package(manifest, target)["status"] == "no_declared_model"


@pytest.mark.parametrize(
    "change",
    [
        {"model": ""},
        {"manufacturer": None},
        {"model": "*"},
        {"firmware": "unknown"},
        {"application": "x\ny"},
        {"model": " " * 300 + "Reader"},
        {"model": 123},
        {"gateway_version": "0.1"},
        {"python_version": "3.12.1"},
        {"hardware_authorized": True},
    ],
)
def test_target_input_is_bounded_and_cannot_grant_authority(change):
    with pytest.raises(ValidationError):
        AdapterTargetProfile(
            **{"manufacturer": "Synthetic", "model": "Reader", **change}
        )


def test_request_and_read_permission_are_checked_before_catalogue_query(monkeypatch):
    _manifest, profile = fixture()
    for change in ({"include_revoked": "true"}, {"hardware_authorized": True}):
        with pytest.raises(ValidationError):
            AdapterMatchRequest(profile=profile, **change)
    db = SimpleNamespace(scalars=AsyncMock())
    monkeypatch.setattr(
        routes, "_authorize", AsyncMock(side_effect=HTTPException(403, "Denied"))
    )
    with pytest.raises(HTTPException):
        asyncio.run(
            routes.match_packages(
                uuid4(),
                AdapterMatchRequest(profile=profile),
                object(),
                db,
                offset=0,
                limit=10,
            )
        )
    db.scalars.assert_not_awaited()
