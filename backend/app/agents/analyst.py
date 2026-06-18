import logging
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from app.agents.state import ResearchState

logger = logging.getLogger(__name__)
MODEL = "claude-sonnet-4-6"

_SYSTEM = """You are a financial research analyst with access to a document knowledge base and live web search results.

Answer the user's query accurately and comprehensively. Ground every claim in the provided sources. When referencing a source, include a brief inline citation like [Source: document name or article title].

Format your answer in clear markdown — use headings, bullet points, and bold text where appropriate. Be specific and data-driven. If the sources don't contain enough information to answer confidently, say so explicitly rather than speculating."""


def analyst_node(state: ResearchState) -> dict:
    messages = state.get("messages") or []
    query = state["query"]
    retrieved_docs = state.get("retrieved_docs") or []
    web_results = state.get("web_results") or []

    # For chat follow-ups, use the last user message as the actual question
    if messages:
        query = messages[-1].content

    if not retrieved_docs and not web_results:
        return {
            "answer": "I couldn't find relevant information in the uploaded documents or from web search to answer your question. Try uploading relevant documents in the Document Upload tab, or rephrase your query.",
            "sources": [],
        }

    # Build source context
    doc_context = ""
    if retrieved_docs:
        doc_context = "## Uploaded Document Extracts\n\n" + "\n\n---\n\n".join(retrieved_docs)

    web_context = ""
    web_sources = []
    if web_results:
        web_lines = []
        for r in web_results:
            title = r.get("title", "Web result")
            url = r.get("url", "")
            text = r.get("text", r.get("highlights", ""))
            if isinstance(text, list):
                text = " ".join(text)
            web_lines.append(f"**{title}**\nURL: {url}\n{text[:1200]}")
            web_sources.append({"title": title, "url": url, "snippet": text[:300]})
        web_context = "## Web Search Results\n\n" + "\n\n---\n\n".join(web_lines)

    prompt = f"""{doc_context}

{web_context}

## User Query

{query}"""

    llm = ChatAnthropic(
        model=MODEL,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=3000,
    )

    logger.info("Analyst: generating answer for query=%r", query[:80])
    response = llm.invoke([
        HumanMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])
    answer = response.content.strip()

    # Collect document sources from retrieved chunks (filename from parent blocks)
    doc_sources = []
    for doc_text in retrieved_docs:
        # Source info is prepended by document_rag_node as a header line
        first_line = doc_text.split("\n")[0]
        if first_line.startswith("Source:"):
            doc_sources.append({"title": first_line[7:].strip(), "url": "", "snippet": ""})

    sources = doc_sources + web_sources
    return {"answer": answer, "sources": sources}
