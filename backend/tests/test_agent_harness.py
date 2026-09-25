import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool

from app.agent.harness import FRAMEWORK_TOOLS, Budget, UnsafeAgent, build, check_inventory


class ScriptedModel(BaseChatModel):
    """Replays tool calls, then a final message; records the tools it was shown."""

    script: list = []
    shown: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.shown.append(sorted(t.name if hasattr(t, "name") else t["name"] for t in tools))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        step = self.script.pop(0) if self.script else "done"
        if isinstance(step, str):
            message = AIMessage(content=step)
        else:
            message = AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"c{len(self.script)}-{i}"} for i, (n, a) in enumerate(step)])
        return ChatResult(generations=[ChatGeneration(message=message)])


executed: list[str] = []


def tool(name):
    def fn(query: str = "") -> str:
        executed.append(name)
        return f"{name} result"

    fn.__name__ = name
    fn.__doc__ = f"{name} for tests."
    return StructuredTool.from_function(fn)


TOOLS = {n: tool(n) for n in ("search_policies", "get_section", "follow_policy_links", "compare_versions")}
SUBAGENTS = [
    {"name": "link-follower", "description": "follows links", "system_prompt": "follow", "tools": [TOOLS["follow_policy_links"], TOOLS["get_section"]]},
    {"name": "version-checker", "description": "checks versions", "system_prompt": "versions", "tools": [TOOLS["compare_versions"]]},
]


def agent_with(script, budget=None):
    executed.clear()
    model = ScriptedModel(script=list(script), shown=[])
    budget = budget or Budget(6, 120, 2)
    agent, found = build(model, list(TOOLS.values()), system_prompt="test", subagents=SUBAGENTS, budget=budget)
    return agent, found, model, budget


def test_compiled_inventory_has_no_write_shell_or_search_tools():
    _agent, found, _model, _budget = agent_with([])
    everything = set(found["main"]).union(*map(set, found["subagents"].values()))
    assert not everything & (FRAMEWORK_TOOLS - {"read_file"})
    assert set(found["main"]) == set(TOOLS) | {"task", "read_file"}
    assert sorted(found["subagents"]) == ["link-follower", "version-checker"]
    assert all("task" not in tools for tools in found["subagents"].values())
    assert found["subagents"]["version-checker"] == ["compare_versions", "read_file"]


def test_model_is_shown_only_the_allowlist():
    agent, _found, model, _budget = agent_with(["done"])
    agent.invoke({"messages": [{"role": "user", "content": "q"}]})
    assert model.shown and all(set(s) == set(TOOLS) | {"task"} for s in model.shown)


def test_calls_to_framework_tools_are_refused_before_they_run():
    script = [[("read_file", {"file_path": "/etc/passwd"}), ("write_file", {"file_path": "/x", "content": "y"})], "done"]
    agent, _found, _model, budget = agent_with(script)
    agent.invoke({"messages": [{"role": "user", "content": "q"}]})
    assert [r["tool"] for r in budget.refusals] == ["read_file", "write_file"]
    assert all(r["reason"] == "tool is not on the allowlist" for r in budget.refusals)
    assert budget.calls == [] and executed == []


def test_tool_call_budget_is_enforced():
    script = [[("search_policies", {"query": str(i)})] for i in range(8)] + ["done"]
    agent, _found, _model, budget = agent_with(script)
    agent.invoke({"messages": [{"role": "user", "content": "q"}]})
    assert len(budget.calls) == 6 and executed == ["search_policies"] * 6
    assert [r["reason"] for r in budget.refusals] == ["tool-call budget of 6 used"] * 2


def test_time_and_delegation_limits():
    budget = Budget(6, 0.0, 2)
    assert budget.refusal("search_policies") == "time limit of 0 s reached"
    budget = Budget(6, 120, 1)
    budget.calls.append({"tool": "task"})
    assert budget.refusal("task") == "delegation budget of 1 used" and budget.refusal("get_section") is None


class UnprofiledModel(ScriptedModel):
    pass


def test_agent_is_refused_when_the_lockdown_profile_does_not_apply(monkeypatch):
    import app.agent.harness as harness

    monkeypatch.setattr(harness, "lock_down_provider", lambda model: None)
    with pytest.raises(UnsafeAgent, match="general-purpose"):
        build(UnprofiledModel(script=[], shown=[]), list(TOOLS.values()), system_prompt="t", subagents=SUBAGENTS,
              budget=Budget(6, 120, 2))


def test_unexpected_tools_refuse_the_agent():
    found = {"main": ["search_policies", "write_file"], "subagents": {"a": ["get_section", "task"]}}
    with pytest.raises(UnsafeAgent, match="write_file") as info:
        check_inventory(found, {"search_policies"}, {"a": {"get_section"}})
    assert "can delegate" in str(info.value)
