"""Each dataset's view shows only its own projects, so a project in both is never counted twice.

CAISO's own file and Berkeley Lab's national file both list CAISO projects. Every analysis
reads a per-dataset view; a query that forgot ``WHERE source = ...`` can't double-count,
because the filter is built into the view (decision 0001).
"""

import psycopg

Conn = psycopg.Connection[tuple[object, ...]]


def test_each_dataset_view_shows_only_its_own_copy_of_a_shared_project(conn: Conn) -> None:
    for source in ("caiso_raw", "lbnl"):
        conn.execute(
            "INSERT INTO projects (source, native_id, status, iso) VALUES (%s, 'SHARED-1', "
            "'Active', 'CAISO')",
            (source,),
        )
    counts = [
        conn.execute(f"SELECT count(*) FROM {view} WHERE native_id = 'SHARED-1'").fetchone()
        for view in ("projects", "caiso_projects", "lbnl_projects")
    ]
    assert counts == [(2,), (1,), (1,)]
