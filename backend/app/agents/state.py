from typing import Any, Optional
from typing_extensions import TypedDict


class AgentReportState(TypedDict):
    # Input
    company_name: str
    ticker: str
    raw_query: str
    focus_areas: list[str]
    # Intermediate
    retrieved_financials: list[str]
    market_news: list[str]
    financial_analysis: dict[str, Any]
    # Control flow
    critic_feedback: Optional[str]
    iterations: int
    is_approved: bool
    # Output
    final_report_json: Optional[dict[str, Any]]
