import json
import logging
import os
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from app.agents.state import ResearchState

logger = logging.getLogger(__name__)

_PROMPT = """You are the routing layer of a financial research assistant.

Analyse the user's query and decide whether the answer needs live web search. If it does, generate 1–3 focused Exa search queries that will surface the most relevant recent information.

User query: {query}

Return ONLY valid JSON — no markdown, no prose:
{{
  "needs_web_search": true | false,
  "search_queries": ["query 1", "query 2"]   // empty list if needs_web_search is false
}}

Guidance:
- needs_web_search = true for: rankings, recent news, current market data, comparisons across companies not in uploaded docs, anything time-sensitive.
- needs_web_search = false for: questions about uploaded documents, general financial concepts, historical analysis already in context.
- Keep search queries specific and information-dense (include year, sector, metric where relevant).
- Maximum 3 search queries."""


def router_node(state: ResearchState) -> dict:
    messages = state.get("messages") or []

    if messages:
        # Chat follow-up — skip search, re-use existing retrieved context
        logger.info("Router: chat follow-up, skipping search")
        return {"search_queries": []}

    query = state["query"]
    logger.info("Router: analysing query for search strategy")

    llm = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=256,
    )
    response = llm.invoke([HumanMessage(content=_PROMPT.format(query=query))])
    raw = response.content.strip()

    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)

    try:
        result = json.loads(raw)
        queries = result.get("search_queries", []) if result.get("needs_web_search") else []
        logger.info("Router: needs_web=%s queries=%d", result.get("needs_web_search"), len(queries))
        return {"search_queries": queries}
    except json.JSONDecodeError:
        logger.warning("Router: JSON parse failed, defaulting to 1 web search")
        return {"search_queries": [query]}
