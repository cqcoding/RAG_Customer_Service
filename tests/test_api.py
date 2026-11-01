"""
Tests for the REST API (src/api/main.py), with the workflow mocked.
"""
import asyncio
import json
import time
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

import src.api.main as api

client = TestClient(api.app)


class TestHealth(unittest.TestCase):
    def test_health(self):
        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")


@patch("src.api.main.logger")
class TestQuery(unittest.TestCase):
    @patch("src.api.main.answer", return_value="O Yamaha C40 custa R$ 599,90.")
    def test_returns_the_answer(self, mock_answer, _logger):
        response = client.post("/query", json={"query": "Quanto custa o Yamaha C40?"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["final_answer"], "O Yamaha C40 custa R$ 599,90.")
        self.assertEqual(body["status"], "success")
        self.assertGreaterEqual(body["latency_ms"], 0)
        mock_answer.assert_called_once_with("Quanto custa o Yamaha C40?", history=[])

    @patch("src.api.main.answer", return_value="ok")
    def test_history_is_passed_to_the_workflow(self, mock_answer, _logger):
        history = [{"role": "user", "content": "Quanto custa o Ohana CK-20?"},
                   {"role": "assistant", "content": "R$ 549,00."}]

        client.post("/query", json={"query": "e tem desconto?", "history": history})

        mock_answer.assert_called_once_with("e tem desconto?", history=history)

    def test_invalid_bodies_are_rejected(self, _logger):
        for body in [{}, {"query": "oi", "history": [{"role": "system", "content": "x"}]}]:
            with self.subTest(body=body):
                self.assertEqual(client.post("/query", json=body).status_code, 422)

    @patch("src.api.main.answer", side_effect=RuntimeError("workflow exploded"))
    def test_workflow_failure_is_a_500_and_logged(self, _answer, mock_logger):
        response = client.post("/query", json={"query": "oi"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "RuntimeError: workflow exploded")
        mock_logger.log_error.assert_called_once()

    def test_requests_are_handled_concurrently(self, _logger):
        """The workflow blocks on LLM calls; one request must not hold up the others.

        All requests go through one event loop, like a real server. (Calling
        TestClient from several threads would give each request its own loop
        and hide the problem.)
        """
        delay = 0.5

        def slow_answer(query, history=None):
            time.sleep(delay)
            return "ok"

        async def send_three():
            transport = httpx.ASGITransport(app=api.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                return await asyncio.gather(*[ac.post("/query", json={"query": "oi"}) for _ in range(3)])

        with patch("src.api.main.answer", side_effect=slow_answer):
            start = time.perf_counter()
            responses = asyncio.run(send_three())
            elapsed = time.perf_counter() - start

        self.assertEqual([r.status_code for r in responses], [200, 200, 200])
        # Serialized, 3 requests would take 3 * delay.
        self.assertLess(elapsed, 2 * delay, f"requests took {elapsed:.2f}s: they ran one at a time")


class TestLogEndpoints(unittest.TestCase):
    def setUp(self):
        events = [
            {"event_type": "routing_decision", "user_query": "oi", "agents_selected": [], "num_agents": 0},
            {"event_type": "llm_call", "agent": "classifier", "latency_ms": 100.0},
            {"event_type": "llm_call", "agent": "synthesizer", "latency_ms": 300.0},
        ]
        self.content = "\n".join(json.dumps(e) for e in events) + "\nnot json\n"

    def _with_log(self, path):
        def fake_path(_):
            fake = unittest.mock.MagicMock()
            fake.exists.return_value = True
            return fake
        mock_open = unittest.mock.mock_open(read_data=self.content)
        mock_open.return_value.__iter__ = lambda f: iter(self.content.splitlines(keepends=True))
        with patch("src.api.main.Path", side_effect=fake_path), patch("builtins.open", mock_open):
            return client.get(path).json()

    def test_stats_aggregate_llm_calls(self):
        self.assertEqual(self._with_log("/logs/stats"), {
            "total_llm_calls": 2,
            "avg_latency_ms": 200.0,
            "calls_by_agent": {"classifier": 1, "synthesizer": 1},
        })

    def test_routing_decisions_are_filtered(self):
        body = self._with_log("/logs/routing-decisions")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["decisions"][0]["event_type"], "routing_decision")

    def test_llm_calls_skip_invalid_lines_and_respect_limit(self):
        body = self._with_log("/logs/llm-calls?limit=2")
        self.assertEqual(body["total"], 3)
        self.assertEqual(len(body["logs"]), 2)


if __name__ == "__main__":
    unittest.main()
