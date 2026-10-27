"""Register every parser; a new parser module is added to `ALL` here."""

from __future__ import annotations

from .agent_zero import AgentZeroParser
from .aider import AiderParser
from .antigravity import AntigravityParser
from .base import Options, Parser
from .chatgpt_desktop import ChatGptDesktopParser
from .claude_code import ClaudeCodeParser
from .claude_desktop import ClaudeDesktopParser
from .cline import ClineParser
from .codex import CodexParser
from .cody import CodyParser
from .continue_dev import ContinueParser
from .copilot_cli import CopilotCliParser
from .copilot_desktop import CopilotDesktopParser
from .crush import CrushParser
from .cursor import CursorParser
from .gemini_cli import GeminiCliParser
from .goose import GooseParser
from .hermes import HermesParser
from .kilo_code import KiloCodeParser
from .kiro import KiroParser
from .letta import LettaParser
from .little_coder import LittleCoderParser
from .muse_code import MuseCodeParser
from .nanobot import NanobotParser
from .ollama import OllamaParser
from .open_interpreter import OpenInterpreterParser
from .openclaw import OpenClawParser
from .opencode import OpenCodeParser
from .openhands import OpenHandsParser
from .pearai import PearAiParser
from .pi import PiParser
from .qwen_code import QwenCodeParser
from .roo_code import RooCodeParser
from .shellgpt import ShellGptParser
from .tabby import TabbyParser
from .twinny import TwinnyParser
from .vscode import VsCodeParser
from .zed import ZedParser

ALL: list[Parser] = [
    ClaudeCodeParser(),
    ClaudeDesktopParser(),
    CodexParser(),
    AntigravityParser(),
    QwenCodeParser(),
    KiroParser(),
    GeminiCliParser(),
    CrushParser(),
    GooseParser(),
    ContinueParser(),
    AiderParser(),
    ZedParser(),
    VsCodeParser(),
    OpenCodeParser(),
    KiloCodeParser(),
    ClineParser(),
    RooCodeParser(),
    TabbyParser(),
    OpenHandsParser(),
    ShellGptParser(),
    PiParser(),
    LittleCoderParser(),
    LettaParser(),
    HermesParser(),
    AgentZeroParser(),
    OpenInterpreterParser(),
    OpenClawParser(),
    NanobotParser(),
    CodyParser(),
    TwinnyParser(),
    PearAiParser(),
    MuseCodeParser(),
    OllamaParser(),
    CopilotCliParser(),
    CopilotDesktopParser(),
    ChatGptDesktopParser(),
    CursorParser(),
]


# Catalog agents whose collected files hold nothing to parse: the `collected`
# rows of the table in docs/agents.md at the repository root, which a test
# keeps equal to this set. The analyzer reports them as "collected only", not
# as a backlog.
NO_TRANSCRIPTS: frozenset[str] = frozenset(
    {
        "camel-ai",  # an OAuth token and config; chat history is under the working directory
        "copilot",  # the language server's OAuth token store; Copilot Chat parses as vscode
        "metagpt",  # LLM configuration only; its workspace is under the working directory
        "shared",  # cross-agent instruction and skill directories
    }
)


def by_agent() -> dict[str, list[Parser]]:
    """Return the registered parsers by their agent name."""
    parsers: dict[str, list[Parser]] = {}
    for parser in ALL:
        parsers.setdefault(parser.agent, []).append(parser)
    return parsers


__all__ = ["ALL", "NO_TRANSCRIPTS", "Options", "Parser", "by_agent"]
