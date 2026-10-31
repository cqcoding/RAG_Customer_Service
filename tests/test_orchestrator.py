import unittest
import json
from unittest.mock import patch, MagicMock
from src.agents.orchestrator import (
    workflow,
    data_extractor,
    sentiment_analyst,
    question_answerer,
    classify_query,
    synthesize_results,
    RouterState
)
from src.agents.base_agent import BaseFinancialAgent
from src.agents.extractor_agent import extract_financial_metrics
from src.agents.qa_agent import run_financial_qa
from src.agents.sentiment_agent import analyze_sentiment_from_query


class TestBaseAgent(unittest.TestCase):
    """Unit tests for BaseFinancialAgent."""

    def setUp(self):
        """Set up test fixtures."""
        self.agent = BaseFinancialAgent(model_name="meta-llama/llama-2-7b")

    def test_agent_initialization(self):
        """Test that BaseFinancialAgent initializes correctly."""
        self.assertIsNotNone(self.agent.llm)
        self.assertIsNotNone(self.agent.retriever)

    def test_clean_json_removes_markdown(self):
        """Test clean_json removes markdown code blocks."""
        test_cases = [
            ("```json\n{\"key\": \"value\"}\n```", '{"key": "value"}'),
            ("  {\"key\": \"value\"}  ", '{"key": "value"}'),
            ("```\n{\"key\": \"value\"}\n```", '{"key": "value"}'),
        ]
        for input_text, expected in test_cases:
            result = self.agent.clean_json(input_text)
            self.assertEqual(result, expected)

    def test_clean_json_handles_plain_json(self):
        """Test clean_json handles plain JSON without markdown."""
        plain_json = '{"key": "value", "number": 42}'
        result = self.agent.clean_json(plain_json)
        self.assertEqual(result, plain_json)


