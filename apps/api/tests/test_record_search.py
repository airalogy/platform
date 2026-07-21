from sqlalchemy.dialects import postgresql

from app.routers.records import build_record_keyword_condition, escape_like_pattern


def compile_condition(q: str) -> str:
    condition = build_record_keyword_condition(q)
    assert condition is not None
    return str(
        condition.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_record_keyword_condition_ignores_empty_queries():
    assert build_record_keyword_condition(None) is None
    assert build_record_keyword_condition(" \n\t ") is None


def test_record_keyword_condition_supports_chinese_and_multiple_terms():
    sql = compile_condition("心身调理 177")

    assert "ILIKE" in sql
    assert "心身调理" in sql
    assert "177" in sql
    assert " AND " in sql


def test_record_keyword_condition_escapes_like_wildcards():
    keyword = r"100%_value\path"
    sql = compile_condition(keyword)

    assert escape_like_pattern(keyword) == r"100\%\_value\\path"
    assert r"100\\%%" in sql
    assert r"\\_value" in sql
