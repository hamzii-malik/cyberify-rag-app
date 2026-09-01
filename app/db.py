"""The only file that opens database connections."""

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from app.config import DSN

# Opened once when the app starts, shared by every request.
pool = ConnectionPool(DSN, min_size=1, max_size=8, open=True, kwargs={"row_factory": dict_row})


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and hand back plain dictionaries."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def execute(sql: str, params: tuple = ()) -> dict | None:
    """Run an INSERT / UPDATE / DELETE. Returns the RETURNING row if there is one."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return None
            row = cur.fetchone()
            return row
