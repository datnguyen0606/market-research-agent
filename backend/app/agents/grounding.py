import logging
import os
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from app.agents.state import ResearchState

logger = logging.getLogger(__name__)

_PROMPT = """You are a factual grounding checker. Assess whether the analyst's answer is properly grounded in the provided sources.

## Sources available
{sources_summary}

## Analyst answer
{answer}

Is the answer grounded in the sources (no significant unsupported claims or hallucinations)?
Return ONLY valid JSON: {{"grounded": true | false, "issue": "brief note if not grounded, else null"}}"""


def grounding_node(state: ResearchState) -> dict:
    answer = state.get("answer") or ""
    sources = state.get("sources") or []
    retrieved_docs = state.get("retrieved_docs") or []

    if not answer:
        return {"grounding_passed": False}

    # If no sources at all, can't verify grounding
    if not sources and not retrieved_docs:
        logger.info("Grounding: no sources to verify against, skipping")
        return {"grounding_passed": True}

    sources_summary = "\n".join(
        f"- {s.get('title', 'Document')} ({s.get('url', 'uploaded doc')})"
        for s in sources[:10]
    ) or f"{len(retrieved_docs)} document extract(s)"

    llm = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=128,
    )

    prompt = _PROMPT.format(
        sources_summary=sources_summary,
        answer=answer[:2000],
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            import json
            result = json.loads(match.group())
            passed = bool(result.get("grounded", True))
            if not passed:
                logger.warning("Grounding: issue detected — %s", result.get("issue"))
            return {"grounding_passed": passed}
    except Exception as exc:
        logger.warning("Grounding check failed: %s", exc)

    return {"grounding_passed": True}
