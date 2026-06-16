import json
import logging
import os
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

JUDGE_MODEL = "claude-opus-4-8"
JUDGE_THRESHOLD = 0.7

_PROMPT = """You are a strict financial report quality evaluator. A junior analyst produced the report below using the source data provided. Score its quality objectively.

## Source Data Available to the Analyst

### Financial Document Extracts
{financials}

### Market News & Sentiment
{news}

## Generated Report
{report}

Score the report on four dimensions (0.0 = completely fails, 1.0 = excellent):

1. **factual_accuracy** — Do financial figures in the report match or reasonably derive from the source documents? Penalise invented numbers.
2. **logical_consistency** — Does the SWOT analysis logically follow from the financials and news? Are conclusions supported by the sources?
3. **completeness** — Are all sections substantive and specific? Penalise vague filler that could apply to any company.
4. **sentiment_alignment** — Does the market_sentiment label (Bullish/Bearish/Neutral) match the actual tone of the retrieved news?

Return ONLY valid JSON — no markdown, no prose:
{{
  "scores": {{
    "factual_accuracy": <0.0–1.0>,
    "logical_consistency": <0.0–1.0>,
    "completeness": <0.0–1.0>,
    "sentiment_alignment": <0.0–1.0>
  }},
  "overall": <weighted average>,
  "passed": <true if overall >= {threshold}>,
  "feedback": "<specific issues, or 'Passes all quality criteria' if passed>"
}}"""


def run_judge(
    ticker: str,
    retrieved_financials: list[str],
    market_news: list[str],
    report: dict,
) -> dict:
    """
    Evaluate a delivered report using claude-opus-4-8 as judge.
    Designed to run in a thread pool AFTER report delivery — never in the hot path.
    """
    financials = "\n\n".join(retrieved_financials) or "No document data was available."
    news = "\n\n".join(market_news) or "No market news was available."

    prompt = _PROMPT.format(
        financials=financials,
        news=news,
        report=json.dumps(report, indent=2),
        threshold=JUDGE_THRESHOLD,
    )

    llm = ChatAnthropic(
        model=JUDGE_MODEL,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=1024,
    )

    logger.info("Judge: evaluating report ticker=%s", ticker)
    response = llm.invoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)

    try:
        result = json.loads(raw)
        if "overall" not in result and "scores" in result:
            s = result["scores"]
            result["overall"] = round(sum(s.values()) / len(s), 3)
        result.setdefault("passed", result.get("overall", 0) >= JUDGE_THRESHOLD)
        logger.info("Judge: ticker=%s overall=%.2f passed=%s", ticker, result.get("overall", 0), result.get("passed"))
        return result
    except json.JSONDecodeError as exc:
        logger.error("Judge: JSON parse failed — %s", exc)
        return {
            "scores": {},
            "overall": 0.0,
            "passed": False,
            "feedback": f"Judge output could not be parsed: {exc}",
        }
