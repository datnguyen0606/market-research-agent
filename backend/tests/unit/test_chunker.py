"""Unit tests for chunker.py — image extraction path and existing helpers."""
from unittest.mock import MagicMock, patch

import pytest

from app.rag.chunker import (
    _make_chunks,
    chunk_docx_pages,
    extract_image_pages,
)


def _mock_anthropic_response(text: str):
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


class TestExtractImagePages:
    def test_returns_single_page_dict(self):
        extracted = "VNM: BUY 110,000\nVHM: HOLD 52,000"
        with patch("app.rag.chunker.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _mock_anthropic_response(extracted)
            result = extract_image_pages(b"\x89PNG\r\n", "image/png")

        assert len(result) == 1
        assert result[0]["page"] == 0
        assert result[0]["text"] == extracted

    def test_normalises_jpg_to_jpeg(self):
        with patch("app.rag.chunker.anthropic.Anthropic") as mock_cls:
            instance = mock_cls.return_value
            instance.messages.create.return_value = _mock_anthropic_response("text")
            extract_image_pages(b"JFIF", "image/jpg")

        call_kwargs = instance.messages.create.call_args
        content = call_kwargs.kwargs["messages"][0]["content"]
        image_block = next(b for b in content if b["type"] == "image")
        assert image_block["source"]["media_type"] == "image/jpeg"

    def test_passes_correct_model(self):
        with patch("app.rag.chunker.anthropic.Anthropic") as mock_cls:
            instance = mock_cls.return_value
            instance.messages.create.return_value = _mock_anthropic_response("text")
            extract_image_pages(b"\x89PNG", "image/png")

        assert instance.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5-20251001"

    def test_strips_whitespace_from_response(self):
        with patch("app.rag.chunker.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _mock_anthropic_response("  hello world  \n")
            result = extract_image_pages(b"\x89PNG", "image/png")

        assert result[0]["text"] == "hello world"

    def test_base64_encodes_file_bytes(self):
        import base64
        file_bytes = b"\x89PNG\r\n\x1a\n"
        with patch("app.rag.chunker.anthropic.Anthropic") as mock_cls:
            instance = mock_cls.return_value
            instance.messages.create.return_value = _mock_anthropic_response("x")
            extract_image_pages(file_bytes, "image/png")

        content = instance.messages.create.call_args.kwargs["messages"][0]["content"]
        image_block = next(b for b in content if b["type"] == "image")
        assert image_block["source"]["data"] == base64.standard_b64encode(file_bytes).decode()


class TestChunkDocxPagesWithImageOutput:
    """extract_image_pages output feeds directly into chunk_docx_pages."""

    def test_image_text_produces_parent_and_child_chunks(self):
        pages = [{"page": 0, "text": "Alpha. Beta. Gamma. Delta. Epsilon."}]
        chunks = chunk_docx_pages(pages)
        types = {c["type"] for c in chunks}
        assert "parent" in types
        assert "child" in types

    def test_empty_image_text_produces_no_chunks(self):
        pages = [{"page": 0, "text": "   "}]
        chunks = chunk_docx_pages(pages)
        assert chunks == []


class TestMakeChunks:
    def test_single_sentence_produces_parent_and_flush_child(self):
        chunks = _make_chunks("Hello world", 0)
        assert any(c["type"] == "parent" for c in chunks)
        assert any(c["type"] == "child" for c in chunks)

    def test_parent_id_prefix(self):
        chunks = _make_chunks("A. B. C.", 2, "doc_")
        parent = next(c for c in chunks if c["type"] == "parent")
        assert parent["id"].startswith("doc_parent_p2")
