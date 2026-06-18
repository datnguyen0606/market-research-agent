import logging
import os

from exa_py import Exa

from app.agents.state import ResearchState

logger = logging.getLogger(__name__)


def web_search_node(state: ResearchState) -> dict:
    search_queries = state.get("search_queries") or []
    if not search_queries:
        logger.info("Web search: no queries from router, skipping")
        return {"web_results": []}

    try:
        client = Exa(api_key=os.getenv("EXA_API_KEY"))
    except Exception as exc:
        logger.warning("Web search: failed to initialise Exa client — %s", exc, exc_info=True)
        return {"web_results": []}

    all_results: list[dict] = []
    seen_urls: set[str] = set()

    for query in search_queries:
        logger.info("Web search: Exa query=%r", query[:80])
        try:
            response = client.search_and_contents(
                query,
                type="auto",
                num_results=5,
                text={"max_characters": 1500},
                highlights={"num_sentences": 3, "highlights_per_url": 2},
            )
            for r in response.results:
                if r.url in seen_urls:
                    continue
                seen_urls.add(r.url)
                all_results.append({
                    "title": r.title or "",
                    "url": r.url or "",
                    "text": r.text or "",
                    "highlights": r.highlights or [],
                })
        except Exception as exc:
            logger.warning("Web search: Exa query failed query=%r — %s", query[:60], exc)

    logger.info("Web search: collected %d unique results", len(all_results))
    return {"web_results": all_results}
