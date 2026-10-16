"""LLM layer: prompts live here as constants so they are easy to tune.
Two implementations behind one interface: OpenAILLM (Agents SDK) and MockLLM (offline,
scripted, used for tests and whenever no OPENAI_API_KEY is configured)."""
import asyncio
import contextvars
import os
import random
from typing import Protocol

from pydantic import BaseModel, Field

from ..config import settings
from ..events import bus
from ..models import Event
from ..tools.registry import TOOLS

# ---------- structured outputs ----------


class Subtask(BaseModel):
    id: str = Field(description="short id like t1, t2")
    goal: str
    depends_on: list[str] = Field(default_factory=list)
    needs_capability: str | None = None


class PlanOutput(BaseModel):
    subtasks: list[Subtask] = Field(default_factory=list)
    direct_answer: str | None = None


class MissingTool(BaseModel):
    name_hint: str
    description: str
    example_input: str = ""


class WorkerOutput(BaseModel):
    result: str
    confidence: float = Field(ge=0, le=1)
    needs_decomposition: bool = False
    missing_tool: MissingTool | None = None


# ---------- prompts ----------

PLANNER_PROMPT = (
    "You are the Planner of an agent system. Break the user's goal into 2-5 subtasks that can "
    "run independently where possible; use depends_on only for real data dependencies (ids of "
    "other subtasks). If the goal is trivial, set direct_answer and return no subtasks. "
    "Subtasks must each be solvable with web search / reading web pages."
)
WORKER_PROMPT = (
    "You are a Worker agent. Solve exactly the subtask you are given using the tools web_search "
    "and fetch_url when needed. Be concise and factual. Report an honest confidence between 0 "
    "and 1: below 0.6 if you are unsure or sources conflict. If the task is too big, set "
    "needs_decomposition. If you lack a tool that would be needed, fill missing_tool."
)
SYNTH_PROMPT = (
    "Combine the subtask results into one clear answer to the original goal. Give a confidence "
    "between 0 and 1 reflecting the weakest evidence."
)

# Set by the runner so tool calls can be attributed to the right node: (run_id, node_id).
CURRENT: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar("current", default=None)


class LLM(Protocol):
    async def plan(self, goal: str, depth: int) -> tuple[PlanOutput, int]: ...
    async def work(self, goal: str, context: str) -> tuple[WorkerOutput, int]: ...
    async def synthesize(self, goal: str, results: dict[str, str]) -> tuple[WorkerOutput, int]: ...


async def _emit(type_: str, **payload) -> None:
    cur = CURRENT.get()
    if cur:
        await bus.publish(Event(run_id=cur[0], type=type_, agent_id=cur[1], payload=payload))


# ---------- real implementation ----------


class OpenAILLM:
    def __init__(self) -> None:
        from agents import Agent, function_tool  # lazy: not needed in mock mode

        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
        self._Agent = Agent

        @function_tool
        async def web_search(query: str) -> str:
            """Search the web and return the top results (title, link, snippet)."""
            await _emit("tool_call", tool="web_search", args={"query": query})
            await _emit("system_flow", **{"from": "agents", "to": "serpapi"})
            res = await TOOLS["web_search"](query)
            await _emit("tool_result", tool="web_search", summary=f"{len(res)} results")
            return "\n".join(f"{r['title']} | {r['link']} | {r['snippet']}" for r in res)

        @function_tool
        async def fetch_url(url: str) -> str:
            """Fetch a web page and return its cleaned text (truncated)."""
            await _emit("tool_call", tool="fetch_url", args={"url": url})
            res = await TOOLS["fetch_url"](url)
            await _emit("tool_result", tool="fetch_url", summary=f"{len(res)} chars")
            return res

        self._tools = [web_search, fetch_url]

    async def _run(self, name, prompt, output_type, text, tools=None):
        from agents import Runner

        agent = self._Agent(
            name=name, instructions=prompt, model=settings.openai_model,
            output_type=output_type, tools=tools or [],
        )
        # One retry on validation/transient errors (PLAN.md rule).
        for attempt in (1, 2):
            try:
                res = await Runner.run(agent, text, max_turns=8)
                return res.final_output, res.context_wrapper.usage.total_tokens
            except Exception:
                if attempt == 2:
                    raise

    async def plan(self, goal, depth):
        return await self._run("Planner", PLANNER_PROMPT, PlanOutput, goal)

    async def work(self, goal, context):
        text = goal if not context else f"{goal}\n\nContext from earlier tasks:\n{context}"
        return await self._run("Worker", WORKER_PROMPT, WorkerOutput, text, self._tools)

    async def synthesize(self, goal, results):
        body = "\n".join(f"- {k}: {v}" for k, v in results.items())
        return await self._run("Synthesizer", SYNTH_PROMPT, WorkerOutput, f"Goal: {goal}\n\nResults:\n{body}")


# ---------- offline scripted implementation ----------


class MockLLM:
    """Deterministic stand-in so orchestration can be tested without an API key.
    Goals containing 'compare' fan out into 3 parallel store lookups; the Mega.pk one
    reports low confidence to trigger the human-approval path."""

    async def plan(self, goal, depth):
        await asyncio.sleep(1.0)
        if depth == 0 and "compare" in goal.lower():
            stores = ["Daraz", "PriceOye", "Mega.pk"]
            subs = [Subtask(id=f"t{i}", goal=f"Find the price on {s}") for i, s in enumerate(stores, 1)]
            return PlanOutput(subtasks=subs), 400
        return PlanOutput(direct_answer=f"(mock) answer to: {goal}"), 200

    async def work(self, goal, context):
        await _emit("tool_call", tool="web_search", args={"query": goal})
        await asyncio.sleep(random.uniform(5.0, 7.0))
        await _emit("tool_result", tool="web_search", summary="mock results")
        low = "mega" in goal.lower()
        return WorkerOutput(result=f"(mock) {goal}: PKR {random.randint(250, 340)},000",
                            confidence=0.4 if low else 0.85), 1500

    async def synthesize(self, goal, results):
        await asyncio.sleep(1.0)
        return WorkerOutput(result="(mock) " + "; ".join(results.values()), confidence=0.8), 500


def get_llm() -> LLM:
    if settings.mock_llm or not settings.openai_api_key:
        return MockLLM()
    return OpenAILLM()
