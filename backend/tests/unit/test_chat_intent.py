from unittest.mock import MagicMock, patch

from app.agents.chat_intent import classify_chat_intent


def _fake_response(content: str):
    msg = MagicMock()
    msg.content = content
    return msg


@patch("app.agents.chat_intent.ChatAnthropic")
def test_classify_correction(mock_anthropic):
    mock_anthropic.return_value.invoke.return_value = _fake_response('{"intent": "correction"}')

    result = classify_chat_intent("That revenue number is wrong, it was actually 15,000B VND.")

    assert result["intent"] == "correction"


@patch("app.agents.chat_intent.ChatAnthropic")
def test_classify_strips_markdown_fence(mock_anthropic):
    mock_anthropic.return_value.invoke.return_value = _fake_response('```json\n{"intent": "satisfied"}\n```')

    result = classify_chat_intent("Thanks, this looks great!")

    assert result["intent"] == "satisfied"


@patch("app.agents.chat_intent.ChatAnthropic")
def test_classify_rejects_unknown_intent_label(mock_anthropic):
    """A label outside the fixed set must degrade to 'other' rather than propagate freely."""
    mock_anthropic.return_value.invoke.return_value = _fake_response('{"intent": "ecstatic"}')

    result = classify_chat_intent("wow amazing")

    assert result["intent"] == "other"


@patch("app.agents.chat_intent.ChatAnthropic")
def test_classify_handles_unparseable_output(mock_anthropic):
    mock_anthropic.return_value.invoke.return_value = _fake_response("garbage, not json")

    result = classify_chat_intent("anything")

    assert result["intent"] == "other"
