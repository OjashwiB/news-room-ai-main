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
from agents.editor.prompts import EDITOR_PROMPT
from tools.web_research_tool import web_research_tool
from tools.file_operations_tool import file_operations_tool
from config.settings import settings

logger = logging.getLogger(__name__)

# Matches "former [optional country adjective] [title] [Name]"
_FORMER_RE = re.compile(
    r'former\s+'
    r'(?:(?:U\.S\.?|United\s+States|British|French|German|Russian|Chinese|'
    r'Canadian|Australian|Japanese|Israeli|Iranian|Saudi|South\s+Korean|'
    r'Indian|Brazilian|Mexican|Italian|Spanish)\s+)?'
    r'(?:President|Prime\s+Minister|Vice[\s-]President|Secretary(?:\s+of\s+State)?|'
    r'Secretary[-\s]General|Director(?:\s+General)?|Chancellor|Minister|Senator|'
    r'Governor|Speaker|CEO|Chairman|Chair(?:woman|man|person)?|Ambassador|'
    r'General|Admiral|Commissioner)'
    r'(?:\s+[A-Z][a-zA-Z\'-]+){1,4}',
    re.IGNORECASE,
)

# Extracts just the name portion from a "former ... [Name]" string
_NAME_RE = re.compile(
    r'former\s+(?:(?:U\.S\.?|United\s+States|British|French|German|Russian|Chinese|'
    r'Canadian|Australian|Japanese|Israeli|Iranian|Saudi|South\s+Korean|'
    r'Indian|Brazilian|Mexican|Italian|Spanish)\s+)?'
    r'(?:President|Prime\s+Minister|Vice[\s-]President|Secretary(?:\s+of\s+State)?|'
    r'Secretary[-\s]General|Director(?:\s+General)?|Chancellor|Minister|Senator|'
    r'Governor|Speaker|CEO|Chairman|Chair(?:woman|man|person)?|Ambassador|'
    r'General|Admiral|Commissioner)\s+',
    re.IGNORECASE,
)


def _tavily_search(query: str) -> str:
    """Direct Tavily search — called deterministically in Python, not via LLM tool."""
    if not settings.TAVILY_API_KEY:
        return "TAVILY_API_KEY not configured — cannot verify"
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
            snippet = r.get("content", "")[:250].replace("\n", " ")
            lines.append(f"• {r.get('title', '')}: {snippet}")
        return "\n".join(lines) if lines else "No results returned"
    except Exception as e:
        return f"Search error: {e}"


def _extract_article_text(message: str) -> str:
    """Pull article text from the pipeline context block."""
    for marker in ("EDITOR OUTPUT", "WRITER OUTPUT"):
        m = re.search(
            rf'=== {re.escape(marker)} ===\s*(.*?)(?:===|\Z)',
            message, re.DOTALL | re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    return message


class Agent(BaseAgent):
    """Editor — verifies titles via Tavily, applies fact-check corrections, produces clean article."""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.1, openai_api_key=settings.OPENAI_API_KEY)
        self.tools = [web_research_tool, file_operations_tool]
        prompt = ChatPromptTemplate.from_messages([
            ("system", EDITOR_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        agent = create_openai_functions_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True, max_iterations=15)
        logger.info("Editor agent initialized")

    def get_info(self) -> AgentInfo:
        return AgentInfo(
            name="editor",
            display_name="Editor",
            description="Verifies titles via Tavily, applies fact-check corrections before script production",
            version="2.0.0",
            module_path="agents.editor.agent",
            parent_agent="executive_producer",
        )

    async def process_message(self, message: str, context: dict = None) -> dict:
        try:
            today = date.today().strftime("%B %d, %Y")
            year = date.today().year

            # ── Step 1: Find every "former [title] [Name]" in the article ──
            article_text = _extract_article_text(message)
            former_matches = list(dict.fromkeys(
                m.group(0) for m in _FORMER_RE.finditer(article_text)
            ))

            preamble_lines = [f"TODAY'S DATE: {today}\n"]

            if former_matches:
                logger.info(f"[Editor] {len(former_matches)} 'former' reference(s) found — running Tavily verification")
                preamble_lines.append(
                    "🚨 TAVILY-VERIFIED TITLE CHECK — READ THIS FIRST:\n"
                    "The following 'former [title]' phrases appear in the article. "
                    "A Tavily search was run for each one right now. "
                    "The results are below. If a person is currently in office, "
                    "their 'former' label is WRONG and must be corrected.\n"
                )
                for ref in former_matches:
                    # Extract name by stripping the "former [title]" prefix
                    name = _NAME_RE.sub("", ref).strip()
                    query = f"{name} current title position role {year}"
                    logger.info(f"[Editor] Tavily search: {query!r}")
                    result = _tavily_search(query)
                    preamble_lines.append(f"PHRASE: \"{ref}\"")
                    preamble_lines.append(f"SEARCH QUERY: {query}")
                    preamble_lines.append(f"TAVILY RESULT:\n{result}")
                    preamble_lines.append("")

                preamble_lines.append(
                    "Based on the Tavily results above, correct any 'former' labels "
                    "that are wrong. Then proceed with other fact-check corrections below.\n"
                )
            else:
                preamble_lines.append("No 'former [title]' references detected in the article.\n")

            augmented_input = "\n".join(preamble_lines) + "\n" + message
            result = self.executor.invoke({"input": augmented_input, "chat_history": []})
            return {"success": True, "response": result.get("output", ""), "agent": "editor"}

        except Exception as e:
            logger.error(f"Editor error: {e}", exc_info=True)
            return {"success": False, "response": f"Editing failed: {str(e)}", "agent": "editor"}
