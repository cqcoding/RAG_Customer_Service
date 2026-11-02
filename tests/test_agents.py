"""
Unit tests for the agents and the LLM client.

Everything external is mocked (LLM, retriever, database, HTTP), so these run
anywhere with no API key, embedding model or PostgreSQL:
  - BaseAgent:   JSON cleanup shared by all agents
  - qa_agent:    retrieval of policy excerpts (no LLM)
  - sql_agent:   query generation, retry and refusal logic (the real
                 database is exercised in test_sql_agent.py)
  - OpenRouterLLM: retries, fallback to other models, and the time limit
"""
import json
import time
import unittest
from unittest.mock import Mock, patch

from langchain_core.documents import Document
from requests.exceptions import HTTPError

from src.agents.base_agent import BaseAgent
from src.agents.qa_agent import run_policy_qa
from src.agents.sql_agent import run_sql_agent
from src.models.model_llm import LLMUnavailableError, OpenRouterLLM
from src.utils.sql_database import UnsafeQueryError

POLICY_PDF = "/app/data/políticas_da_loja.pdf"


def llm_reply(content, model="mock-model") -> dict:
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return {"content": content, "model_used": model}


def policy_doc(text: str, page: int = 0) -> Document:
    return Document(page_content=text, metadata={
        "source": POLICY_PDF, "page": page, "file_type": "pdf",
        "document": "políticas_da_loja", "doc_type": "store_policy",
    })


def query_result(rows: list[dict], sql: str = "SELECT 1") -> dict:
    return {"sql": sql, "columns": list(rows[0]) if rows else [], "rows": rows, "truncated": False}


# --------------------------------------------------------------------------
# BaseAgent
# --------------------------------------------------------------------------

class TestBaseAgent(unittest.TestCase):
    def test_clean_json_strips_markdown_fences(self):
        for text in ['```json\n{"key": "value"}\n```',
                     '```JSON\n{"key": "value"}\n```',
                     '```\n{"key": "value"}\n```',
                     '  {"key": "value"}  ']:
            with self.subTest(text=text):
                self.assertEqual(BaseAgent.clean_json(text), '{"key": "value"}')

    def test_clean_json_keeps_plain_json(self):
        plain = '{"sql": "SELECT 1", "reason": null}'
        self.assertEqual(BaseAgent.clean_json(plain), plain)


# --------------------------------------------------------------------------
# Policy agent (retrieval over the PDF)
# --------------------------------------------------------------------------

@patch("src.agents.qa_agent._retriever")
class TestPolicyQAAgent(unittest.TestCase):
    def test_returns_the_retrieved_excerpts(self, mock_retriever):
        mock_retriever.return_value.invoke.return_value = [
            policy_doc("O cliente pode solicitar a devolução em até 7 (sete) dias corridos.", page=3),
            policy_doc("Rua 14 de Maio, 3200 — Centro, Campo Grande – MS", page=0),
        ]

        result = run_policy_qa("Posso devolver minha compra?")

        mock_retriever.return_value.invoke.assert_called_once_with("Posso devolver minha compra?")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["excerpts"], [
            {"source": "políticas_da_loja.pdf", "page": 4,
             "text": "O cliente pode solicitar a devolução em até 7 (sete) dias corridos."},
            {"source": "políticas_da_loja.pdf", "page": 1,
             "text": "Rua 14 de Maio, 3200 — Centro, Campo Grande – MS"},
        ])
        self.assertEqual(result["sources"], ["políticas_da_loja.pdf, p. 1", "políticas_da_loja.pdf, p. 4"])

    def test_does_not_call_an_llm(self, mock_retriever):
        mock_retriever.return_value.invoke.return_value = [policy_doc("Pix, boleto e cartão.")]

        with patch("src.models.model_llm.requests.post") as mock_post:
            run_policy_qa("Quais as formas de pagamento?")

        mock_post.assert_not_called()

    def test_nothing_retrieved(self, mock_retriever):
        mock_retriever.return_value.invoke.return_value = []

        result = run_policy_qa("Vocês vendem carros?")

        self.assertEqual(result, {"query": "Vocês vendem carros?", "status": "not_found",
                                  "excerpts": [], "sources": []})

    def test_missing_page_metadata(self, mock_retriever):
        mock_retriever.return_value.invoke.return_value = [
            Document(page_content="Texto", metadata={"source": POLICY_PDF})]

        result = run_policy_qa("?")

        self.assertIsNone(result["excerpts"][0]["page"])
        self.assertEqual(result["sources"], ["políticas_da_loja.pdf"])

    def test_retriever_failure(self, mock_retriever):
        mock_retriever.return_value.invoke.side_effect = RuntimeError("Chroma unavailable")

        result = run_policy_qa("Qual o prazo?")

        self.assertEqual(result, {"query": "Qual o prazo?", "status": "error",
                                  "error": "RuntimeError: Chroma unavailable"})


