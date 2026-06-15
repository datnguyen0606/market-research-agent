import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import HallucinationMetric, AnswerRelevancyMetric


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
