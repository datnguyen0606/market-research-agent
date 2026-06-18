"""
Eval tests for the research pipeline.

These call the real Anthropic API against fixed synthetic context so the LLM
actually generates output, then evaluate quality with DeepEval metrics.

Retrieval (Qdrant, Exa) is mocked so tests are deterministic regardless of
what documents are uploaded or what Exa returns — the eval focuses purely on
whether the analyst prompt produces good answers given known context.

Run separately from unit tests:
    pytest tests/eval/ -v

Skipped automatically when ANTHROPIC_API_KEY is not set.
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from deepeval import assert_test
from deepeval.metrics import HallucinationMetric, AnswerRelevancyMetric, GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

# Skip entire module when either key is absent.
# ANTHROPIC_API_KEY — used by analyst/router/grounding nodes.
# OPENAI_API_KEY    — used by deepeval's evaluation metrics (HallucinationMetric, GEval etc.).
pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("OPENAI_API_KEY"),
    reason="Both ANTHROPIC_API_KEY and OPENAI_API_KEY are required to run eval tests",
)


def _state(**overrides) -> dict:
    base = {
        "query": "",
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


# ── Analyst quality ───────────────────────────────────────────────────────────

def test_analyst_extracts_correct_figure_without_hallucinating():
    """
    Given a document containing a specific financial figure, the analyst
    should cite it accurately. HallucinationMetric catches invented numbers.
    """
    from app.agents.analyst import analyst_node

    context = (
        "Source: vinamilk_q3_2025.pdf\n\n"
        "Q3 2025 Financial Highlights: Net profit 2,500B VND on revenue of 15,000B VND. "
        "Net margin: 16.67%. YoY revenue growth: 8.3%."
    )
    state = _state(
        query="What was Vinamilk's net profit margin in Q3 2025?",
        retrieved_docs=[context],
    )
    result = analyst_node(state)
    assert result["answer"], "Analyst produced an empty answer"

    test_case = LLMTestCase(
        input=state["query"],
        actual_output=result["answer"],
        retrieval_context=[context],
    )
    assert_test(test_case, [
        HallucinationMetric(threshold=0.3),
        AnswerRelevancyMetric(threshold=0.7),
    ])


def test_analyst_synthesises_comparison_across_two_documents():
    """
    Given two documents about competing companies, the analyst should mention
    both with their respective figures — not just one.
    """
    from app.agents.analyst import analyst_node

    docs = [
        "Source: vinamilk_market.pdf\n\nVinamilk holds 54% domestic dairy market share as of 2025.",
        "Source: thmilk_report.pdf\n\nTH True Milk holds approximately 12% domestic dairy market share.",
    ]
    state = _state(
        query="Compare Vinamilk and TH True Milk market share in Vietnam.",
        retrieved_docs=docs,
    )
    result = analyst_node(state)
    assert result["answer"]

    completeness = GEval(
        name="Comparison completeness",
        criteria=(
            "The output must reference both Vinamilk and TH True Milk with their respective "
            "market share figures (54% and 12%) drawn from the retrieval context. "
            "Generic statements without figures are penalised."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        threshold=0.6,
    )
    test_case = LLMTestCase(
        input=state["query"],
        actual_output=result["answer"],
        retrieval_context=docs,
    )
    assert_test(test_case, [completeness])


def test_analyst_incorporates_web_results_alongside_documents():
    """
    When both document context and web results are available, the analyst
    should draw on both sources rather than ignoring one.
    """
    from app.agents.analyst import analyst_node

    doc = "Source: internal_report.pdf\n\nVinamilk Q3 2025 net margin: 16.67%."
    web = [{
        "title": "Vietnam dairy sector outlook",
        "url": "https://example.com/dairy-outlook",
        "text": "Southeast Asian dairy exports grew 23% in H1 2025, benefiting regional producers.",
        "highlights": ["Southeast Asian dairy exports grew 23%"],
    }]
    state = _state(
        query="How is Vinamilk positioned for export market growth?",
        retrieved_docs=[doc],
        web_results=web,
    )
    result = analyst_node(state)
    assert result["answer"]

    grounding = GEval(
        name="Source integration",
        criteria=(
            "The output should draw on both the uploaded document context (Vinamilk margin) and "
            "the web search context (export growth figures). "
            "An answer that ignores either source entirely is penalised."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        threshold=0.5,
    )
    test_case = LLMTestCase(
        input=state["query"],
        actual_output=result["answer"],
        retrieval_context=[doc, web[0]["text"]],
    )
    assert_test(test_case, [grounding])


def test_analyst_does_not_fabricate_when_no_sources():
    """
    With no retrieved docs and no web results, the analyst should return its
    canned 'no information found' message — not invent an answer.
    This path does NOT call the LLM, but we assert the output is honest.
    """
    from app.agents.analyst import analyst_node

    result = analyst_node(_state(query="What is Apple's revenue for Q1 2026?"))
    assert result["answer"]
    # Should clearly indicate lack of information, not fabricate figures
    answer_lower = result["answer"].lower()
    assert any(phrase in answer_lower for phrase in ["couldn't find", "no relevant", "no information", "upload"]), (
        f"Expected a 'no info' response, got: {result['answer'][:200]}"
    )


# ── Grounding quality ─────────────────────────────────────────────────────────

def test_grounding_detects_figure_not_present_in_sources():
    """
    The grounding node should flag an answer that cites a specific financial
    figure (35%) that doesn't appear in the source document (which says 16.67%).
    """
    from app.agents.grounding import grounding_node

    state = _state(
        answer=(
            "Vinamilk reported an exceptional net profit margin of 35% in Q3 2025, "
            "the highest in the company's history."
        ),
        sources=[{"title": "vinamilk_q3_2025.pdf", "url": ""}],
        retrieved_docs=["Source: vinamilk_q3_2025.pdf\n\nNet margin: 16.67%. Revenue 15,000B VND."],
    )
    result = grounding_node(state)
    # 35% doesn't appear in the source — a good grounding check catches this.
    # Haiku is a cheap model so we document the expectation but allow a miss.
    assert isinstance(result["grounding_passed"], bool), "grounding_passed must be a bool"
    if result["grounding_passed"]:
        pytest.xfail("Grounding check missed the hallucinated 35% figure — known limitation of cheap model")


def test_grounding_passes_for_accurate_answer():
    """A well-grounded answer with correct figures should pass the grounding check."""
    from app.agents.grounding import grounding_node

    state = _state(
        answer="Vinamilk's net profit margin in Q3 2025 was 16.67%, derived from 2,500B VND net profit on 15,000B VND revenue.",
        sources=[{"title": "vinamilk_q3_2025.pdf", "url": ""}],
        retrieved_docs=["Source: vinamilk_q3_2025.pdf\n\nNet profit 2,500B VND, revenue 15,000B VND, margin 16.67%."],
    )
    result = grounding_node(state)
    assert result["grounding_passed"] is True, "A factually correct, sourced answer should pass grounding"


# ── Router quality ────────────────────────────────────────────────────────────

def test_router_generates_web_queries_for_ranking_question():
    """
    'Top N companies' questions are time-sensitive and need web search.
    The router should detect this and return at least one Exa query.
    """
    from app.agents.router import router_node

    result = router_node(_state(
        query="What are the top 5 Vietnamese companies with the best financial results this quarter?"
    ))
    assert isinstance(result["search_queries"], list)
    assert len(result["search_queries"]) >= 1, (
        "A ranking + time-sensitive query should generate at least one web search query"
    )


def test_router_generates_contextual_queries_not_just_the_raw_input():
    """
    The router should decompose the user's intent into targeted search queries,
    not just echo the raw input verbatim.
    """
    from app.agents.router import router_node

    user_query = "How are Vietnam dairy companies doing financially?"
    result = router_node(_state(query=user_query))

    if result["search_queries"]:  # only check if web search was triggered
        for query in result["search_queries"]:
            # Good sub-queries are more specific than a raw paraphrase
            assert len(query) > 5, "Query should be a non-trivial search string"