# --------------------------------------------------------------------------
# SQL agent (store data), with the database mocked
# --------------------------------------------------------------------------

@patch("src.agents.sql_agent.get_schema_description",
       return_value="TABLE products\n  price_brl numeric(10,2)\nTABLE orders\n  status text")
@patch("src.agents.sql_agent.run_readonly_query")
@patch("src.agents.sql_agent.llm")
class TestSqlAgent(unittest.TestCase):
    def test_success_returns_rows_and_sql(self, mock_llm, mock_query, _schema):
        sql = "SELECT name, price_brl FROM products WHERE name ILIKE '%Yamaha C40%'"
        mock_llm.invoke.return_value = llm_reply({"sql": sql})
        mock_query.return_value = query_result(
            [{"name": "Yamaha C40 Nylon Natural", "price_brl": 599.9}], sql)

        result = run_sql_agent("Quanto custa o Yamaha C40?")

        mock_query.assert_called_once_with(sql)
        self.assertEqual(result, {
            "query": "Quanto custa o Yamaha C40?",
            "status": "success",
            "sql": sql,
            "row_count": 1,
            "truncated": False,
            "rows": [{"name": "Yamaha C40 Nylon Natural", "price_brl": 599.9}],
        })

    def test_prompt_has_schema_and_store_rules(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.return_value = llm_reply({"sql": "SELECT 1"})
        mock_query.return_value = query_result([{"?column?": 1}])

        run_sql_agent("Quais produtos estão em promoção?")

        system, user = mock_llm.invoke.call_args[0][0][:2]
        self.assertIn("TABLE products", system["content"])
        self.assertIn("LIMIT 50", system["content"])
        for rule in ["ILIKE", "is_active", "discontinued", "CURRENT_DATE", "PRIVACY"]:
            self.assertIn(rule, system["content"])
        self.assertEqual(user, {"role": "user", "content": "Quais produtos estão em promoção?"})

    def test_fenced_json_reply_is_parsed(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.return_value = llm_reply('```json\n{"sql": "SELECT count(*) FROM products"}\n```')
        mock_query.return_value = query_result([{"count": 65}])

        self.assertEqual(run_sql_agent("Quantos produtos?")["rows"], [{"count": 65}])

    def test_refusal_does_not_touch_the_database(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.return_value = llm_reply(
            {"sql": None, "reason": "Would expose customers' personal data."})

        result = run_sql_agent("Liste o e-mail de todos os clientes")

        self.assertEqual(result["status"], "not_answerable")
        self.assertIn("personal data", result["reason"])
        mock_query.assert_not_called()

    def test_database_error_is_retried_once_with_the_error(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.side_effect = [
            llm_reply({"sql": "SELECT price FROM products"}),
            llm_reply({"sql": "SELECT price_brl FROM products"}),
        ]
        mock_query.side_effect = [Exception('column "price" does not exist'),
                                  query_result([{"price_brl": 599.9}])]

        result = run_sql_agent("Quanto custa?")

        self.assertEqual(result["status"], "success")
        self.assertEqual(mock_llm.invoke.call_count, 2)
        retry_messages = mock_llm.invoke.call_args_list[1][0][0]
        self.assertEqual(retry_messages[2]["role"], "assistant")  # the failed attempt
        self.assertIn('column "price" does not exist', retry_messages[3]["content"])

    def test_second_failure_is_reported(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.return_value = llm_reply({"sql": "SELECT nope FROM products"})
        mock_query.side_effect = Exception('column "nope" does not exist')

        result = run_sql_agent("?")

        self.assertEqual(result["status"], "error")
        self.assertIn('column "nope" does not exist', result["error"])
        self.assertEqual(mock_llm.invoke.call_count, 2)

    def test_unsafe_sql_is_not_retried(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.return_value = llm_reply({"sql": "DELETE FROM orders"})
        mock_query.side_effect = UnsafeQueryError("Only SELECT queries are allowed.")

        result = run_sql_agent("apague os pedidos")

        self.assertEqual(result["status"], "error")
        self.assertIn("UnsafeQueryError", result["error"])
        self.assertEqual(mock_llm.invoke.call_count, 1)

    def test_invalid_llm_output_is_an_error(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.return_value = llm_reply("Claro! Aqui está a consulta: SELECT 1")

        result = run_sql_agent("?")

        self.assertEqual(result["status"], "error")
        mock_query.assert_not_called()

    def test_llm_unavailable_is_an_error(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.side_effect = Exception("Todos os modelos falharam")

        result = run_sql_agent("?")

        self.assertEqual(result["status"], "error")
        self.assertIn("Todos os modelos falharam", result["error"])

    def test_deadline_is_passed_to_the_llm(self, mock_llm, mock_query, _schema):
        mock_llm.invoke.return_value = llm_reply({"sql": "SELECT 1"})
        mock_query.return_value = query_result([{"?column?": 1}])

        run_sql_agent("?", deadline=1234.5)

        self.assertEqual(mock_llm.invoke.call_args.kwargs["deadline"], 1234.5)


# --------------------------------------------------------------------------
# OpenRouterLLM client: retries and model fallback
# --------------------------------------------------------------------------

def http_response(status: int, payload=None, text=None) -> Mock:
    response = Mock(status_code=status)
    response.text = text if text is not None else json.dumps(payload or {})
    response.json.return_value = payload or {}
    if status >= 400:
        response.raise_for_status.side_effect = HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


def completion(content: str, model: str) -> dict:
    return {"model": model, "choices": [{"message": {"content": content}}]}


@patch("src.models.model_llm.time.sleep")
@patch("src.models.model_llm.requests.post")
class TestOpenRouterLLM(unittest.TestCase):
    def test_returns_content_and_model(self, mock_post, _sleep):
        mock_post.return_value = http_response(200, completion("Olá!", "model-a"))

        result = OpenRouterLLM(model="model-a").invoke([{"role": "user", "content": "oi"}])

        self.assertEqual(result, {"content": "Olá!", "model_used": "model-a"})
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "model-a")
        self.assertEqual(body["temperature"], 0)

    def test_rate_limit_is_retried_with_backoff(self, mock_post, mock_sleep):
        mock_post.side_effect = [http_response(429), http_response(429),
                                 http_response(200, completion("ok", "model-a"))]

        result = OpenRouterLLM(model="model-a").invoke([])

        self.assertEqual(result["content"], "ok")
        self.assertEqual([c.args[0] for c in mock_sleep.call_args_list], [2, 4])

    def test_falls_back_to_next_model_on_server_error(self, mock_post, _sleep):
        mock_post.side_effect = [http_response(500, text="internal error"),
                                 http_response(200, completion("ok", OpenRouterLLM.FALLBACK_MODELS[0]))]

        result = OpenRouterLLM(model="model-a").invoke([])

        self.assertEqual(result["model_used"], OpenRouterLLM.FALLBACK_MODELS[0])
        self.assertEqual([c.kwargs["json"]["model"] for c in mock_post.call_args_list],
                         ["model-a", OpenRouterLLM.FALLBACK_MODELS[0]])

    def test_empty_response_falls_back(self, mock_post, _sleep):
        mock_post.side_effect = [http_response(200, text=""),
                                 http_response(200, completion("ok", "fallback"))]

        self.assertEqual(OpenRouterLLM(model="model-a").invoke([])["content"], "ok")

    def test_raises_when_every_model_fails(self, mock_post, _sleep):
        mock_post.return_value = http_response(500, text="down")

        with self.assertRaises(LLMUnavailableError) as ctx:
            OpenRouterLLM(model="model-a").invoke([])

        self.assertIn("Todos os modelos falharam", str(ctx.exception))
        self.assertEqual(mock_post.call_count, 1 + len(OpenRouterLLM.FALLBACK_MODELS))

    def test_fallback_can_be_disabled(self, mock_post, _sleep):
        mock_post.return_value = http_response(500, text="down")

        with self.assertRaises(LLMUnavailableError):
            OpenRouterLLM(model="model-a", enable_fallback=False).invoke([])

        self.assertEqual(mock_post.call_count, 1)

    def test_each_model_is_tried_once(self, mock_post, _sleep):
        # The router's model is also the last fallback: it must not be tried twice.
        mock_post.return_value = http_response(500, text="down")

        with self.assertRaises(LLMUnavailableError):
            OpenRouterLLM(model=OpenRouterLLM.FALLBACK_MODELS[-1]).invoke([])

        tried = [c.kwargs["json"]["model"] for c in mock_post.call_args_list]
        self.assertEqual(len(tried), len(set(tried)))
        self.assertEqual(set(tried), set(OpenRouterLLM.FALLBACK_MODELS))

    def test_auth_and_credit_errors_do_not_fall_back(self, mock_post, _sleep):
        for status in (401, 402, 403):
            with self.subTest(status=status):
                mock_post.reset_mock()
                mock_post.return_value = http_response(status, text="no")

                with self.assertRaises(LLMUnavailableError) as ctx:
                    OpenRouterLLM(model="model-a").invoke([])

                self.assertIn(str(status), str(ctx.exception))
                self.assertEqual(mock_post.call_count, 1)


@patch("src.models.model_llm.time.sleep")
@patch("src.models.model_llm.requests.post")
class TestOpenRouterLLMTimeLimit(unittest.TestCase):
    def test_no_attempt_once_the_deadline_passed(self, mock_post, _sleep):
        with self.assertRaises(LLMUnavailableError) as ctx:
            OpenRouterLLM(model="model-a").invoke([], deadline=time.monotonic() - 1)

        self.assertIn("Tempo limite", str(ctx.exception))
        mock_post.assert_not_called()

    def test_request_timeout_is_capped_by_the_deadline(self, mock_post, _sleep):
        mock_post.return_value = http_response(200, completion("ok", "model-a"))

        OpenRouterLLM(model="model-a").invoke([], deadline=time.monotonic() + 10)

        timeout = mock_post.call_args.kwargs["timeout"]
        self.assertLessEqual(timeout, 10)
        self.assertGreater(timeout, 9)

    def test_without_deadline_the_timeout_is_the_default(self, mock_post, _sleep):
        mock_post.return_value = http_response(200, completion("ok", "model-a"))

        OpenRouterLLM(model="model-a").invoke([])

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 60)

    def test_no_retry_wait_that_would_pass_the_deadline(self, mock_post, mock_sleep):
        # 2.5 s left: waiting 2 s for a 429 retry would leave less than 1 s,
        # so the client moves straight to the next model instead of sleeping.
        mock_post.return_value = http_response(429)

        with self.assertRaises(LLMUnavailableError):
            OpenRouterLLM(model="model-a").invoke([], deadline=time.monotonic() + 2.5)

        mock_sleep.assert_not_called()
        self.assertEqual(mock_post.call_count, 1 + len(OpenRouterLLM.FALLBACK_MODELS))

    def test_stops_when_time_runs_out_between_models(self, mock_post, _sleep):
        clock = {"now": 100.0}

        def slow_failure(*args, **kwargs):
            clock["now"] += 20     # each attempt takes 20 s and fails
            return http_response(500, text="down")

        mock_post.side_effect = slow_failure
        with patch("src.models.model_llm.time.monotonic", side_effect=lambda: clock["now"]):
            with self.assertRaises(LLMUnavailableError) as ctx:
                OpenRouterLLM(model="model-a").invoke([], deadline=130.0)

        self.assertIn("Tempo limite", str(ctx.exception))
        self.assertEqual(mock_post.call_count, 2)                 # at 100 s and 120 s, not at 140 s
        self.assertLessEqual(mock_post.call_args_list[1].kwargs["timeout"], 10)


if __name__ == "__main__":
    unittest.main()
