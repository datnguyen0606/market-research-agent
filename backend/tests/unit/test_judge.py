import json
from unittest.mock import MagicMock, patch

from app.agents.judge import run_judge


def _fake_response(content: str):
    msg = MagicMock()
    msg.content = content
    return msg


@patch("app.agents.judge.ChatAnthropic")
def test_run_judge_parses_clean_json(mock_anthropic):
    mock_anthropic.return_value.invoke.return_value = _fake_response(json.dumps({
        "scores": {
            "factual_accuracy": 0.9,
            "logical_consistency": 0.8,
            "completeness": 0.85,
            "sentiment_alignment": 0.9,
        },
        "overall": 0.86,
        "passed": True,
        "feedback": "Passes all quality criteria",
    }))

    result = run_judge("VNM", ["financials"], ["news"], {"executive_summary": "..."})

    assert result["passed"] is True
    assert result["overall"] == 0.86
    assert result["scores"]["factual_accuracy"] == 0.9


@patch("app.agents.judge.ChatAnthropic")
def test_run_judge_strips_markdown_fence(mock_anthropic):
    payload = {
        "scores": {
            "factual_accuracy": 0.5,
            "logical_consistency": 0.5,
            "completeness": 0.5,
            "sentiment_alignment": 0.5,
        },
        "overall": 0.5,
        "passed": False,
        "feedback": "Mediocre",
    }
    mock_anthropic.return_value.invoke.return_value = _fake_response(f"```json\n{json.dumps(payload)}\n```")

    result = run_judge("VNM", [], [], {})

    assert result["overall"] == 0.5
    assert result["passed"] is False


@patch("app.agents.judge.ChatAnthropic")
def test_run_judge_computes_overall_when_missing(mock_anthropic):
    mock_anthropic.return_value.invoke.return_value = _fake_response(json.dumps({
        "scores": {
            "factual_accuracy": 1.0,
            "logical_consistency": 1.0,
            "completeness": 1.0,
            "sentiment_alignment": 1.0,
        },
        "feedback": "Great",
    }))

    result = run_judge("VNM", [], [], {})

    assert result["overall"] == 1.0
    assert result["passed"] is True


@patch("app.agents.judge.ChatAnthropic")
def test_run_judge_handles_unparseable_output(mock_anthropic):
    """The judge call itself never raises — a bad LLM response degrades to a failing score."""
    mock_anthropic.return_value.invoke.return_value = _fake_response("not json at all")

    result = run_judge("VNM", [], [], {})

    assert result["passed"] is False
    assert result["overall"] == 0.0
    assert "could not be parsed" in result["feedback"]
