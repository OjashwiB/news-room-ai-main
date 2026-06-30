import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import re
import logging
import requests
from datetime import date
from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from agents.registry import BaseAgent, AgentInfo
from agents.fact_checker.prompts import FACT_CHECKER_PROMPT
from tools.web_research_tool import web_research_tool
from config.settings import settings

logger = logging.getLogger(__name__)

# Named political figures: "[Title] [Name]" or "[Country] [Title] [Name]"
_OFFICIAL_RE = re.compile(
    r'(?:(?:U\.S\.?|United\s+States|British|French|German|Russian|Chinese|'
    r'Canadian|Australian|Japanese|Israeli|Iranian|Saudi|South\s+Korean|'
    r'Indian|Brazilian|Mexican|Italian|Spanish)\s+)?'
    r'(?:former\s+)?'
    r'(?:President|Prime\s+Minister|Vice[\s-]President|Secretary(?:\s+of\s+State)?|'
    r'Secretary[-\s]General|Director(?:\s+General)?|Chancellor|Minister\s+of\s+\w+|'
    r'Senator|Governor|Speaker|CEO|Chairman|Chair(?:woman|man|person)?|Ambassador)'
    r'\s+(?:[A-Z][a-zA-Z\'-]+\s+){0,2}[A-Z][a-zA-Z\'-]+',
    re.IGNORECASE,
)


def _tavily_search(query: str) -> str:
    """Direct Tavily search — deterministic Python call, not via LLM tool."""
    if not settings.TAVILY_API_KEY:
        return "TAVILY_API_KEY not configured"
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "max_results": 3,
                "topic": "news",
            },
            timeout=15,
        )
        if not resp.ok:
            return f"Search failed: HTTP {resp.status_code}"
        data = resp.json()
        lines = []
        if data.get("answer"):
            lines.append(f"Summary: {data['answer']}")
        for r in data.get("results", [])[:3]:
            snippet = r.get("content", "")[:200].replace("\n", " ")
            lines.append(f"• {r.get('title', '')}: {snippet}")
        return "\n".join(lines) if lines else "No results"
    except Exception as e:
        return f"Search error: {e}"


def _extract_article_text(message: str) -> str:
    for marker in ("WRITER OUTPUT",):
        m = re.search(
            rf'=== {re.escape(marker)} ===\s*(.*?)(?:===|\Z)',
            message, re.DOTALL | re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    return message


class Agent(BaseAgent):
    """Fact Checker — runs Tavily title verification before LLM review of the article."""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.0, openai_api_key=settings.OPENAI_API_KEY)
        self.tools = [web_research_tool]
        prompt = ChatPromptTemplate.from_messages([
            ("system", FACT_CHECKER_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        agent = create_openai_functions_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True, max_iterations=15)
        logger.info("Fact Checker agent initialized")

    def get_info(self) -> AgentInfo:
        return AgentInfo(
            name="fact_checker",
            display_name="Fact Checker",
            description="Verifies factual claims in draft articles before script production",
            version="2.0.0",
            module_path="agents.fact_checker.agent",
            parent_agent="executive_producer",
        )

    async def process_message(self, message: str, context: dict = None) -> dict:
        try:
            today = date.today().strftime("%B %d, %Y")
            year = date.today().year

            # ── Pre-run Tavily searches for every named official in the article ──
            article_text = _extract_article_text(message)
            officials = list(dict.fromkeys(
                m.group(0) for m in _OFFICIAL_RE.finditer(article_text)
            ))

            preamble_lines = [f"TODAY'S DATE: {today}\n"]

            if officials:
                logger.info(f"[Fact Checker] Pre-running Tavily title checks for {len(officials)} official(s)")
                preamble_lines.append(
                    "PRE-RUN TAVILY TITLE VERIFICATION:\n"
                    "The following named officials appear in the article. "
                    "Live Tavily searches were run for each to verify their current title. "
                    "Use these results in your VERIFIED / CORRECTIONS NEEDED sections.\n"
                )
                for ref in officials[:8]:  # cap at 8 to keep input manageable
                    # Build a search query from the reference
                    query = f"{ref} current role title {year}"
                    logger.info(f"[Fact Checker] Tavily: {query!r}")
                    result = _tavily_search(query)
                    preamble_lines.append(f"ARTICLE SAYS: \"{ref}\"")
                    preamble_lines.append(f"TAVILY RESULT: {result}")
                    preamble_lines.append("")
                preamble_lines.append(
                    "Now fact-check the full article using the Tavily results above "
                    "plus any additional web_research_tool calls you need.\n"
                )

            augmented_input = "\n".join(preamble_lines) + "\n" + message
            result = self.executor.invoke({"input": augmented_input, "chat_history": []})
            output = result.get("output", "")

            verdict = "UNKNOWN"
            for line in output.splitlines():
                line = line.strip()
                if "CLEAR TO PUBLISH" in line:
                    verdict = "CLEAR TO PUBLISH"
                    break
                elif "PUBLISH WITH NOTES" in line:
                    verdict = "PUBLISH WITH NOTES"
                    break
                elif "HOLD FOR CORRECTIONS" in line:
                    verdict = "HOLD FOR CORRECTIONS"
                    break

            logger.info(f"[Fact Checker] Verdict: {verdict}")
            return {
                "success": True,
                "response": output,
                "verdict": verdict,
                "agent": "fact_checker",
            }
        except Exception as e:
            logger.error(f"Fact Checker error: {e}", exc_info=True)
            return {
                "success": False,
                "response": f"Fact checking failed: {str(e)}",
                "verdict": "ERROR",
                "agent": "fact_checker",
            }
