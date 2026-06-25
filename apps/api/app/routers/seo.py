from collections.abc import Iterable
from datetime import datetime
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request, Response
from sqlalchemy import and_, select

from app.database import DBSession
from app.models.lab import Lab
from app.models.project import PermissionType, Project, ProjectType
from app.models.protocol import Protocol

router = APIRouter(tags=["seo"])


def get_site_origin(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    host = host.split(",")[0].strip() if host else request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def format_lastmod(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.date().isoformat()


def render_url_entry(loc: str, lastmod: str | None = None) -> str:
    parts = [f"  <url>\n    <loc>{escape(loc)}</loc>"]
    if lastmod:
        parts.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
    parts.append("  </url>")
    return "\n".join(parts)


def render_sitemap(entries: Iterable[tuple[str, str | None]]) -> str:
    body = "\n".join(render_url_entry(loc=loc, lastmod=lastmod) for loc, lastmod in entries)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
        f"{body}\n"
        "</urlset>\n"
    )


@router.get("/sitemap.xml", include_in_schema=False)
async def get_sitemap(request: Request, db_session: DBSession):
    site_origin = get_site_origin(request)
    entries: list[tuple[str, str | None]] = [
        (f"{site_origin}/", None),
        (f"{site_origin}/hub/list", None),
    ]

    project_rows = (
        await db_session.execute(
            select(
                Lab.uid.label("lab_uid"),
                Project.uid.label("project_uid"),
                Project.updated_at.label("updated_at"),
            )
            .select_from(Project)
            .join(Lab, Lab.id == Project.lab_id)
            .where(
                Project.type == ProjectType.PUBLIC,
                Project.deleted_at.is_(None),
            )
            .order_by(Project.updated_at.desc(), Project.id.asc())
        )
    ).all()

    for row in project_rows:
        entries.append(
            (
                f"{site_origin}/labs/{quote(row.lab_uid, safe='')}/projects/{quote(row.project_uid, safe='')}/protocols",
                format_lastmod(row.updated_at),
            )
        )

    protocol_rows = (
        await db_session.execute(
            select(
                Lab.uid.label("lab_uid"),
                Project.uid.label("project_uid"),
                Protocol.uid.label("protocol_uid"),
                Protocol.updated_at.label("updated_at"),
            )
            .select_from(Protocol)
            .join(
                Project,
                and_(
                    Project.id == Protocol.project_id,
                    Project.type == ProjectType.PUBLIC,
                    Project.permission_type == PermissionType.INHERIT,
                    Project.deleted_at.is_(None),
                ),
            )
            .join(Lab, Lab.id == Project.lab_id)
            .where(Protocol.deleted_at.is_(None))
            .order_by(Protocol.updated_at.desc(), Protocol.id.asc())
        )
    ).all()

    for row in protocol_rows:
        entries.append(
            (
                f"{site_origin}/labs/{quote(row.lab_uid, safe='')}/projects/{quote(row.project_uid, safe='')}/protocols/{quote(row.protocol_uid, safe='')}/protocol",
                format_lastmod(row.updated_at),
            )
        )

    return Response(content=render_sitemap(entries), media_type="application/xml")
