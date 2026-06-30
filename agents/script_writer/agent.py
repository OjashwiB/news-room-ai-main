import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from agents.registry import BaseAgent, AgentInfo
from agents.script_writer.prompts import SCRIPT_WRITER_PROMPT
from tools.file_operations_tool import file_operations_tool
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


class Agent(BaseAgent):
    """Script Writer — converts a news article into a broadcast anchor script."""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.3, openai_api_key=settings.OPENAI_API_KEY)
        self.tools = [file_operations_tool]
        prompt = ChatPromptTemplate.from_messages([
            ("system", SCRIPT_WRITER_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        agent = create_openai_functions_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True, max_iterations=8)
        logger.info("Script Writer agent initialized")

    def get_info(self) -> AgentInfo:
        return AgentInfo(
            name="script_writer",
            display_name="Script Writer",
            description="Converts articles into broadcast-ready news anchor scripts",
            version="1.0.0",
            module_path="agents.script_writer.agent",
            parent_agent="executive_producer",
        )

    async def process_message(self, message: str, context: dict = None) -> dict:
        try:
            result = self.executor.invoke({"input": message, "chat_history": []})
            output = result.get("output", "")

            # Append the actual script text so downstream agents (anchor) can extract it
            # without re-regenerating from context.
            script_text = self._read_saved_script(output, message)
            if script_text:
                output = f"{output}\n\n=== SCRIPT ===\n{script_text}"
            else:
                logger.warning("[script_writer] Could not locate saved script file — anchor will receive no script content")

            return {"success": True, "response": output, "agent": "script_writer"}
        except Exception as e:
            logger.error(f"Script Writer error: {e}", exc_info=True)
            return {"success": False, "response": f"Script writing failed: {str(e)}", "agent": "script_writer"}

    def _read_saved_script(self, output: str, message: str = "") -> str | None:
        import re as _re
        from pathlib import Path as _Path

        # Build ordered list of directories to search.
        # The EP injects SAVE_DIR pointing to the per-run scripts folder — check it first.
        search_dirs: list[_Path] = []
        if message:
            m = _re.search(r'SAVE_DIR[:\s]+([^\n]+)', message, _re.IGNORECASE)
            if m:
                run_dir = _Path(m.group(1).strip())
                if run_dir.exists():
                    search_dirs.append(run_dir)

        # Also try the directory path the LLM mentions in its output message
        dir_match = _re.search(r'(?:directory|folder)[:\s]+[`\'"]?(\./output/[^\s`\'"]+)[`\'"]?', output, _re.IGNORECASE)
        if dir_match:
            lm_dir = _Path(dir_match.group(1).strip())
            if lm_dir.exists() and lm_dir not in search_dirs:
                search_dirs.append(lm_dir)

        # Global scripts dir as final fallback
        global_dir = _Path(settings.SCRIPTS_DIR)
        if global_dir.exists() and global_dir not in search_dirs:
            search_dirs.append(global_dir)

        if not search_dirs:
            return None

        # Try to match a filename mentioned in the LLM output
        fname = None
        for pattern in (
            r'`([\w\-\.]+\.md)`',
            r'"([\w\-\.]+\.md)"',
            r"'([\w\-\.]+\.md)'",
            r'filename\s+[`\'"]?([\w\-\.]+\.md)[`\'"]?',
        ):
            m = _re.search(pattern, output, _re.IGNORECASE)
            if m:
                fname = m.group(1)
                break

        for d in search_dirs:
            if fname:
                path = d / fname
                if path.exists():
                    try:
                        content = path.read_text(encoding="utf-8").strip()
                        logger.info(f"[script_writer] Appending script from {path}")
                        return content
                    except Exception as e:
                        logger.warning(f"[script_writer] Could not read {path}: {e}")
            # Fall back to most-recently-modified .md in this directory
            try:
                files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
                if files:
                    content = files[0].read_text(encoding="utf-8").strip()
                    logger.info(f"[script_writer] Appending most recent script: {files[0]}")
                    return content
            except Exception as e:
                logger.warning(f"[script_writer] Could not read latest script from {d}: {e}")

        return None
