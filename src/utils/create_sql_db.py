"""
Load the store CSVs into PostgreSQL and set up the SQL agent's read-only role.

Run with:  python -m src.utils.create_sql_db

Re-running is safe: schema.sql drops and recreates every table.
"""
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql

from src.config import get_settings

DATA_PATH = Path(__file__).resolve().parents[2] / "data"
SCHEMA_PATH = Path(__file__).resolve().parent / "sql" / "schema.sql"
CSV_PREFIX = "desafio_tecnico_ai_eng - "

# Parents before children, so foreign keys resolve.
TABLES = ["categories", "customers", "products", "orders", "order_items", "promotions"]

# The only customers columns the SQL agent's role may read. Names, phones and
# e-mails are not granted, so no prompt injection can make the agent return them.
READER_CUSTOMER_COLUMNS = ("customer_id", "city")


def read_table(table: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH / f"{CSV_PREFIX}{table}.csv", encoding="utf-8")
    if table == "promotions":
        df["is_active"] = df["is_active"].astype(bool)
    # NaN -> None so empty CSV cells become SQL NULL.
    return df.astype(object).where(df.notna(), None)


def setup_reader_role(conn: psycopg.Connection, user: str, password: str) -> None:
    """Create/refresh the read-only role: SELECT on every table, except the
    customers' personal data columns."""
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,)).fetchone()
    action = "ALTER" if exists else "CREATE"
    conn.execute(sql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(
        sql.SQL(action), sql.Identifier(user), sql.Literal(password)))
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(user)))
    conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(user)))
    conn.execute(sql.SQL("REVOKE SELECT ON customers FROM {}").format(sql.Identifier(user)))
    conn.execute(sql.SQL("GRANT SELECT ({}) ON customers TO {}").format(
        sql.SQL(", ").join(map(sql.Identifier, READER_CUSTOMER_COLUMNS)), sql.Identifier(user)))


def create_sql_db() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

        for table in TABLES:
            df = read_table(table)
            columns = ", ".join(df.columns)
            placeholders = ", ".join(["%s"] * len(df.columns))
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                    df.itertuples(index=False, name=None),
                )
            print(f"{table}: {len(df)} rows")

        setup_reader_role(conn, settings.database_reader_user, settings.database_reader_password)
        print(f"Read-only role '{settings.database_reader_user}' ready.")
    # Leaving the `with` block commits the transaction.
    print("PostgreSQL store database loaded.")


if __name__ == "__main__":
    create_sql_db()
