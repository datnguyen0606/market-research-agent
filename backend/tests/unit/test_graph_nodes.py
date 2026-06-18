"""
Unit tests for individual graph nodes.

All Anthropic, Qdrant, and Exa calls are mocked — these run fast with no API keys.
They test plumbing (state flow, error handling, routing logic), not output quality.
Output quality is covered by tests/eval/test_pipeline.py.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.agents.router import router_node
from app.agents.analyst import analyst_node
from app.agents.grounding import grounding_node
from app.agents.document import document_rag_node
from app.agents.search import web_search_node
from app.agents.retrieval import retrieval_node


def _state(**overrides) -> dict:
    base = {
        "query": "What are the key financial risks?",
        "search_queries": [],
        "retrieved_docs": [],
        "web_results": [],
        "messages": [],
        "answer": None,
        "sources": [],
        "grounding_passed": False,
    }
    base.update(overrides)
    return base


# ── Router ────────────────────────────────────────────────────────────────────

@patch("app.agents.router.ChatAnthropic")
def test_router_skips_search_and_llm_on_chat_followup(mock_cls):
    """Chat follow-ups bypass web search entirely — no LLM call needed."""
    state = _state(messages=[HumanMessage(content="Tell me more about the margins.")])
    result = router_node(state)
    assert result["search_queries"] == []
    mock_cls.assert_not_called()


@patch("app.agents.router.ChatAnthropic")
def test_router_extracts_queries_from_valid_json(mock_cls):
    mock_cls.return_value.invoke.return_value = MagicMock(content=json.dumps({
        "needs_web_search": True,
        "search_queries": ["Vietnam dairy earnings Q2 2026", "VNM financial results 2026"],
    }))
    result = router_node(_state(query="Top dairy companies in Vietnam this quarter"))
    assert result["search_queries"] == ["Vietnam dairy earnings Q2 2026", "VNM financial results 2026"]


@patch("app.agents.router.ChatAnthropic")
def test_router_falls_back_to_user_query_on_bad_json(mock_cls):
    """Malformed LLM JSON falls back to a single query using the raw user input."""
    mock_cls.return_value.invoke.return_value = MagicMock(content="not valid json {{")
    result = router_node(_state(query="top companies Q2 2026"))
    assert result["search_queries"] == ["top companies Q2 2026"]


@patch("app.agents.router.ChatAnthropic")
def test_router_returns_empty_list_when_web_not_needed(mock_cls):
    mock_cls.return_value.invoke.return_value = MagicMock(content=json.dumps({
        "needs_web_search": False,
        "search_queries": [],
    }))
    result = router_node(_state(query="Summarise the uploaded documents"))
    assert result["search_queries"] == []


# ── Analyst ───────────────────────────────────────────────────────────────────

def test_analyst_returns_no_info_without_calling_llm():
    """No retrieved docs and no web results → canned 'no info' response, no LLM call needed."""
    with patch("app.agents.analyst.ChatAnthropic") as mock_cls:
        result = analyst_node(_state())
        mock_cls.assert_not_called()
    assert result["answer"]
    assert result["sources"] == []


@patch("app.agents.analyst.ChatAnthropic")
def test_analyst_uses_retrieved_docs_in_prompt(mock_cls):
    mock_cls.return_value.invoke.return_value = MagicMock(content="Margin is 16.67%.")
    doc = "Source: annual_report.pdf\n\nNet profit 2500B VND on 15000B revenue."
    result = analyst_node(_state(retrieved_docs=[doc]))
    assert result["answer"] == "Margin is 16.67%."


@patch("app.agents.analyst.ChatAnthropic")
def test_analyst_uses_last_chat_message_as_query(mock_cls):
    """On follow-up, the last HumanMessage content — not the original query — drives the prompt."""
    mock_cls.return_value.invoke.return_value = MagicMock(content="Costs rose because of commodity prices.")
    state = _state(
        query="original query",
        messages=[HumanMessage(content="Why did costs increase?")],
        retrieved_docs=["Source: report.pdf\n\nInput costs rose 20% YoY."],
    )
    analyst_node(state)
    call_args = str(mock_cls.return_value.invoke.call_args)
    assert "Why did costs increase?" in call_args


@patch("app.agents.analyst.ChatAnthropic")
def test_analyst_extracts_web_source_urls(mock_cls):
    mock_cls.return_value.invoke.return_value = MagicMock(content="Markets are bullish.")
    web = [{"title": "Market Outlook", "url": "https://example.com/outlook", "text": "Strong growth.", "highlights": []}]
    result = analyst_node(_state(web_results=web))
    assert any(s["url"] == "https://example.com/outlook" for s in result["sources"])


# ── Grounding ─────────────────────────────────────────────────────────────────

def test_grounding_passes_when_no_sources_to_verify_against():
    """No sources → skip check, default to passed so we don't block valid document-less answers."""
    result = grounding_node(_state(answer="Some answer."))
    assert result["grounding_passed"] is True


def test_grounding_fails_immediately_on_empty_answer():
    result = grounding_node(_state(answer="", sources=[{"title": "doc", "url": ""}]))
    assert result["grounding_passed"] is False


