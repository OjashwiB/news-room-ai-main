from langchain.tools import tool
from typing import Optional
import logging
import requests
from config.settings import settings

logger = logging.getLogger(__name__)


@tool
def web_research_tool(
    query: str,
    limit: Optional[int] = 5,
    search_depth: Optional[str] = "advanced",
) -> str:
    """
    Research a topic using real-time web search via Tavily.

    Args:
        query: The research query
        limit: Number of results to return (default 5)
        search_depth: "basic" or "advanced" (default "advanced")

    Returns:
        Formatted string of sources with titles, content excerpts, and URLs
    """
    if not settings.TAVILY_API_KEY:
        return "Error: TAVILY_API_KEY not configured."

    try:
        payload = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "search_depth": search_depth,
            "include_answer": True,
            "max_results": limit,
            "topic": "news",
        }
        response = requests.post(
            "https://api.tavily.com/search",
            json=payload,
            timeout=15,
        )

        if not response.ok:
            return f"Error: HTTP {response.status_code} from Tavily"

        data = response.json()
        results = data.get("results", [])

        if not results:
            return f"No results found for: {query}"

        lines = [f"Research results for: '{query}'\n"]
        for i, r in enumerate(results[:limit], 1):
            lines.append(
                f"{i}. {r.get('title', 'No title')}\n"
                f"   {r.get('content', '')[:400]}\n"
                f"   URL: {r.get('url', '')}\n"
            )

        if data.get("answer"):
            lines.insert(1, f"Summary: {data['answer']}\n")

        logger.info(f"[web_research_tool] {len(results)} results for: {query}")
        return "\n".join(lines)

    except requests.exceptions.Timeout:
        return "Error: Search request timed out"
    except Exception as e:
        logger.error(f"[web_research_tool] Error: {e}", exc_info=True)
        return f"Error: {str(e)}"
