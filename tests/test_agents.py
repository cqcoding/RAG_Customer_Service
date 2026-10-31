import unittest
import json
from unittest.mock import patch, MagicMock, Mock
from src.agents.base_agent import BaseFinancialAgent
from src.agents.extractor_agent import extract_financial_metrics, define_context_and_sources
from src.agents.qa_agent import question_answering_with_retrieval
from src.agents.sentiment_agent import get_openrouter_text_sentiment, analyze_sentiment_from_query


class TestBaseFinancialAgent(unittest.TestCase):
    """Tests for BaseFinancialAgent class."""

    def setUp(self):
        """Initialize agent before each test."""
        self.agent = BaseFinancialAgent(model_name="meta-llama/llama-2-7b")

    def test_agent_initialization(self):
        """Test agent initializes with LLM and retriever."""
        self.assertIsNotNone(self.agent.llm)
        self.assertIsNotNone(self.agent.retriever)

    def test_clean_json_removes_markdown_triple_backticks(self):
        """Test clean_json removes triple backticks."""
        test_input = '```json\n{"key": "value"}\n```'
        expected = '{"key": "value"}'
        result = self.agent.clean_json(test_input)
        self.assertEqual(result, expected)

    def test_clean_json_removes_leading_trailing_whitespace(self):
        """Test clean_json strips whitespace."""
        test_input = '  \n  {"key": "value"}  \n  '
        expected = '{"key": "value"}'
        result = self.agent.clean_json(test_input)
        self.assertEqual(result, expected)

    def test_clean_json_handles_plain_json(self):
        """Test clean_json doesn't modify plain JSON."""
        plain_json = '{"name": "test", "value": 123}'
        result = self.agent.clean_json(plain_json)
        self.assertEqual(result, plain_json)

    def test_clean_json_with_nested_structure(self):
        """Test clean_json handles nested JSON."""
        nested = '```\n{"outer": {"inner": "value"}}\n```'
        expected = '{"outer": {"inner": "value"}}'
        result = self.agent.clean_json(nested)
        self.assertEqual(result, expected)


class TestExtractorAgent(unittest.TestCase):
    """Tests for extractor agent functionality."""

    @patch('src.agents.extractor_agent.agent')
    def test_define_context_and_sources(self, mock_agent):
        """Test context and sources extraction."""
        # Mock documents with metadata
        mock_doc1 = Mock()
        mock_doc1.page_content = "Revenue for Q1: $1M"
        mock_doc1.metadata = {
            "source": "Tesla_2023.pdf",
            "ticker": "TSLA",
            "document_type": "Annual Report",
            "fiscal_year": "2023"
        }
        
        mock_doc2 = Mock()
        mock_doc2.page_content = "Profit margins increased"
        mock_doc2.metadata = {
            "source": "Microsoft_2023.pdf",
            "ticker": "MSFT",
            "document_type": "Quarterly Report",
            "fiscal_year": "2023"
        }
        
        mock_agent.retriever.invoke.return_value = [mock_doc1, mock_doc2]
        
        context_parts, sources = define_context_and_sources("test query", mock_agent.retriever)
        
        self.assertEqual(len(context_parts), 2)
        self.assertEqual(len(sources), 2)
        self.assertIn("TSLA", sources[0]["ticker"])
        self.assertIn("MSFT", sources[1]["ticker"])

    @patch('src.agents.extractor_agent.agent')
    def test_extract_financial_metrics_success(self, mock_agent):
        """Test successful metric extraction."""
        mock_doc = Mock()
        mock_doc.page_content = "Revenue: $1000000, Profit: $200000"
        mock_doc.metadata = {"source": "report.pdf", "ticker": "TEST", "fiscal_year": "2023"}
        
        mock_agent.retriever.invoke.return_value = [mock_doc]
        mock_agent.llm.invoke.return_value = {
            "content": '{"revenue": {"value": 1000000, "currency": "USD"}}'
        }
        
        result = extract_financial_metrics("What is the revenue?")
        
        self.assertIsNotNone(result)
        self.assertIn("revenue", result)

    @patch('src.agents.extractor_agent.agent')
    def test_extract_financial_metrics_empty_retrieval(self, mock_agent):
        """Test extraction when no documents found."""
        mock_agent.retriever.invoke.return_value = []
        
        result = extract_financial_metrics("What is the revenue?")
        
        self.assertIsNotNone(result)

    @patch('src.agents.extractor_agent.agent')
    def test_extract_financial_metrics_with_null_values(self, mock_agent):
        """Test extraction handles missing data with nulls."""
        mock_doc = Mock()
        mock_doc.page_content = "Partial data available"
        mock_doc.metadata = {"source": "report.pdf"}
        
        mock_agent.retriever.invoke.return_value = [mock_doc]
        mock_agent.llm.invoke.return_value = {
            "content": '{"revenue": {"value": null, "currency": null}}'
        }
        
        result = extract_financial_metrics("What is the revenue?")
        
        self.assertIsNotNone(result)