@patch("app.agents.grounding.ChatAnthropic")
def test_grounding_passes_on_llm_approval(mock_cls):
    mock_cls.return_value.invoke.return_value = MagicMock(content='{"grounded": true, "issue": null}')
    state = _state(
        answer="The margin is 16.67% as reported in Q3 2025.",
        sources=[{"title": "Annual Report", "url": ""}],
    )
    result = grounding_node(state)
    assert result["grounding_passed"] is True


@patch("app.agents.grounding.ChatAnthropic")
def test_grounding_fails_on_llm_rejection(mock_cls):
    mock_cls.return_value.invoke.return_value = MagicMock(
        content='{"grounded": false, "issue": "figure not present in sources"}'
    )
    state = _state(
        answer="Revenue was 99,000B VND which set a world record.",
        sources=[{"title": "Unrelated Doc", "url": ""}],
    )
    result = grounding_node(state)
    assert result["grounding_passed"] is False


@patch("app.agents.grounding.ChatAnthropic")
def test_grounding_defaults_to_passed_on_llm_parse_failure(mock_cls):
    """Parse failure must never block a valid answer — fail open, not closed."""
    mock_cls.return_value.invoke.return_value = MagicMock(content="oops not json")
    state = _state(answer="Some answer.", sources=[{"title": "Doc", "url": ""}])
    result = grounding_node(state)
    assert result["grounding_passed"] is True


# ── Web search ────────────────────────────────────────────────────────────────

def test_web_search_skips_when_router_sent_no_queries():
    """search_queries=[] is the router's signal to skip web search entirely."""
    with patch("app.agents.search.Exa") as mock_cls:
        result = web_search_node(_state(search_queries=[]))
        mock_cls.assert_not_called()
    assert result["web_results"] == []


@patch("app.agents.search.Exa")
def test_web_search_deduplicates_urls_across_sub_queries(mock_cls):
    """Same URL appearing in results from two sub-queries should appear only once."""
    def _result(url):
        r = MagicMock()
        r.url, r.title, r.text, r.highlights = url, "Title", "Content", []
        return r

    mock_response = MagicMock()
    mock_response.results = [_result("https://example.com/a"), _result("https://example.com/b")]
    mock_cls.return_value.search_and_contents.return_value = mock_response

    result = web_search_node(_state(search_queries=["query 1", "query 2"]))
    urls = [r["url"] for r in result["web_results"]]
    assert len(urls) == len(set(urls)), "Duplicate URLs should be removed"
    assert len(urls) == 2


@patch("app.agents.search.Exa")
def test_web_search_continues_on_single_query_failure(mock_cls):
    """If one sub-query fails, the others should still return results."""
    good_result = MagicMock()
    good_result.url, good_result.title, good_result.text, good_result.highlights = (
        "https://good.com", "Good", "Content", []
    )
    good_response = MagicMock()
    good_response.results = [good_result]

    mock_cls.return_value.search_and_contents.side_effect = [
        Exception("Exa timeout"),
        good_response,
    ]
    result = web_search_node(_state(search_queries=["failing query", "working query"]))
    assert len(result["web_results"]) == 1
    assert result["web_results"][0]["url"] == "https://good.com"


# ── Document RAG ─────────────────────────────────────────────────────────────

@patch("app.agents.document.embed_sparse")
@patch("app.agents.document.embed_chunks")
@patch("app.agents.document.search_chunks")
def test_document_rag_returns_empty_when_no_chunks_found(mock_search, mock_dense, mock_sparse):
    mock_dense.return_value = [[0.1] * 768]
    mock_sparse.return_value = [{"indices": [1], "values": [1.0]}]
    mock_search.return_value = []
    result = document_rag_node(_state())
    assert result["retrieved_docs"] == []


@patch("app.agents.document.embed_sparse")
@patch("app.agents.document.embed_chunks")
def test_document_rag_returns_empty_on_embedding_failure(mock_dense, mock_sparse):
    mock_dense.side_effect = RuntimeError("Jina API unreachable")
    result = document_rag_node(_state())
    assert result["retrieved_docs"] == []


@patch("app.agents.document.embed_sparse")
@patch("app.agents.document.embed_chunks")
@patch("app.agents.document.search_chunks")
@patch("app.agents.document.fetch_parent")
@patch("app.agents.document.rerank")
def test_document_rag_prepends_source_header(mock_rerank, mock_fetch, mock_search, mock_dense, mock_sparse):
    """Each retrieved parent block should be prefixed with 'Source: <filename>' for citation."""
    mock_dense.return_value = [[0.1] * 768]
    mock_sparse.return_value = [{"indices": [1], "values": [1.0]}]
    mock_search.return_value = [
        {"text_snippet": "snippet", "parent_id": "p1", "doc_id": "doc1", "filename": "report.pdf", "score": 0.9}
    ]
    mock_rerank.return_value = [{"index": 0}]
    mock_fetch.return_value = {"full_text": "Full page text about financials.", "filename": "report.pdf"}

    result = document_rag_node(_state())
    assert len(result["retrieved_docs"]) == 1
    assert result["retrieved_docs"][0].startswith("Source: report.pdf")
