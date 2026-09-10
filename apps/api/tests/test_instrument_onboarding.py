import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.routers import instrument_installations as installations
from app.routers import instrument_integrations as integrations
from app.routers import research_instrument_gateways as gateways


def sql(statement):
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_equipment_search_scopes_and_filters_before_pagination():
    lab, resource = uuid4(), uuid4()
    statement = (
        gateways.equipment_options_query(lab, q="100%_!", resource_id=resource)
        .offset(30)
        .limit(31)
    )
    compiled = sql(statement)
    assert str(lab) in compiled and str(resource) in compiled
    assert "resources.archived_at IS NULL" in compiled
    assert "resources.status = 'active'" in compiled
    assert "current_revision_id = resource_revisions.id" in compiled
    assert "booking" in compiled and "IS true" in compiled
    assert "ESCAPE '!'" in compiled
    assert "%100!%!_!!%" in statement.compile().params.values()
    assert compiled.index("resources.lab_id =") < compiled.index("LIMIT 31")


def test_equipment_options_check_each_item_and_expose_only_identity(monkeypatch):
    gateway = SimpleNamespace(id=uuid4(), lab_id=uuid4())
    user = SimpleNamespace(id=uuid4())
    rows = [
        SimpleNamespace(id=uuid4(), name="Fixture", code="R", private="secret")
        for _ in range(3)
    ]
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: rows))
    )
    managed = AsyncMock(return_value=gateway)
    access = AsyncMock(side_effect=[(rows[0], None), HTTPException(403, "denied")])
    monkeypatch.setattr(gateways, "_gateway_context", managed)
    monkeypatch.setattr(gateways, "_equipment_context", access)
    result = asyncio.run(
        gateways.equipment_options(
            gateway.id, user, db, q="", resource_id=None, offset=0, limit=2
        )
    )
    assert result == {
        "items": [{"id": str(rows[0].id), "name": "Fixture", "code": "R"}],
        "has_more": True,
        "next_offset": 2,
    }
    managed.assert_awaited_once_with(db, user, gateway.id, lock=False)
    assert access.await_count == 2


@pytest.mark.parametrize("route", ["installations", "integrations"])
def test_selected_equipment_filter_is_applied_before_history_limit(monkeypatch, route):
    module = installations if route == "installations" else integrations
    gateway = SimpleNamespace(id=uuid4(), lab_id=uuid4())
    resource = SimpleNamespace(
        id=uuid4(),
        lab_id=gateway.lab_id,
        resource_type_id=uuid4(),
        status="retired",
        archived_at=True,
    )
    user = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(
        get=AsyncMock(return_value=resource),
        scalars=AsyncMock(return_value=SimpleNamespace(all=list)),
    )
    monkeypatch.setattr(module, "_gateway_context", AsyncMock(return_value=gateway))
    monkeypatch.setattr(
        installations,
        "resolve_resource_access",
        AsyncMock(return_value=SimpleNamespace(allows=lambda _: True)),
    )
    monkeypatch.setattr(integrations, "_equipment_context", AsyncMock())
    if route == "installations":
        result = asyncio.run(
            module.list_installations(
                user, db, gateway.id, limit=30, offset=0, resource_id=resource.id
            )
        )
    else:
        result = asyncio.run(
            module.list_integrations(gateway.id, user, db, resource_id=resource.id)
        )
    assert result["items"] == []
    compiled = sql(db.scalars.call_args.args[0])
    assert str(gateway.id) in compiled and str(resource.id) in compiled
    assert compiled.index("resource_id =") < compiled.index("LIMIT")
    if route == "installations":
        assert "archived_at" not in compiled and "status =" not in compiled


@pytest.mark.parametrize("failure", ["foreign_lab", "denied"])
def test_installation_scope_denied_before_history_lookup(monkeypatch, failure):
    gateway = SimpleNamespace(id=uuid4(), lab_id=uuid4())
    resource = SimpleNamespace(
        id=uuid4(),
        lab_id=uuid4() if failure == "foreign_lab" else gateway.lab_id,
        resource_type_id=uuid4(),
    )
    db = SimpleNamespace(get=AsyncMock(return_value=resource), scalars=AsyncMock())
    monkeypatch.setattr(
        installations, "_gateway_context", AsyncMock(return_value=gateway)
    )
    monkeypatch.setattr(
        installations,
        "resolve_resource_access",
        AsyncMock(return_value=SimpleNamespace(allows=lambda _: False)),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            installations.list_installations(
                SimpleNamespace(id=uuid4()),
                db,
                gateway.id,
                limit=30,
                offset=0,
                resource_id=resource.id,
            )
        )
    assert error.value.status_code == (404 if failure == "foreign_lab" else 403)
    db.scalars.assert_not_awaited()
