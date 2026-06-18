import fitz
import docx as python_docx


def extract_pages(doc: fitz.Document) -> list[dict]:
    pages = []
    for page_num, page in enumerate(doc):
        blocks = page.get_text("blocks")
        pages.append({"page": page_num, "blocks": blocks})
    return pages


def extract_docx_pages(file_bytes: bytes) -> list[dict]:
    """Extract text from a docx file, grouping paragraphs into page-like chunks."""
    import io
    doc = python_docx.Document(io.BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    # Group every 30 paragraphs as a synthetic "page" so parent-child chunking works
    page_size = 30
    pages = []
    for i in range(0, max(1, len(paragraphs)), page_size):
        group = paragraphs[i : i + page_size]
        pages.append({"page": i // page_size, "text": "\n".join(group)})
    return pages


def chunk_document(pages: list[dict]) -> list[dict]:
    """Chunk PDF pages (from extract_pages) into parent + child chunks."""
    chunks = []
    for page in pages:
        full_text = " ".join(b[4] for b in page["blocks"] if isinstance(b[4], str)).strip()
        if not full_text:
            continue
        chunks.extend(_make_chunks(full_text, page["page"]))
    return chunks


def chunk_docx_pages(pages: list[dict]) -> list[dict]:
    """Chunk docx synthetic pages (from extract_docx_pages) into parent + child chunks."""
    chunks = []
    for page in pages:
        full_text = page["text"].strip()
        if not full_text:
            continue
        chunks.extend(_make_chunks(full_text, page["page"]))
    return chunks


def _make_chunks(full_text: str, page_num: int, doc_prefix: str = "") -> list[dict]:
    parent_id = f"{doc_prefix}parent_p{page_num}" if doc_prefix else f"parent_p{page_num}"
    chunks = [{"id": parent_id, "text": full_text, "type": "parent", "page": page_num, "parent_id": parent_id}]

    sentences = [s.strip() for s in full_text.split(". ") if s.strip()]
    window: list[str] = []
    for i, sent in enumerate(sentences):
        window.append(sent)
        if len(window) == 3:
            chunks.append({
                "id": f"child_{parent_id}_{i}",
                "text": ". ".join(window),
                "type": "child",
                "parent_id": parent_id,
                "page": page_num,
            })
            window = window[1:]
    if window:
        chunks.append({
            "id": f"child_{parent_id}_flush",
            "text": ". ".join(window),
            "type": "child",
            "parent_id": parent_id,
            "page": page_num,
        })
    return chunks
