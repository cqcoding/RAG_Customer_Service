"""
Unit tests for the orchestrator: routing, conversation memory and synthesis.
All LLM calls and agents are mocked, so these need no network, model download
or database. The agents themselves are tested in test_agents.py.
"""
import json
import unittest
from unittest.mock import patch

from src.agents.orchestrator import (
    FALLBACK_ANSWER,
    answer,
    classify_query,
    route_to_agents,
    synthesize_results,
)


def reply(content) -> dict:
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return {"content": content, "model_used": "mock"}


def route(*pairs) -> dict:
    return {"classifications": [{"source": s, "query": q} for s, q in pairs]}


@patch("src.agents.orchestrator.logger")
class TestClassifyQuery(unittest.TestCase):
    @patch("src.agents.orchestrator.router_llm")
    def test_parses_fenced_json(self, mock_router, _logger):
        mock_router.invoke.return_value = reply(
            '```json\n{"classifications": [{"source": "store_database", "query": "Preço do Yamaha C40?"}]}\n```')

        result = classify_query({"query": "Quanto custa o Yamaha C40?"})

        self.assertEqual(result["classifications"],
                         [{"source": "store_database", "query": "Preço do Yamaha C40?"}])

    @patch("src.agents.orchestrator.router_llm")
    def test_invalid_output_routes_nowhere(self, mock_router, _logger):
        for bad in ["not json", '{"classifications": [{"source": "hacker", "query": "x"}]}']:
            with self.subTest(bad=bad):
                mock_router.invoke.return_value = reply(bad)
                self.assertEqual(classify_query({"query": "oi"}), {"classifications": []})

    @patch("src.agents.orchestrator.router_llm")
    def test_router_sees_recent_history(self, mock_router, _logger):
        mock_router.invoke.return_value = reply(route())
        history = [{"role": "user", "content": "Quanto custa o Ohana CK-20?"},
                   {"role": "assistant", "content": "O Ohana CK-20 custa R$ 549,00."}]

        classify_query({"query": "e tem desconto?", "history": history})

        router_input = mock_router.invoke.call_args[0][0][1]["content"]
        self.assertIn("Customer: Quanto custa o Ohana CK-20?", router_input)
        self.assertIn("Assistant: O Ohana CK-20 custa R$ 549,00.", router_input)
        self.assertIn("Current message: e tem desconto?", router_input)

    @patch("src.agents.orchestrator.router_llm")
    def test_history_is_bounded(self, mock_router, _logger):
        mock_router.invoke.return_value = reply(route())
        history = [{"role": "user", "content": f"msg {i} " + "x" * 2000} for i in range(20)]

        classify_query({"query": "e agora?", "history": history})

        router_input = mock_router.invoke.call_args[0][0][1]["content"]
        self.assertNotIn("msg 13 ", router_input)
        self.assertIn("msg 19 ", router_input)
        self.assertLess(len(router_input), 6 * 700)


class TestRouteToAgents(unittest.TestCase):
    def test_fans_out_with_sub_questions(self):
        state = {"query": "original",
                 **route(("store_database", "pedido 4?"), ("question_answerer", "troca?"))}

        sends = route_to_agents(state)

        self.assertEqual([s.node for s in sends], ["store_database", "question_answerer"])
        self.assertEqual(sends[0].arg["query"], "pedido 4?")
        self.assertEqual(sends[1].arg["query"], "troca?")

    def test_no_classifications_goes_to_synthesis(self):
        self.assertEqual(route_to_agents({"query": "obrigado", "classifications": []}), "synthesize")


@patch("src.agents.orchestrator.logger")
class TestSynthesize(unittest.TestCase):
    @patch("src.agents.orchestrator.synth_llm")
    def test_prompt_has_results_and_history(self, mock_synth, _logger):
        mock_synth.invoke.return_value = reply("Seu pedido foi entregue.")
        state = {
            "query": "e o pedido 4?",
            "history": [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "Olá!"}],
            "results": [{"source": "store_database", "result": {"rows": [{"status": "delivered"}]}}],
        }

        self.assertEqual(synthesize_results(state), {"final_answer": "Seu pedido foi entregue."})

        messages = mock_synth.invoke.call_args[0][0]
        self.assertIn('"e o pedido 4?"', messages[0]["content"])
        self.assertEqual(messages[1:3], state["history"])
        self.assertIn('"status": "delivered"', messages[-1]["content"])

    @patch("src.agents.orchestrator.synth_llm")
    def test_no_results_uses_strict_prompt_without_facts(self, mock_synth, _logger):
        mock_synth.invoke.return_value = reply("Desculpe, só ajudo com assuntos da loja.")

        synthesize_results({"query": "Qual a capital da França?", "results": []})

        messages = mock_synth.invoke.call_args[0][0]
        self.assertIn("do NOT state any fact", messages[0]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "Qual a capital da França?"})

    @patch("src.agents.orchestrator.synth_llm")
    def test_llm_failure_gives_friendly_fallback(self, mock_synth, _logger):
        mock_synth.invoke.side_effect = Exception("Todos os modelos falharam")

        result = synthesize_results({"query": "oi", "results": []})

        self.assertEqual(result["final_answer"], FALLBACK_ANSWER)


@patch("src.agents.orchestrator.logger")
@patch("src.agents.orchestrator.synth_llm")
@patch("src.agents.orchestrator.router_llm")
@patch("src.agents.orchestrator.run_policy_qa")
@patch("src.agents.orchestrator.run_sql_agent")
class TestWorkflow(unittest.TestCase):
    def test_mixed_question_uses_both_agents(self, mock_sql, mock_qa, mock_router, mock_synth, _logger):
        mock_router.invoke.return_value = reply(route(
            ("store_database", "Status e itens do pedido 4?"),
            ("question_answerer", "Política de troca para defeito?")))
        mock_sql.return_value = {"status": "success", "rows": [{"status": "delivered"}]}
        mock_qa.return_value = {"status": "success", "final_answer": "Trocas em até 7 dias."}
        mock_synth.invoke.return_value = reply("Pode trocar em até 7 dias.")

        result = answer("Meu pedido 4 chegou com defeito, posso trocar?")

        self.assertEqual(result, "Pode trocar em até 7 dias.")
        mock_sql.assert_called_once_with("Status e itens do pedido 4?")
        mock_qa.assert_called_once_with("Política de troca para defeito?")
        synth_input = mock_synth.invoke.call_args[0][0][-1]["content"]
        self.assertIn("store_database", synth_input)
        self.assertIn("question_answerer", synth_input)

    def test_small_talk_skips_agents(self, mock_sql, mock_qa, mock_router, mock_synth, _logger):
        mock_router.invoke.return_value = reply(route())
        mock_synth.invoke.return_value = reply("De nada!")

        self.assertEqual(answer("Obrigado!"), "De nada!")
        mock_sql.assert_not_called()
        mock_qa.assert_not_called()

    def test_agent_crash_still_produces_an_answer(self, mock_sql, mock_qa, mock_router, mock_synth, _logger):
        mock_router.invoke.return_value = reply(route(("store_database", "estoque?")))
        mock_sql.side_effect = Exception("connection refused")
        mock_synth.invoke.return_value = reply("Não consegui consultar o estoque agora.")

        self.assertEqual(answer("Tem estoque?"), "Não consegui consultar o estoque agora.")
        self.assertIn("Error: connection refused", mock_synth.invoke.call_args[0][0][-1]["content"])


if __name__ == "__main__":
    unittest.main()
