"""
Read-only access to the store PostgreSQL database for the SQL agent.

"""
import re
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache

import psycopg
from psycopg.conninfo import make_conninfo

from src.config import get_settings

STATEMENT_TIMEOUT_MS = 5000
MAX_ROWS = 50

_SCHEMA_QUERY = """
SELECT c.relname                                   AS table_name,
       obj_description(c.oid, 'pg_class')          AS table_comment,
       a.attname                                   AS column_name,
       format_type(a.atttypid, a.atttypmod)        AS data_type,
       col_description(c.oid, a.attnum)            AS column_comment,
       (SELECT string_agg(
                   CASE con.contype
                       WHEN 'p' THEN 'PK'
                       WHEN 'f' THEN 'FK -> ' || ref.relname
                   END, ', ')
          FROM pg_constraint con
          LEFT JOIN pg_class ref ON ref.oid = con.confrelid
         WHERE con.conrelid = c.oid
           AND con.contype IN ('p', 'f')
           AND a.attnum = ANY (con.conkey))        AS keys
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
 WHERE n.nspname = 'public' AND c.relkind = 'r'
   -- Only what the connected role may read: the agent never sees the
   -- customers' personal data columns (see create_sql_db.setup_reader_role).
   AND has_column_privilege(c.oid, a.attnum, 'SELECT')
 ORDER BY c.relname, a.attnum
"""


class UnsafeQueryError(ValueError):
    """Raised when generated SQL is not a single read-only query."""


def validate_select(sql: str) -> str:
    """Return the query without a trailing ';', or raise UnsafeQueryError."""
    query = sql.strip().rstrip(";").strip()
    if not query:
        raise UnsafeQueryError("Empty query.")
    if ";" in query:
        raise UnsafeQueryError("Only one statement is allowed.")
    if not re.match(r"^(select|with)\b", query, re.IGNORECASE):
        raise UnsafeQueryError("Only SELECT queries are allowed.")
    return query


def _connect_reader() -> psycopg.Connection:
    """Read-only connection as the SELECT-only reader role."""
    settings = get_settings()
    conninfo = make_conninfo(
        settings.database_url,
        user=settings.database_reader_user,
        password=settings.database_reader_password,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
        connect_timeout=5,
    )
    conn = psycopg.connect(conninfo)
    conn.read_only = True
    return conn


@lru_cache(maxsize=1)
def get_schema_description() -> str:
    """Describe tables, columns, keys and comments, for the agent's prompt."""
    with _connect_reader() as conn:
        rows = conn.execute(_SCHEMA_QUERY).fetchall()

    lines, current = [], None
    for table, table_comment, column, data_type, column_comment, keys in rows:
        if table != current:
            current = table
            lines.append(f"\nTABLE {table}" + (f"  -- {table_comment}" if table_comment else ""))
        line = f"  {column} {data_type}"
        if keys:
            line += f" [{keys}]"
        if column_comment:
            line += f"  -- {column_comment}"
        lines.append(line)
    return "\n".join(lines).strip()


def _to_json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def run_readonly_query(sql: str, max_rows: int = MAX_ROWS) -> dict:
    """
    Run a validated SELECT and return
    {"sql", "columns", "rows" (list of dicts), "truncated"}.
    """
    query = validate_select(sql)
    with _connect_reader() as conn:
        cur = conn.execute(query)
        columns = [col.name for col in cur.description]
        fetched = cur.fetchmany(max_rows + 1)
        conn.rollback()

    rows = [
        {col: _to_json_value(val) for col, val in zip(columns, row, strict=True)}
        for row in fetched[:max_rows]
    ]
    return {
        "sql": query,
        "columns": columns,
        "rows": rows,
        "truncated": len(fetched) > max_rows,
    }
