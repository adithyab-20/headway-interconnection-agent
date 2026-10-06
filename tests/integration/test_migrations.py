"""Migrations build the whole schema from an empty database, and re-running them is harmless."""

import psycopg

from interconnection_agent.db import connect
from interconnection_agent.migrate import apply_migrations

Conn = psycopg.Connection[tuple[object, ...]]


def _exists(conn: Conn, name: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) IS NOT NULL", (name,)).fetchone()
    return bool(row and row[0])


def test_migrations_build_the_schema_from_empty_and_a_rerun_changes_nothing() -> None:
    with connect() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
        assert not _exists(conn, "projects")

        first = apply_migrations(conn)
        conn.commit()
        assert first, "nothing was applied to an empty database"
        for name in (
            "caiso_projects",
            "lbnl_projects",
            "places",
            "project_places",
            "place_bottlenecks",
            "planned_upgrades",
        ):
            assert _exists(conn, name), f"{name} missing after migration"

        assert apply_migrations(conn) == []
        conn.commit()
