from typing import Dict, Optional, List, Any
import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AgentInfo:
    name: str
    display_name: str
    description: str
    version: str
    module_path: str
    enabled: bool = True
    parent_agent: Optional[str] = None
    manages_agents: Optional[List[str]] = field(default_factory=list)


class BaseAgent(ABC):
    @abstractmethod
    def get_info(self) -> AgentInfo:
        pass

    @abstractmethod
    async def process_message(self, message: str, context: dict = None) -> dict:
        pass


class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._loaded_agents: Dict[str, BaseAgent] = {}
        self._register_agents()

    def _register_agents(self):
        self.register_agent(AgentInfo(
            name="executive_producer",
            display_name="Executive Producer",
            description="Orchestrates the full news production workflow",
            version="1.0.0",
            module_path="agents.executive_producer.agent",
            parent_agent=None,
            manages_agents=["researcher", "writer", "fact_checker", "editor", "script_writer", "anchor", "video_editor", "producer", "publisher"],
        ))
        self.register_agent(AgentInfo(
            name="researcher",
            display_name="Researcher",
            description="Researches topics using web search and compiles source material",
            version="1.0.0",
            module_path="agents.researcher.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="writer",
            display_name="Writer",
            description="Writes news articles from research material",
            version="1.0.0",
            module_path="agents.writer.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="fact_checker",
            display_name="Fact Checker",
            description="Verifies factual claims in draft articles before script production",
            version="1.0.0",
            module_path="agents.fact_checker.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="editor",
            display_name="Editor",
            description="Applies fact-check corrections and verifies current titles/status before script production",
            version="1.0.0",
            module_path="agents.editor.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="script_writer",
            display_name="Script Writer",
            description="Converts articles into broadcast-ready news anchor scripts",
            version="1.0.0",
            module_path="agents.script_writer.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="anchor",
            display_name="Anchor",
            description="Generates AI news anchor video from broadcast script using HeyGen",
            version="1.0.0",
            module_path="agents.anchor.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="video_editor",
            display_name="Video Editor",
            description="Downloads anchor video, extracts graphic cues, builds video package",
            version="1.0.0",
            module_path="agents.video_editor.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="producer",
            display_name="Producer",
            description="Confirms output files and compiles production summary",
            version="1.0.0",
            module_path="agents.producer.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="publisher",
            display_name="Publisher",
            description="Uploads finished video to YouTube and sets title, description, thumbnail",
            version="1.0.0",
            module_path="agents.publisher.agent",
            parent_agent="executive_producer",
        ))
        self.register_agent(AgentInfo(
            name="breaking_news_checker",
            display_name="Breaking News Checker",
            description="Monitors current headlines and triggers emergency productions for qualifying breaking news",
            version="1.0.0",
            module_path="agents.breaking_news_checker.agent",
            parent_agent=None,
        ))

    def register_agent(self, agent_info: AgentInfo):
        self._agents[agent_info.name] = agent_info
        print(f"Registered agent: {agent_info.name}")

    def get_agent_info(self, name: str) -> Optional[AgentInfo]:
        return self._agents.get(name)

    def list_agents(self) -> Dict[str, AgentInfo]:
        return {n: i for n, i in self._agents.items() if i.enabled}

    async def get_agent(self, name: str) -> Optional[BaseAgent]:
        if name not in self._agents or not self._agents[name].enabled:
            return None
        if name not in self._loaded_agents:
            try:
                module = importlib.import_module(self._agents[name].module_path)
                self._loaded_agents[name] = module.Agent()
            except Exception as e:
                print(f"Error loading agent {name}: {e}")
                return None
        return self._loaded_agents.get(name)


agent_registry = AgentRegistry()
