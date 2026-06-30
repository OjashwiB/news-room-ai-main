import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from agents.registry import BaseAgent, AgentInfo
from agents.writer.prompts import WRITER_PROMPT
from tools.file_operations_tool import file_operations_tool
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


class Agent(BaseAgent):
    """Writer — produces a polished news article from research material."""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.3, openai_api_key=settings.OPENAI_API_KEY)
        self.tools = [file_operations_tool]
        prompt = ChatPromptTemplate.from_messages([
            ("system", WRITER_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        agent = create_openai_functions_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True, max_iterations=8)
        logger.info("Writer agent initialized")

    def get_info(self) -> AgentInfo:
        return AgentInfo(
            name="writer",
            display_name="Writer",
            description="Writes news articles from research material",
            version="1.0.0",
            module_path="agents.writer.agent",
            parent_agent="executive_producer",
        )

    async def process_message(self, message: str, context: dict = None) -> dict:
        try:
            result = self.executor.invoke({"input": message, "chat_history": []})
            return {"success": True, "response": result.get("output", ""), "agent": "writer"}
        except Exception as e:
            logger.error(f"Writer error: {e}", exc_info=True)
            return {"success": False, "response": f"Writing failed: {str(e)}", "agent": "writer"}
