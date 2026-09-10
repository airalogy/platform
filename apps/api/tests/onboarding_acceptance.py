"""Real API/SQL scope and pagination acceptance; bulk fixtures are synthetic data."""

from uuid import UUID, uuid4

import httpx

from app.database import sessionmanager
from app.main import app
from app.models.resource import Resource, ResourceRevision


def exercise_onboarding_scope(runtime):
    async def exercise():
        lab = runtime.seed["lab"]["id"]
        base = f"/labs/{lab}/resource-library"
        definitions = await runtime.json("GET", base + "/definition-versions")
        definition = next(
            item
            for item in definitions["items"]
            if item["protocol_uid"] == "plasmid_resource_definition_en"
        )
        prefix = "workspace-" + uuid4().hex
        templates = []
        for booking in (False, True):
            kind = await runtime.json(
                "POST",
                base + "/types",
                {
                    "protocol_version_id": definition["id"],
                    "code": prefix + str(booking),
                    "name": "Synthetic pagination fixture",
                    "capabilities": {"booking": booking},
                    "booking_policy": "auto" if booking else "none",
                },
            )
            templates.append(
                await runtime.json(
                    "POST",
                    base + "/resources",
                    {
                        "resource_type_id": kind["id"],
                        "name": prefix + str(booking),
                        "code": uuid4().hex,
                        "visibility": "lab",
                        "data": {
                            "construct_name": "Synthetic",
                            "features": [],
                            **dict.fromkeys(
                                [
                                    "aliases",
                                    "backbone",
                                    "sequence",
                                    "sequence_file",
                                    "resistance_markers",
                                    "host_species",
                                    "copy_number",
                                    "external_source",
                                ]
                            ),
                        },
                    },
                )
            )
        gateway = (
            await runtime.confirm(
                "/research-instrument-gateways",
                {"lab_id": lab, "name": prefix, "enabled": False},
            )
        )["gateway"]
        # Seed enough genuine rows to cross the previous generic-resource limit.
        # Each clone has its own current revision; APIs and permission checks are not mocked.
        equipment = []
        async with sessionmanager.session() as db:
            for index, count in ((0, 101), (1, 32)):
                source = await db.get(Resource, UUID(templates[index]["id"]))
                revision = await db.get(ResourceRevision, source.current_revision_id)
                for n in range(count):
                    row = Resource(
                        id=uuid4(),
                        lab_id=source.lab_id,
                        resource_type_id=source.resource_type_id,
                        name=f"{prefix}-{index}-{n:03}",
                        code=uuid4().hex,
                        visibility="lab",
                        created_by_user_id=source.created_by_user_id,
                    )
                    db.add(row)
                    await db.flush()
                    current = ResourceRevision(
                        id=uuid4(),
                        resource_id=row.id,
                        resource_type_revision_id=revision.resource_type_revision_id,
                        revision=1,
                        data=revision.data,
                        created_by_user_id=source.created_by_user_id,
                    )
                    db.add(current)
                    await db.flush()
                    row.current_revision_id = current.id
                    if index == 1:
                        equipment.append(str(row.id))
            await db.commit()
        url = f"/research-instrument-gateways/{gateway['id']}/equipment-options"
        first = await runtime.json("GET", url + f"?q={prefix}&limit=30")
        assert len(first["items"]) == 30 and first["has_more"]
        second = await runtime.json(
            "GET", url + f"?q={prefix}&offset={first['next_offset']}&limit=30"
        )
        assert len(second["items"]) == 3 and not second["has_more"]
        ids = {item["id"] for item in first["items"] + second["items"]}
        assert ids == {*equipment, templates[1]["id"]}
        assert all(set(item) == {"id", "name", "code"} for item in first["items"])
        exact = await runtime.json("GET", url + f"?resource_id={equipment[-1]}")
        assert [item["id"] for item in exact["items"]] == [equipment[-1]]
        assert (await runtime.json("GET", url + "?q=%25"))["items"] == []
        for excluded in (templates[0]["id"], str(uuid4())):
            assert (await runtime.json("GET", url + f"?resource_id={excluded}"))[
                "items"
            ] == []
        async with sessionmanager.session() as db:
            row = await db.get(Resource, UUID(equipment[-1]))
            row.status = "retired"
            await db.commit()
        assert (await runtime.json("GET", url + f"?resource_id={equipment[-1]}"))[
            "items"
        ] == []
        await runtime.json("GET", url + "?limit=101", status=422)
        await runtime.json("GET", url + "?offset=-1", status=422)
        # A normal member and an anonymous caller cannot use this management surface.
        viewer = next(
            item for item in runtime.seed["accounts"] if item["key"] == "viewer"
        )
        auth = await runtime.json(
            "POST",
            "/signin_by_email",
            {"email": viewer["email"], "password": viewer["password"]},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            denied = await client.get(url, headers={"Auth-Token": auth["token"]})
            assert denied.status_code == 403, denied.text
            assert (await client.get(url)).status_code in {401, 403}
        assert (
            await runtime.json(
                "GET", f"/research-instrument-gateways/{gateway['id']}/commands"
            )
        )["items"] == []

    runtime.run(exercise())
