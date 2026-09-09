"""Cross-route installation lock: approval does not permit concurrent execution."""

from fastapi import HTTPException
from sqlalchemy import and_, or_, select

from app.models.instrument_installation import InstrumentDeviceBinding
from app.services.research_runtime import utcnow


async def assert_no_pending_installation(db, gateway_id):
    pending = await db.scalar(
        select(InstrumentDeviceBinding.id)
        .where(
            InstrumentDeviceBinding.gateway_id == gateway_id,
            or_(
                InstrumentDeviceBinding.state == "installing",
                and_(
                    InstrumentDeviceBinding.state == "authorized",
                    InstrumentDeviceBinding.expires_at > utcnow(),
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
