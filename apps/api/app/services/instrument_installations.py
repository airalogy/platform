"""Cross-route installation lock: approval does not permit concurrent execution."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, or_, select

from app.models.instrument_installation import InstrumentDeviceBinding


def managed_instrument_scope(gateway_id, resource_id=None):
    """Claimed installations opt equipment into managed execution permanently.

    Revoking an already claimed grant must not restore the manual-command back door.
    Resource scope prevents switching to another Gateway to evade qualification.
    Never delete binding history to re-enable equipment.
    """
    conditions = [InstrumentDeviceBinding.gateway_id == gateway_id]
    if resource_id is not None:
        conditions.append(InstrumentDeviceBinding.resource_id == resource_id)
    return (
        select(InstrumentDeviceBinding.id)
        .where(
            or_(*conditions),
            or_(
                InstrumentDeviceBinding.started_at.is_not(None),
                InstrumentDeviceBinding.state.in_(["installing", "installed"]),
                and_(
                    InstrumentDeviceBinding.state == "authorized",
                    InstrumentDeviceBinding.expires_at > datetime.now(UTC),
                ),
            ),
        )
        .exists()
    )


async def managed_execution_block_reason(db, gateway_id, resource_id=None):
    if await db.scalar(select(managed_instrument_scope(gateway_id, resource_id))):
        # The qualified active-version runtime is a separate lifecycle stage.
        # Until it exists, an installation receipt cannot enable physical jobs.
        return "Managed instrument qualification and active-version authorization are required"
    return None


async def assert_manual_execution_allowed(db, gateway_id, resource_id=None):
    reason = await managed_execution_block_reason(db, gateway_id, resource_id)
    if reason:
        raise HTTPException(409, reason)


async def assert_no_pending_installation(db, gateway_id):
    pending = await db.scalar(
        select(InstrumentDeviceBinding.id)
        .where(
            InstrumentDeviceBinding.gateway_id == gateway_id,
            or_(
                InstrumentDeviceBinding.state == "installing",
                and_(
                    InstrumentDeviceBinding.state == "authorized",
                    InstrumentDeviceBinding.expires_at > datetime.now(UTC),
                ),
            ),
        )
        .limit(1)
    )
    if pending:
        raise HTTPException(
            409,
            "Finish or explicitly revoke the pending installation before changing Gateway execution or identity",
        )