class TestQAAgent(unittest.TestCase):
    """Tests for QA agent functionality."""

    @patch('src.agents.qa_agent.agent')
    def test_question_answering_success(self, mock_agent):
        """Test successful question answering."""
        mock_doc = Mock()
        mock_doc.page_content = "Q4 revenue was $50 billion"
        mock_doc.metadata = {
            "source": "Annual_Report_2023.pdf",
            "ticker": "TSLA",
            "fiscal_year": "2023"
        }
        
        mock_agent.retriever.invoke.return_value = [mock_doc]
        mock_agent.llm.invoke.return_value = {
            "content": json.dumps({
                "reasoning": "Based on the document",
                "final_answer": "Q4 revenue was $50 billion",
                "sources": ["Annual_Report_2023.pdf"]
            })
        }
        
        result = question_answering_with_retrieval("What was Q4 revenue?")
        
        self.assertIn("reasoning", result)
        self.assertIn("final_answer", result)
        self.assertIn("sources", result)

    @patch('src.agents.qa_agent.agent')
    def test_question_answering_no_documents(self, mock_agent):
        """Test QA when no documents found."""
        mock_agent.retriever.invoke.return_value = []
        
        result = question_answering_with_retrieval("What is the revenue?")
        
        self.assertIsInstance(result, str)
        parsed = json.loads(result)
        self.assertIn("No documents found", parsed["reasoning"])

    @patch('src.agents.qa_agent.agent')
    def test_question_answering_multiple_sources(self, mock_agent):
        """Test QA with multiple source documents."""
        mock_docs = []
        for i in range(3):
            doc = Mock()
            doc.page_content = f"Content {i}"
            doc.metadata = {
                "source": f"Report_{i}.pdf",
                "ticker": "TEST",
                "fiscal_year": "2023"
            }
            mock_docs.append(doc)
        
        mock_agent.retriever.invoke.return_value = mock_docs
        mock_agent.llm.invoke.return_value = {
            "content": json.dumps({
                "reasoning": "Comparing all sources",
                "final_answer": "Consolidated answer",
                "sources": ["Report_0.pdf", "Report_1.pdf", "Report_2.pdf"]
            })
        }
        
        result = question_answering_with_retrieval("Compare sources")
        
        parsed = json.loads(result)
        self.assertEqual(len(parsed["sources"]), 3)


