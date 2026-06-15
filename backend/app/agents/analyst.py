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
    financials = "\n\n".join(state["retrieved_financials"]) or "No document data available."
    news = "\n\n".join(state["market_news"]) or "No market news available."
    focus = ", ".join(state["focus_areas"]) or "overall financial performance"
    feedback = f"\n\nCritic feedback from previous attempt:\n{state['critic_feedback']}" if state.get("critic_feedback") else ""

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
    if not state["retrieved_financials"] and not state["market_news"]:
        raise ValueError(
            "No data available: document index is empty for ticker "
            f"'{state['ticker']}' and web search returned 0 results. "
            "Please upload a financial document or verify the ticker symbol."
        )

    llm = ChatAnthropic(
        model=MODEL,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=2048,
    )

    prompt = _build_prompt(state)
    logger.info("Analyst: calling Claude for ticker=%s (iteration %d)", state["ticker"], state["iterations"])

    response = llm.invoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    # Extract JSON if wrapped in markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)

    try:
        analysis = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Analyst: JSON parse failed — %s\nRaw: %s", exc, raw[:500])
        raise ValueError(f"Analyst produced invalid JSON: {exc}") from exc

    return {"financial_analysis": analysis}
