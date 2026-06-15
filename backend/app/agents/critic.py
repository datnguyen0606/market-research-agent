import logging
from app.agents.state import AgentReportState

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["executive_summary", "financial_metrics", "swot_analysis", "market_sentiment"]
SWOT_KEYS = ["strengths", "weaknesses", "opportunities", "threats"]
VALID_SENTIMENTS = {"Bullish", "Bearish", "Neutral"}


def _validate(analysis: dict) -> list[str]:
    issues = []
    for field in REQUIRED_FIELDS:
        if field not in analysis or analysis[field] is None:
            issues.append(f"Missing required field: {field}")

    fm = analysis.get("financial_metrics") or {}
    if not isinstance(fm, dict):
        issues.append("financial_metrics must be an object")

    swot = analysis.get("swot_analysis") or {}
    if isinstance(swot, dict):
        for key in SWOT_KEYS:
            items = swot.get(key)
            if not isinstance(items, list) or len(items) == 0:
                issues.append(f"swot_analysis.{key} must be a non-empty list")
    else:
        issues.append("swot_analysis must be an object")

    sentiment = analysis.get("market_sentiment", "")
    if sentiment not in VALID_SENTIMENTS:
        issues.append(f"market_sentiment must be one of {VALID_SENTIMENTS}, got: {sentiment!r}")

    return issues


def critic_node(state: AgentReportState) -> dict:
    analysis = state.get("financial_analysis") or {}
    iterations = state.get("iterations", 0) + 1
    issues = _validate(analysis)

    if not issues:
        logger.info("Critic: approved on iteration %d", iterations)
        return {
            "is_approved": True,
            "iterations": iterations,
            "critic_feedback": None,
            "final_report_json": {**analysis, "critic_iterations": iterations},
        }

    logger.warning("Critic: %d issues on iteration %d: %s", len(issues), iterations, issues)

    if iterations >= 3:
        logger.warning("Critic: max iterations reached, delivering best available result")
        return {
            "is_approved": False,
            "iterations": iterations,
            "critic_feedback": None,
            "final_report_json": {**analysis, "critic_iterations": iterations},
        }

    feedback = "Please fix the following issues:\n" + "\n".join(f"- {i}" for i in issues)
    return {
        "is_approved": False,
        "iterations": iterations,
        "critic_feedback": feedback,
        "final_report_json": None,
    }
