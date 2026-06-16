import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import HallucinationMetric, AnswerRelevancyMetric, GEval
from deepeval.test_case import LLMTestCaseParams


# ── Existing DeepEval metrics ──────────────────────────────────────────────────

def test_financial_accuracy():
    user_query = "What was Vinamilk's net profit margin in Q3 2025?"
    context = ["Q3 2025 Financial Statement: Net profit 2,500B VND on 15,000B VND revenue."]
    generated_output = "Vinamilk recorded a net profit margin of 16.67% in Q3 2025."

    test_case = LLMTestCase(
        input=user_query,
        actual_output=generated_output,
        retrieval_context=context,
    )

    assert_test(test_case, [
        HallucinationMetric(threshold=0.3),
        AnswerRelevancyMetric(threshold=0.8),
    ])


def test_swot_relevancy():
    user_query = "What are the main strengths of Vinamilk?"
    context = ["Vinamilk holds over 50% domestic market share in the dairy segment as of 2024."]
    generated_output = "Vinamilk's primary strength is its dominant domestic market share exceeding 50%."

    test_case = LLMTestCase(
        input=user_query,
        actual_output=generated_output,
        retrieval_context=context,
    )

    assert_test(test_case, [
        HallucinationMetric(threshold=0.3),
        AnswerRelevancyMetric(threshold=0.8),
    ])


# ── LLM-as-Judge tests (GEval) ─────────────────────────────────────────────────
# GEval uses an LLM to score outputs against custom criteria — same principle
# as our critic's judge node, but run offline in CI against golden examples.

def test_judge_factual_accuracy():
    """Judge should reject reports that invent figures not in source documents."""
    context = ["Q3 2025: Revenue 15,000B VND, Net profit 2,500B VND, Margin 16.67%."]
    hallucinated_output = "Vinamilk reported revenue of 18,000B VND and a margin of 22% in Q3 2025."

    test_case = LLMTestCase(
        input="Analyse Vinamilk Q3 2025 financial performance.",
        actual_output=hallucinated_output,
        retrieval_context=context,
    )

    factual_accuracy = GEval(
        name="Factual Accuracy",
        criteria="The output must only cite financial figures that appear in the retrieval context. "
                 "Invented or extrapolated numbers are a critical failure.",
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        threshold=0.4,  # expect a low score — this output is hallucinated
        strict_mode=False,
    )

    # This test passes if the judge correctly gives a LOW score (catches the hallucination)
    score = factual_accuracy.measure(test_case)
    assert score < 0.4, f"Judge failed to detect hallucinated figures — score was {score:.2f}"


def test_judge_completeness():
    """Judge should reward specific, evidence-backed SWOT over generic filler."""
    context = [
        "Vinamilk holds 54% domestic dairy market share.",
        "Imported milk powder costs rose 18% YoY in 2025.",
        "Southeast Asian dairy export volumes grew 23% in H1 2025.",
    ]
    specific_output = (
        "Strengths: 54% domestic market share provides pricing power. "
        "Weaknesses: 18% YoY rise in imported milk powder costs pressures margins. "
        "Opportunities: 23% growth in Southeast Asian dairy exports. "
        "Threats: Continued commodity price volatility."
    )

    test_case = LLMTestCase(
        input="Provide a SWOT analysis for Vinamilk.",
        actual_output=specific_output,
        retrieval_context=context,
    )

    completeness = GEval(
        name="Completeness",
        criteria="The output must cite specific figures and facts from the source context. "
                 "Generic statements like 'strong market position' without evidence are penalised.",
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        threshold=0.7,
    )

    assert_test(test_case, [completeness])
