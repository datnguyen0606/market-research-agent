from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ResearchState(TypedDict):
    # Input
    query: str
    # Router output — Exa sub-queries (empty = skip web search)
    search_queries: list[str]
    # Retrieval results
    retrieved_docs: list[str]
    web_results: list[dict[str, Any]]   # [{title, url, text, highlights}]
    # Chat history — add_messages reducer merges across checkpoints
    messages: Annotated[list[BaseMessage], add_messages]
    # Output
    answer: Optional[str]
    sources: list[dict[str, Any]]       # [{title, url, snippet}]
    grounding_passed: bool