class TestSentimentAgent(unittest.TestCase):
    """Tests for sentiment analysis agent."""

    @patch('src.agents.sentiment_agent.agent')
    def test_sentiment_analysis_bullish(self, mock_agent):
        """Test sentiment analysis identifying bullish sentiment."""
        mock_agent.llm.invoke.return_value = {
            "content": json.dumps({
                "sentiment": "bullish",
                "risks": [],
                "red_flags": [],
                "comparison_to_previous": "positive"
            }),
            "model_used": "llama-2"
        }
        
        result = get_openrouter_text_sentiment("Strong revenue growth and market expansion")
        
        self.assertEqual(result["sentiment"], "bullish")
        self.assertIsInstance(result["risks"], list)
        self.assertIsInstance(result["red_flags"], list)

    @patch('src.agents.sentiment_agent.agent')
    def test_sentiment_analysis_bearish(self, mock_agent):
        """Test sentiment analysis identifying bearish sentiment."""
        mock_agent.llm.invoke.return_value = {
            "content": json.dumps({
                "sentiment": "bearish",
                "risks": ["market_volatility", "supply_chain"],
                "red_flags": ["declining_margins"],
                "comparison_to_previous": None
            }),
            "model_used": "llama-2"
        }
        
        result = get_openrouter_text_sentiment("Declining profits and market challenges")
        
        self.assertEqual(result["sentiment"], "bearish")
        self.assertEqual(len(result["risks"]), 2)
        self.assertEqual(len(result["red_flags"]), 1)

    @patch('src.agents.sentiment_agent.agent')
    def test_sentiment_analysis_neutral(self, mock_agent):
        """Test sentiment analysis identifying neutral sentiment."""
        mock_agent.llm.invoke.return_value = {
            "content": json.dumps({
                "sentiment": "neutral",
                "risks": [],
                "red_flags": [],
                "comparison_to_previous": None
            }),
            "model_used": "llama-2"
        }
        
        result = get_openrouter_text_sentiment("Steady performance with no major changes")
        
        self.assertEqual(result["sentiment"], "neutral")

    @patch('src.agents.sentiment_agent.agent')
    def test_sentiment_analysis_json_error(self, mock_agent):
        """Test sentiment analysis handles JSON parsing errors."""
        mock_agent.llm.invoke.return_value = {
            "content": "Invalid JSON response"
        }
        mock_agent.clean_json.return_value = "Invalid JSON response"
        
        result = get_openrouter_text_sentiment("Some text")
        
        self.assertEqual(result["sentiment"], "error")
        self.assertIn("error_message", result)

    @patch('src.agents.sentiment_agent.agent')
    def test_analyze_sentiment_from_query(self, mock_agent):
        """Test full sentiment analysis from query."""
        mock_doc = Mock()
        mock_doc.page_content = "Strong financial performance"
        mock_doc.metadata = {"source": "report.pdf"}
        
        mock_agent.retriever.invoke.return_value = [mock_doc]
        mock_agent.llm.invoke.return_value = {
            "content": json.dumps({
                "sentiment": "bullish",
                "risks": [],
                "red_flags": []
            })
        }
        
        result = analyze_sentiment_from_query("What is the sentiment?")
        
        self.assertIsNotNone(result)


class TestErrorHandling(unittest.TestCase):
    """Tests for error handling across agents."""

    @patch('src.agents.base_agent.OpenRouterLLM')
    def test_agent_handles_llm_failure(self, mock_llm_class):
        """Test agent handles LLM call failure."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM unavailable")
        mock_llm_class.return_value = mock_llm
        
        agent = BaseFinancialAgent(model_name="test-model")
        
        with self.assertRaises(Exception):
            agent.llm.invoke([])

    @patch('src.agents.base_agent.get_retriever')
    def test_agent_handles_retriever_failure(self, mock_get_retriever):
        """Test agent handles retriever failure."""
        mock_retriever = MagicMock()
        mock_retriever.invoke.side_effect = Exception("Database error")
        mock_get_retriever.return_value = mock_retriever
        
        agent = BaseFinancialAgent(model_name="test-model")
        
        with self.assertRaises(Exception):
            agent.retriever.invoke("query")


class TestDataStructures(unittest.TestCase):
    """Tests for data structure validation."""

    def test_sentiment_result_structure(self):
        """Test sentiment result has expected structure."""
        sentiment_result = {
            "sentiment": "bullish",
            "risks": ["risk1"],
            "red_flags": [],
            "comparison": None,
            "model_used": "llama-2"
        }
        
        required_keys = {"sentiment", "risks", "red_flags"}
        self.assertTrue(required_keys.issubset(set(sentiment_result.keys())))

    def test_extraction_result_structure(self):
        """Test extraction result has expected structure."""
        extraction_result = {
            "revenue": {"value": 1000000, "currency": "USD"},
            "profit": {"value": 200000, "currency": "USD"}
        }
        
        for metric in extraction_result.values():
            self.assertIn("value", metric)
            self.assertIn("currency", metric)

    def test_qa_result_structure(self):
        """Test QA result has expected structure."""
        qa_result = {
            "reasoning": "Step-by-step analysis",
            "final_answer": "The answer is X",
            "sources": ["source1", "source2"]
        }
        
        required_keys = {"reasoning", "final_answer", "sources"}
        self.assertEqual(set(qa_result.keys()), required_keys)


if __name__ == "__main__":
    unittest.main()
