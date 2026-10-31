"""
Tests for the SQL agent and its read-only database layer.

The database tests need a loaded PostgreSQL (DATABASE_URL, then
`python -m src.utils.create_sql_db`) and are skipped when it is unreachable.
LLM calls are always mocked here; see test_llm_behavior.py for real-model tests.
"""
import json
import unittest
from unittest.mock import patch

import psycopg

from src.config import get_settings
from src.utils.sql_database import (
    UnsafeQueryError,
    get_schema_description,
    run_readonly_query,
    validate_select,
)


def _database_available() -> bool:
    try:
        settings = get_settings()
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1 FROM products LIMIT 1")
            conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (settings.database_reader_user,))
        return True
    except Exception:
        return False


DB_AVAILABLE = _database_available()
requires_db = unittest.skipUnless(DB_AVAILABLE, "PostgreSQL store database not available")


def llm_reply(payload: dict) -> dict:
    return {"content": json.dumps(payload), "model_used": "mock"}


def rows(sql: str) -> list[dict]:
    return run_readonly_query(sql)["rows"]


class TestValidateSelect(unittest.TestCase):
    def test_accepts_select_and_with(self):
        self.assertEqual(validate_select(" SELECT 1; "), "SELECT 1")
        self.assertEqual(validate_select("with x as (select 1) select * from x"),
                         "with x as (select 1) select * from x")

    def test_rejects_writes_and_multiple_statements(self):
        for sql in ["DELETE FROM orders", "UPDATE products SET price_brl = 0",
                    "DROP TABLE orders", "SELECT 1; DROP TABLE orders",
                    "SET statement_timeout = 0", "", "   ;"]:
            with self.subTest(sql=sql), self.assertRaises(UnsafeQueryError):
                validate_select(sql)


@requires_db
class TestReadOnlyDatabase(unittest.TestCase):
    def test_schema_description_lists_tables_and_comments(self):
        schema = get_schema_description()
        for table in ["categories", "customers", "products", "orders", "order_items", "promotions"]:
            self.assertIn(f"TABLE {table}", schema)
        self.assertIn("FK -> orders", schema)
        self.assertIn("is_active = TRUE", schema)

    def test_join_query_returns_json_friendly_rows(self):
        result = run_readonly_query(
            "SELECT o.order_id, o.order_date, o.total_brl, p.name "
            "FROM orders o JOIN order_items oi USING (order_id) "
            "JOIN products p USING (product_id) WHERE o.order_id = 4"
        )
        self.assertEqual(result["rows"], [{
            "order_id": 4, "order_date": "2025-12-10", "total_brl": 799.9,
            "name": "Giannini GF-3D Dreadnought Sunburst",
        }])
        json.dumps(result)  # must be serializable for logging and synthesis

    def test_writes_are_rejected_by_the_database(self):
        # These get past validate_select (they start with WITH/SELECT), so
        # Postgres itself must refuse them.
        for sql in ["WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
                    "SELECT * FROM query_to_xml('delete from products', false, false, '')"]:
            with self.subTest(sql=sql), self.assertRaises(psycopg.Error):
                run_readonly_query(sql)
        self.assertEqual(rows("SELECT count(*) AS n FROM orders"), [{"n": 20}])
        self.assertEqual(rows("SELECT count(*) AS n FROM products"), [{"n": 65}])

    def test_connects_as_select_only_role(self):
        self.assertEqual(rows("SELECT current_user AS u"),
                         [{"u": get_settings().database_reader_user}])

    def test_rows_are_capped(self):
        result = run_readonly_query("SELECT product_id FROM products", max_rows=10)
        self.assertEqual(len(result["rows"]), 10)
        self.assertTrue(result["truncated"])


@requires_db
class TestSqlAgent(unittest.TestCase):
    @patch("src.agents.sql_agent.llm")
    def test_answers_with_rows(self, mock_llm):
        from src.agents.sql_agent import run_sql_agent
        mock_llm.invoke.return_value = llm_reply(
            {"sql": "SELECT status, tracking_code FROM orders WHERE order_id = 8"})

        result = run_sql_agent("Qual o status do pedido 8?")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rows"], [{"status": "shipped", "tracking_code": "BRJL5544332BR"}])
        system_prompt = mock_llm.invoke.call_args[0][0][0]["content"]
        self.assertIn("TABLE orders", system_prompt)
        self.assertIn("PRIVACY", system_prompt)

    @patch("src.agents.sql_agent.llm")
    def test_catalog_question(self, mock_llm):
        from src.agents.sql_agent import run_sql_agent
        mock_llm.invoke.return_value = llm_reply(
            {"sql": "SELECT price_brl FROM products WHERE name ILIKE '%Yamaha C40%'"})

        result = run_sql_agent("Quanto custa o Yamaha C40?")

        self.assertEqual(result["rows"], [{"price_brl": 599.9}])

    @patch("src.agents.sql_agent.llm")
    def test_retries_once_with_database_error(self, mock_llm):
        from src.agents.sql_agent import run_sql_agent
        mock_llm.invoke.side_effect = [
            llm_reply({"sql": "SELECT price FROM products WHERE product_id = 81"}),
            llm_reply({"sql": "SELECT price_brl FROM products WHERE product_id = 81"}),
        ]

        result = run_sql_agent("Quanto custa o produto 81?")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rows"], [{"price_brl": 599.9}])
        # The conversation sent on the retry includes the database error.
        retry_messages = mock_llm.invoke.call_args_list[1][0][0]
        self.assertTrue(any('column "price" does not exist' in m["content"]
                            for m in retry_messages if m["role"] == "user"))

    @patch("src.agents.sql_agent.llm")
    def test_unsafe_sql_is_not_retried(self, mock_llm):
        from src.agents.sql_agent import run_sql_agent
        mock_llm.invoke.return_value = llm_reply({"sql": "DELETE FROM orders"})

        result = run_sql_agent("apague os pedidos")

        self.assertEqual(result["status"], "error")
        self.assertEqual(mock_llm.invoke.call_count, 1)

    @patch("src.agents.sql_agent.llm")
    def test_refusal_is_passed_through(self, mock_llm):
        from src.agents.sql_agent import run_sql_agent
        mock_llm.invoke.return_value = llm_reply(
            {"sql": None, "reason": "Would expose other customers' data."})

        result = run_sql_agent("Liste o e-mail de todos os clientes")

        self.assertEqual(result["status"], "not_answerable")
        self.assertIn("other customers", result["reason"])


if __name__ == "__main__":
    unittest.main()
