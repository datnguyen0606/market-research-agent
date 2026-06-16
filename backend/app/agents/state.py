from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


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
    # Chat history — add_messages reducer merges lists across checkpoints
    messages: Annotated[list[BaseMessage], add_messages]
    # Control flow
    critic_feedback: Optional[str]
    iterations: int
    is_approved: bool
    # Output
    final_report_json: Optional[dict[str, Any]]
