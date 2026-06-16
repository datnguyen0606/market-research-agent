from unittest.mock import MagicMock, patch

from app.integrations.langsmith import attach_feedback


def test_attach_feedback_noops_without_run_id(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls-test-key")
    with patch("langsmith.Client") as mock_client:
        result = attach_feedback(None, key="overall_quality", score=0.8)

    assert result is False
    mock_client.assert_not_called()


def test_attach_feedback_noops_without_api_key(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    with patch("langsmith.Client") as mock_client:
        result = attach_feedback("run-123", key="overall_quality", score=0.8)

    assert result is False
    mock_client.assert_not_called()


def test_attach_feedback_calls_create_feedback(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls-test-key")
    with patch("langsmith.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance

        result = attach_feedback("run-123", key="factual_accuracy", score=0.9, value="correction", comment="note")

    assert result is True
    mock_instance.create_feedback.assert_called_once_with(
        run_id="run-123", key="factual_accuracy", score=0.9, value="correction", comment="note"
    )


def test_attach_feedback_swallows_client_errors(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls-test-key")
    with patch("langsmith.Client") as mock_client_cls:
        mock_client_cls.return_value.create_feedback.side_effect = RuntimeError("network down")

        result = attach_feedback("run-123", key="overall_quality", score=0.5)

    assert result is False
