"""Built-in opt-in micro-tools for Tether."""

from __future__ import annotations

from tether.tools.agent import make_agent_tool
from tether.tools.bash import make_bash_tool
from tether.tools.done import make_done_tool
from tether.tools.edit import make_edit_tool
from tether.tools.mem import make_mem_tool
from tether.tools.web import make_web_tool

ALL_BUILTIN_TOOLS = ("bash", "web", "edit", "mem", "skill", "agent")

__all__ = [
    "ALL_BUILTIN_TOOLS",
    "make_agent_tool",
    "make_bash_tool",
    "make_done_tool",
    "make_edit_tool",
    "make_mem_tool",
    "make_web_tool",
]