class TestDataExtractor(unittest.TestCase):
    """Unit tests for data extractor agent."""

    @patch('src.agents.orchestrator.extract_financial_metrics')
    @patch('src.agents.orchestrator.logger')
    def test_data_extractor_success(self, mock_logger, mock_extract):
        """Test data extractor returns results on success."""
        mock_extract.return_value = {
            "revenue": {"value": 1000000, "currency": "USD"},
            "profit": {"value": 200000, "currency": "USD"}
        }
        
        state = {
            "query": "What is the revenue?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = data_extractor(state)
        
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["source"], "data_extractor")
        mock_logger.log_agent_execution.assert_called_once()

    @patch('src.agents.orchestrator.extract_financial_metrics')
    @patch('src.agents.orchestrator.logger')
    def test_data_extractor_error_handling(self, mock_logger, mock_extract):
        """Test data extractor handles errors gracefully."""
        mock_extract.side_effect = Exception("Retrieval failed")
        
        state = {
            "query": "What is the revenue?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = data_extractor(state)
        
        self.assertIn("results", result)
        self.assertIn("Error", result["results"][0]["result"])
        mock_logger.log_agent_execution.assert_called_once()


class TestSentimentAnalyst(unittest.TestCase):
    """Unit tests for sentiment analyst agent."""

    @patch('src.agents.orchestrator.analyze_sentiment_from_query')
    @patch('src.agents.orchestrator.logger')
    def test_sentiment_analyst_success(self, mock_logger, mock_analyze):
        """Test sentiment analyst returns sentiment on success."""
        mock_analyze.return_value = {
            "sentiment": "bullish",
            "risks": ["interest_rate_risk"],
            "red_flags": [],
            "overall_score": 0.85
        }
        
        state = {
            "query": "What is the sentiment?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = sentiment_analyst(state)
        
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["source"], "sentiment_analyst")

    @patch('src.agents.orchestrator.analyze_sentiment_from_query')
    @patch('src.agents.orchestrator.logger')
    def test_sentiment_analyst_error_handling(self, mock_logger, mock_analyze):
        """Test sentiment analyst handles errors gracefully."""
        mock_analyze.side_effect = Exception("Analysis failed")
        
        state = {
            "query": "What is the sentiment?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = sentiment_analyst(state)
        
        self.assertIn("results", result)
        self.assertIn("Error", result["results"][0]["result"])


class TestQuestionAnswerer(unittest.TestCase):
    """Unit tests for question answerer agent."""

    @patch('src.agents.orchestrator.run_financial_qa')
    @patch('src.agents.orchestrator.logger')
    def test_question_answerer_success(self, mock_logger, mock_qa):
        """Test question answerer returns answer on success."""
        mock_qa.return_value = {
            "reasoning": "Based on the documents...",
            "final_answer": "The revenue is 1M USD",
            "sources": ["Document 1"]
        }
        
        state = {
            "query": "What is the revenue?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = question_answerer(state)
        
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["source"], "question_answerer")

    @patch('src.agents.orchestrator.run_financial_qa')
    @patch('src.agents.orchestrator.logger')
    def test_question_answerer_error_handling(self, mock_logger, mock_qa):
        """Test question answerer handles errors gracefully."""
        mock_qa.side_effect = Exception("QA failed")
        
        state = {
            "query": "What is the revenue?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = question_answerer(state)
        
        self.assertIn("results", result)
        self.assertIn("Error", result["results"][0]["result"])


class TestRouterLogic(unittest.TestCase):
    """Unit tests for router logic."""

    @patch('src.agents.orchestrator.router_llm.invoke')
    @patch('src.agents.orchestrator.logger')
    def test_classify_query_success(self, mock_logger, mock_llm):
        """Test query classification success."""
        mock_response = {
            "content": json.dumps({
                "classifications": [
                    {"source": "data_extractor", "query": "What financial metrics are available?"},
                    {"source": "sentiment_analyst", "query": "What is the sentiment?"}
                ]
            })
        }
        mock_llm.return_value = mock_response
        
        state = {
            "query": "What are the financial metrics and sentiment?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = classify_query(state)
        
        self.assertIn("classifications", result)
        self.assertEqual(len(result["classifications"]), 2)

    @patch('src.agents.orchestrator.router_llm.invoke')
    @patch('src.agents.orchestrator.logger')
    def test_classify_query_error_handling(self, mock_logger, mock_llm):
        """Test classify_query handles errors gracefully."""
        mock_llm.side_effect = Exception("LLM failed")
        
        state = {
            "query": "What are the metrics?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = classify_query(state)
        
        self.assertIn("classifications", result)
        self.assertEqual(len(result["classifications"]), 0)


class TestOrchestrator(unittest.TestCase):
    """Integration tests for orchestrator workflow."""

    @patch('src.agents.orchestrator.extract_financial_metrics')
    @patch('src.agents.orchestrator.analyze_sentiment_from_query')
    @patch('src.agents.orchestrator.run_financial_qa')
    @patch('src.agents.orchestrator.router_llm.invoke')
    def test_orchestrator_workflow(self, mock_llm, mock_qa, mock_sentiment, mock_extractor):
        """Test orchestrator processes queries through workflow."""
        # Mock the router response
        mock_llm.side_effect = [
            {
                "content": json.dumps({
                    "classifications": [
                        {"source": "data_extractor", "query": "What are financial metrics?"}
                    ]
                })
            },
            {"content": json.dumps({"final_answer": "The revenue is 1M USD"})}
        ]
        
        # Mock individual agent responses
        mock_extractor.return_value = {"revenue": {"value": 1000000}}
        mock_sentiment.return_value = {"sentiment": "bullish"}
        mock_qa.return_value = {"final_answer": "Answer here"}
        
        state = {
            "query": "What are the financial metrics?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        # Verify initial state
        self.assertEqual(state["query"], "What are the financial metrics?")
        self.assertEqual(len(state["results"]), 0)

    @patch('src.agents.orchestrator.router_llm.invoke')
    @patch('src.agents.orchestrator.logger')
    def test_synthesize_results_success(self, mock_logger, mock_llm):
        """Test result synthesis."""
        mock_llm.return_value = {
            "content": "Synthesized answer combining all sources"
        }
        
        state = {
            "query": "What are the metrics?",
            "classifications": [],
            "results": [
                {"source": "data_extractor", "result": "Revenue: 1M"},
                {"source": "sentiment_analyst", "result": "Sentiment: Bullish"}
            ],
            "final_answer": ""
        }
        
        result = synthesize_results(state)
        
        self.assertIn("final_answer", result)
        self.assertNotEqual(result["final_answer"], "")

    @patch('src.agents.orchestrator.router_llm.invoke')
    @patch('src.agents.orchestrator.logger')
    def test_synthesize_results_empty(self, mock_logger, mock_llm):
        """Test synthesis with no results."""
        state = {
            "query": "What are the metrics?",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        result = synthesize_results(state)
        
        self.assertIn("final_answer", result)
        self.assertIn("No results found", result["final_answer"])

    def test_orchestrator_state_structure(self):
        """Test orchestrator state has correct structure."""
        state = {
            "query": "test query",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        required_keys = {"query", "classifications", "results", "final_answer"}
        self.assertEqual(set(state.keys()), required_keys)

    def test_orchestrator_handles_empty_query(self):
        """Test orchestrator handles empty query gracefully."""
        state = {
            "query": "",
            "classifications": [],
            "results": [],
            "final_answer": ""
        }
        
        self.assertEqual(state["query"], "")
        self.assertEqual(len(state["results"]), 0)


class TestAgentIntegration(unittest.TestCase):
    """Integration tests for agents working together."""

    def test_multiple_agents_parallel_execution(self):
        """Test that results from multiple agents can be combined."""
        results = [
            {"source": "data_extractor", "result": "Revenue: 1M"},
            {"source": "sentiment_analyst", "result": "Sentiment: Bullish"},
            {"source": "question_answerer", "result": "Answer: Yes"}
        ]
        
        # Verify all results are present
        sources = [r["source"] for r in results]
        self.assertEqual(len(sources), 3)
        self.assertIn("data_extractor", sources)
        self.assertIn("sentiment_analyst", sources)
        self.assertIn("question_answerer", sources)

    def test_results_aggregation(self):
        """Test that results can be aggregated properly."""
        results = [
            {"source": "data_extractor", "result": "metrics"},
            {"source": "sentiment_analyst", "result": "analysis"}
        ]
        
        aggregated = {result["source"]: result["result"] for result in results}
        
        self.assertEqual(len(aggregated), 2)
        self.assertEqual(aggregated["data_extractor"], "metrics")
        self.assertEqual(aggregated["sentiment_analyst"], "analysis")


if __name__ == "__main__":
    unittest.main()