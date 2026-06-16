import json
import logging
import os
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

INTENT_MODEL = "claude-haiku-4-5-20251001"
VALID_INTENTS = {"correction", "clarifying_question", "satisfied", "other"}

_PROMPT = """A user is chatting with an AI financial-analysis assistant after receiving a report. \
Classify their follow-up message into exactly one category:

- "correction": the user is pointing out an error or disputing a fact/number in the report.
- "clarifying_question": the user is asking for more detail, context, or explanation without disputing anything.
- "satisfied": the user is expressing approval, thanks, or closing the conversation.
- "other": none of the above apply (small talk, unrelated, ambiguous).

User message:
\"\"\"{message}\"\"\"

Return ONLY valid JSON — no markdown, no prose:
{{"intent": "<correction|clarifying_question|satisfied|other>"}}"""


def classify_chat_intent(message: str) -> dict:
    """
    Classify a chat follow-up into an implicit satisfaction signal using a cheap,
    fast model. Designed to run in a batch job, never in the hot chat path.
    """
    llm = ChatAnthropic(
        model=INTENT_MODEL,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=64,
    )

    response = llm.invoke([HumanMessage(content=_PROMPT.format(message=message))])
    raw = response.content.strip()

    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)

    try:
        result = json.loads(raw)
        intent = result.get("intent")
        if intent not in VALID_INTENTS:
            intent = "other"
        return {"intent": intent}
    except json.JSONDecodeError as exc:
        logger.error("Chat intent: JSON parse failed — %s", exc)
        return {"intent": "other"}
