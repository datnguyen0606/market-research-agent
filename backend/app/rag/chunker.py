import fitz


def extract_pages(doc: fitz.Document) -> list[dict]:
    pages = []
    for page_num, page in enumerate(doc):
        blocks = page.get_text("blocks")
        pages.append({"page": page_num, "blocks": blocks})
    return pages


def chunk_document(pages: list[dict]) -> list[dict]:
    chunks = []
    for page in pages:
        full_text = " ".join(b[4] for b in page["blocks"] if isinstance(b[4], str)).strip()
        if not full_text:
            continue
        parent_id = f"parent_p{page['page']}"
        chunks.append({"id": parent_id, "text": full_text, "type": "parent", "page": page["page"]})

        sentences = [s.strip() for s in full_text.split(". ") if s.strip()]
        window: list[str] = []
        for i, sent in enumerate(sentences):
            window.append(sent)
            if len(window) == 3:
                child_text = ". ".join(window)
                chunks.append({
                    "id": f"child_{parent_id}_{i}",
                    "text": child_text,
                    "type": "child",
                    "parent_id": parent_id,
                    "page": page["page"],
                })
                window = window[1:]
        # flush remaining window
        if len(window) >= 1:
            child_text = ". ".join(window)
            chunks.append({
                "id": f"child_{parent_id}_flush",
                "text": child_text,
                "type": "child",
                "parent_id": parent_id,
                "page": page["page"],
            })
    return chunks
