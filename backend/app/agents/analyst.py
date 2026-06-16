import json
import logging
import os
import re
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from app.agents.state import AgentReportState

logger = logging.getLogger(__name__)
MODEL = "claude-sonnet-4-6"


def _build_prompt(state: AgentReportState) -> str:
    messages = state.get("messages") or []
    financials = "\n\n".join(state.get("retrieved_financials") or []) or "No document data available."
    news = "\n\n".join(state.get("market_news") or []) or "No market news available."
    feedback = f"\n\nCritic feedback:\n{state['critic_feedback']}" if state.get("critic_feedback") else ""

    if messages:
        user_question = messages[-1].content
        existing = json.dumps(state.get("financial_analysis") or {}, indent=2)
        return f"""You are a senior financial analyst. The user has a follow-up question about {state['company_name']} ({state['ticker']}).

Current report:
{existing}

Source data:
## Financial Documents
{financials}

## Market News
{news}

User question: {user_question}

Answer precisely. Update the report JSON if the answer changes any figures or analysis. Return ONLY the complete updated JSON with the same structure — no markdown, no prose outside JSON."""

    focus = ", ".join(state.get("focus_areas") or []) or "overall financial performance"
    return f"""You are a senior financial analyst. Analyse {state['company_name']} ({state['ticker']}).

Focus areas: {focus}

## Financial Document Extracts
{financials}

## Market News & Sentiment
{news}
{feedback}

Return ONLY a valid JSON object with this exact structure (no markdown, no prose outside JSON):
{{
  "executive_summary": "2-3 sentence summary of overall performance and outlook",
  "financial_metrics": {{
    "revenue_vnd_billions": <number or null>,
    "net_profit_vnd_billions": <number or null>,
    "margin_percentage": <number or null>
  }},
  "swot_analysis": {{
    "strengths": ["..."],
    "weaknesses": ["..."],
    "opportunities": ["..."],
    "threats": ["..."]
  }},
  "market_sentiment": "Bullish" | "Bearish" | "Neutral"
}}"""


def analyst_node(state: AgentReportState) -> dict:
    messages = state.get("messages") or []

    if not messages:
        # Initial mode — require fresh data from RAG / search
        if not state.get("retrieved_financials") and not state.get("market_news"):
            raise ValueError(
                f"No data available: document index is empty for ticker '{state['ticker']}' "
                "and web search returned 0 results. Please upload a financial document or verify the ticker symbol."
            )

    llm = ChatAnthropic(
        model=MODEL,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=2048,
    )

    prompt = _build_prompt(state)
    logger.info("Analyst: calling Claude ticker=%s iteration=%d chat=%s",
                state["ticker"], state.get("iterations", 0), bool(messages))

    response = llm.invoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)

    try:
        analysis = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Analyst: JSON parse failed — %s\nRaw: %s", exc, raw[:500])
        raise ValueError(f"Analyst produced invalid JSON: {exc}") from exc

    return {"financial_analysis": analysis}
