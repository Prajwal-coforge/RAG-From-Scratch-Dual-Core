"""A Deep Agents harness with the framework's own tools removed or blocked.

create_deep_agent adds filesystem tools (ls, read_file, write_file,
edit_file, delete, glob, grep), a shell tool (execute), and a
general-purpose subagent that inherits all of them. The controls:

1. A harness profile, registered under the provider the framework resolves
   for the model, excludes every filesystem and shell tool and disables the
   general-purpose subagent. If it does not resolve, the default subagent
   appears and check 4 refuses the agent.
2. The filesystem middleware is replaced, in the main agent and in every
   subagent, by one that registers only read_file, which the framework
   requires. Its backend is the default per-run in-memory state, not the
   host filesystem, and a deny rule covers every path.
3. RunGuard, in every graph, hides tools outside the allowlist from the
   model, rejects calls to them before they run, and enforces the shared
   tool-call and time budget.
4. After compiling, the tool executors of the main agent and each subagent
   are read back and the agent is refused if anything else is registered.

Subagents are built without the subagent middleware, so they cannot
delegate: delegation depth is one. No checkpointer or store is passed, so
nothing persists between runs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from deepagents import (
    FilesystemMiddleware,
    FilesystemPermission,
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_ollama import ChatOllama

FRAMEWORK_TOOLS = frozenset({"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"})
REQUIRED_BY_FRAMEWORK = frozenset({"read_file"})
DELEGATION_TOOL = "task"
PROVIDER = "ollama"
DENY_ALL_FILES = [FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="deny")]


class UnsafeAgent(RuntimeError):
    pass


@dataclass
class Budget:
    """Per-run limits and trace, shared by the main agent and its subagents."""

    max_tool_calls: int
    time_limit_s: float
    max_delegations: int
    started: float = field(default_factory=time.monotonic)
    calls: list[dict] = field(default_factory=list)
    refusals: list[dict] = field(default_factory=list)
    cancelled: bool = False

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.started

    def refusal(self, name: str) -> str | None:
        if self.cancelled or self.elapsed_s >= self.time_limit_s:
            return f"time limit of {self.time_limit_s:.0f} s reached"
        if len(self.calls) >= self.max_tool_calls:
            return f"tool-call budget of {self.max_tool_calls} used"
        if name == DELEGATION_TOOL and sum(c["tool"] == DELEGATION_TOOL for c in self.calls) >= self.max_delegations:
            return f"delegation budget of {self.max_delegations} used"
        return None


class RunGuard(AgentMiddleware):
    """Allowlist and budget enforcement at the model and tool-call boundaries."""

    def __init__(self, allowed: set[str], budget: Budget, scope: str) -> None:
        super().__init__()
        self.allowed = frozenset(allowed)
        self.budget = budget
        self.scope = scope

    @property
    def name(self) -> str:
        return f"RunGuard[{self.scope}]"

    def wrap_model_call(self, request, handler):
        return handler(request.override(tools=[t for t in request.tools if _tool_name(t) in self.allowed]))

    def wrap_tool_call(self, request, handler):
        call = request.tool_call
        reason = None if call["name"] in self.allowed else "tool is not on the allowlist"
        reason = reason or self.budget.refusal(call["name"])
        if reason:
            self.budget.refusals.append({"scope": self.scope, "tool": call["name"], "args": call.get("args"), "reason": reason})
            return ToolMessage(content=f"Refused: {reason}. Answer from the evidence already gathered.",
                               tool_call_id=call["id"], name=call["name"], status="error")
        started = time.monotonic()
        record = {"scope": self.scope, "tool": call["name"], "args": call.get("args"), "started_s": round(self.budget.elapsed_s, 2)}
        self.budget.calls.append(record)
        try:
            result = handler(request)
        except Exception as exc:  # a failed tool is reported, not hidden
            record.update(outcome="error", error=f"{type(exc).__name__}: {exc}", duration_ms=round((time.monotonic() - started) * 1000, 1))
            return ToolMessage(content=f"Tool failed: {type(exc).__name__}: {exc}", tool_call_id=call["id"], name=call["name"], status="error")
        failed = getattr(result, "status", None) == "error"
        record.update(outcome="error" if failed else "ok", duration_ms=round((time.monotonic() - started) * 1000, 1))
        if failed:
            record["error"] = str(result.content)[:300]
        return result


def _tool_name(tool) -> str | None:
    return tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)


def lock_down_provider(model) -> str:
    """Register the lockdown profile under the provider the framework will resolve for this model."""
    from deepagents._models import get_model_provider

    provider = get_model_provider(model) or PROVIDER
    register_harness_profile(
        provider,
        HarnessProfile(
            excluded_tools=FRAMEWORK_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    return provider


def local_model(lock: dict, *, timeout_s: float) -> ChatOllama:
    """The pinned local chat model. There is no fallback to any hosted model."""
    return ChatOllama(
        model=lock["chat"]["model"],
        base_url=lock["ollama_url"].rstrip("/"),
        temperature=0,
        seed=7,
        num_ctx=8192,
        num_predict=1024,
        reasoning=False,
        client_kwargs={"timeout": timeout_s},
    )


def minimal_files() -> FilesystemMiddleware:
    return FilesystemMiddleware(tools=["read_file"], _permissions=DENY_ALL_FILES)


def tool_executor_names(graph) -> set[str]:
    node = graph.nodes.get("tools")
    return set(node.bound.tools_by_name) if node is not None else set()


def subagent_graphs(agent) -> dict[str, object]:
    """The compiled subagent graphs registered behind the task tool."""
    task = agent.nodes["tools"].bound.tools_by_name.get(DELEGATION_TOOL) if "tools" in agent.nodes else None
    graphs: dict[str, object] = {}
    if task is None:
        return graphs
    for fn in (task.func, task.coroutine):
        for cell in (getattr(fn, "__closure__", None) or ()):
            value = cell.cell_contents
            if isinstance(value, dict) and value and all(hasattr(v, "nodes") for v in value.values()):
                graphs.update(value)
    return graphs


def inventory(agent) -> dict:
    """What each graph can actually execute, read from the compiled tool nodes."""
    return {
        "main": sorted(tool_executor_names(agent)),
        "subagents": {name: sorted(tool_executor_names(g)) for name, g in subagent_graphs(agent).items()},
    }


def check_inventory(found: dict, allowed_main: set[str], allowed_sub: dict[str, set[str]]) -> None:
    problems = []
    extra = set(found["main"]) - allowed_main - {DELEGATION_TOOL} - REQUIRED_BY_FRAMEWORK
    if extra:
        problems.append(f"main agent has tools outside the allowlist: {sorted(extra)}")
    if set(found["subagents"]) != set(allowed_sub):
        problems.append(f"subagents are {sorted(found['subagents'])}, expected {sorted(allowed_sub)}")
    for name, tools in found["subagents"].items():
        extra = set(tools) - allowed_sub.get(name, set()) - REQUIRED_BY_FRAMEWORK
        if extra:
            problems.append(f"subagent {name} has tools outside its allowlist: {sorted(extra)}")
        if DELEGATION_TOOL in tools:
            problems.append(f"subagent {name} can delegate")
    if problems:
        raise UnsafeAgent("; ".join(problems))


def build(model, tools, *, system_prompt: str, subagents: list[dict], budget: Budget):
    """subagents: dicts with name, description, system_prompt, and tools (a subset of tools)."""
    lock_down_provider(model)
    main_allowed = {t.name for t in tools} | ({DELEGATION_TOOL} if subagents else set())
    specs = [
        {**spec, "middleware": [minimal_files(), RunGuard({t.name for t in spec["tools"]}, budget, spec["name"])]}
        for spec in subagents
    ]
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        subagents=specs,
        middleware=[minimal_files(), RunGuard(main_allowed, budget, "main")],
    )
    found = inventory(agent)
    check_inventory(found, main_allowed, {s["name"]: {t.name for t in s["tools"]} for s in subagents})
    return agent, found
