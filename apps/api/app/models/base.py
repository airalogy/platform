from typing import Any, Self
from uuid import UUID

from sqlalchemy import ColumnElement, exists, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    __abstract__ = True

    json_exclude_fields: list[str] | None = None
    json_include_fields: list[str] | None = None
    json_computed_fields: list[str] | None = None

    def __iter__(self):
        columns = self.__table__.columns.keys()
        for key in columns:
            if not self.json_exclude_fields or key not in self.json_exclude_fields:
                yield key, getattr(self, key)

        if self.json_include_fields:
            for key in self.json_include_fields:
                yield key, getattr(self, key)
        if self.json_computed_fields:
            for method in self.json_computed_fields:
                yield method, getattr(self, method)()

    def as_dict(
        self,
        excludes: list[str] | None = None,
        computed: list[str] | None = None,
        includes: list[str] | None = None,
        only: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        excludes = excludes if excludes else self.json_exclude_fields
        computed = computed if computed else self.json_computed_fields
        includes = includes if includes else self.json_include_fields
        columns = self.__table__.columns.keys()
        data = {}
        if only:
            if includes:
                includes = [key for key in includes if key in only]
            if computed:
                computed = [method for method in computed if method in only]
        for key in columns:
            if excludes and key in excludes:
                continue
            if only and key not in only:
                continue
            data[key] = getattr(self, key)

        if includes:
            for key in includes:
                data[key] = getattr(self, key)
        if computed:
            for method in computed:
                data[method] = getattr(self, method)()

        if kwargs:
            data.update(kwargs)

        return data

    @classmethod
    def default_find_scope(cls) -> list[Any] | None:
        return None

    @classmethod
    async def find(
        cls,
        db_session: AsyncSession,
        id: int | str | UUID,
        options=None,
        with_for_update: bool = False,
        skip_default_scope: bool = False,
    ) -> Self:
        _stmt = select(cls).where(cls.id == id)
        default_find_scope = cls.default_find_scope()
        if default_find_scope and not skip_default_scope:
            _stmt = _stmt.where(*default_find_scope)
        if options:
            _stmt = _stmt.options(options)
        if with_for_update:
            _stmt = _stmt.with_for_update()
        _result = await db_session.execute(_stmt)
        return _result.scalars().one()

    @classmethod
    async def find_by(
        cls,
        db_session: AsyncSession,
        where_conditions: list[Any],
        options=None,
        with_for_update: bool = False,
    ) -> Self | None:
        _stmt = select(cls).where(*where_conditions).order_by(cls.id.asc()).limit(1)
        if options:
            _stmt = _stmt.options(options)
        if with_for_update:
            _stmt = _stmt.with_for_update()
        _result = await db_session.execute(_stmt)
        return _result.scalar()

    @classmethod
    def conditions_from_dict(cls, parmas: dict) -> list[ColumnElement[bool]]:
        columns = cls.__table__.columns.keys()
        conditions = []
        for k, v in parmas.items():
            if k in columns:
                conditions.append(getattr(cls, k) == v)
        return conditions

    @classmethod
    async def count(cls, db_session: AsyncSession, where_conditions: list[Any]) -> int:
        _stmt = select(func.count()).select_from(cls).where(*where_conditions)
        _result = await db_session.execute(_stmt)
        return _result.scalar() or 0

    @classmethod
    async def exists(
        cls, db_session: AsyncSession, where_conditions: list[Any]
    ) -> bool:
        _stmt = select(exists().where(*where_conditions))
        _result = await db_session.execute(_stmt)
        return _result.scalar() or False

    @classmethod
    async def all(
        cls,
        db_session: AsyncSession,
        where_conditions: list[Any],
        page: int = 1,
        page_size: int = 10,
        *,
        options=None,
        order_by=None,
    ) -> list[Self]:
        if order_by is None:
            order_by = [cls.id.desc()]
        elif type(order_by) is not list:
            order_by = [order_by]
        _stmt = (
            select(cls)
            .where(*where_conditions)
            .order_by(*order_by)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        if options:
            _stmt = _stmt.options(options)
        _result = await db_session.execute(_stmt)
        return _result.scalars().all()

    @classmethod
    async def create(cls, db_session: AsyncSession, **kwargs):
        insert_stmt = insert(cls).values(kwargs).returning(cls)
        return (await db_session.execute(insert_stmt)).scalars().first()

    async def save(self, db_session: AsyncSession):
        db_session.add(self)
        return await db_session.commit()

    async def delete(self, db_session: AsyncSession):
        await db_session.delete(self)
        await db_session.commit()
        return True

    async def update(self, db: AsyncSession, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        return await db.commit()

    def set_attrs(self, **kwargs):
        for k, v in kwargs.items():
            if getattr(self, k) != v:
                setattr(self, k, v)
        return self

    @classmethod
    async def count_with_join(
        cls, db_session: AsyncSession, join_model, where_conditions: list[Any]
    ) -> int:
        """Count records with a join table"""
        _stmt = (
            select(func.count(cls.id.distinct()))
            .select_from(cls)
            .join(join_model)
            .where(*where_conditions)
        )
        _result = await db_session.execute(_stmt)
        return _result.scalar() or 0
