import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from mcp.client import Client
from mcp.server import MCPServer
from pydantic import BaseModel, Field, ValidationError

from app.core.agent.tools.base import AgentTool
from app.core.agent.tools.mcp.loader import (
    _list_descriptors,
    _normalize_result,
    _unique_name,
)
from app.core.agent.orchestrator import run_function_calling
from app.core.llm.native_chat import NativeChatModel
from app.core.llm.types import ChatChunk, HumanMessage, ToolCallDelta, Usage


class _QueryInput(BaseModel):
    query: str = Field(min_length=1)
    limit: int = 3


class NativeAgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_tool_validates_and_applies_defaults(self):
        called = {}

        async def run(query: str, limit: int) -> str:
            called.update(query=query, limit=limit)
            return query

        tool = AgentTool.from_function(
            coroutine=run,
            name="search",
            description="search",
            args_schema=_QueryInput,
        )

        self.assertEqual(await tool.ainvoke({"query": "echo"}), "echo")
        self.assertEqual(called, {"query": "echo", "limit": 3})
        with self.assertRaises(ValidationError):
            await tool.ainvoke({"query": ""})

    async def test_chat_chunks_aggregate_fragmented_tool_calls_and_usage(self):
        first = ChatChunk(
            tool_call_deltas={
                0: ToolCallDelta(
                    index=0,
                    id="call_1",
                    name="knowledge_",
                    arguments='{"query":"',
                )
            }
        )
        second = ChatChunk(
            tool_call_deltas={
                0: ToolCallDelta(
                    index=0,
                    name="search",
                    arguments='MCP 2.0"}',
                )
            },
            usage=Usage(input_tokens=12, output_tokens=4, cached_tokens=2),
            finish_reason="tool_calls",
        )

        gathered = first + second
        self.assertEqual(gathered.tool_calls[0].name, "knowledge_search")
        self.assertEqual(gathered.tool_calls[0].arguments, {"query": "MCP 2.0"})
        self.assertEqual(gathered.usage_metadata["input_tokens"], 12)

    async def test_complete_serializes_native_tools_and_parses_tool_call(self):
        async def run(query: str) -> str:
            return query

        tool = AgentTool.from_function(
            coroutine=run,
            name="search",
            description="search docs",
            args_schema=_QueryInput,
        )
        response = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "search",
                                    "arguments": '{"query":"echo"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 2},
        }
        model = NativeChatModel("test", "key", "https://llm.example/v1").bind_tools([tool])

        with patch(
            "app.core.llm.native_chat._post_with_retry",
            new=AsyncMock(return_value=response),
        ) as post:
            message = await model.ainvoke([HumanMessage("find echo")])

        payload = post.await_args.kwargs["json"]
        self.assertEqual(payload["tools"][0]["function"]["name"], "search")
        self.assertEqual(message.tool_calls[0].arguments, {"query": "echo"})
        self.assertEqual(message.usage_metadata["output_tokens"], 2)

    async def test_stream_parses_text_tool_deltas_and_usage_tail(self):
        frames = [
            {"choices": [{"delta": {"content": "先查"}, "finish_reason": None}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"query":"echo"}',
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "prompt_tokens_details": {"cached_tokens": 1},
                },
            },
        ]
        body = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
        body += "data: [DONE]\n\n"

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body, request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        model = NativeChatModel("test", "key", "https://llm.example/v1")
        gathered = None
        try:
            with patch("app.core.llm.native_chat._get_shared_client", return_value=client):
                async for chunk in model.astream("hello"):
                    gathered = chunk if gathered is None else gathered + chunk
        finally:
            await client.aclose()

        self.assertIsNotNone(gathered)
        self.assertEqual(gathered.content, "先查")
        self.assertEqual(gathered.tool_calls[0].name, "search")
        self.assertEqual(gathered.usage.cached_tokens, 1)

    async def test_stream_retries_once_without_usage_option_when_provider_rejects_it(self):
        payloads = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            payloads.append(payload)
            if len(payloads) == 1:
                return httpx.Response(
                    400,
                    json={"error": {"message": "unknown stream_options.include_usage"}},
                    request=request,
                )
            body = 'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n'
            body += "data: [DONE]\n\n"
            return httpx.Response(200, content=body, request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        model = NativeChatModel("test", "key", "https://llm.example/v1")
        chunks = []
        try:
            with patch("app.core.llm.native_chat._get_shared_client", return_value=client):
                async for chunk in model.astream("hello"):
                    chunks.append(chunk)
        finally:
            await client.aclose()

        self.assertEqual("".join(chunk.content for chunk in chunks), "ok")
        self.assertIn("stream_options", payloads[0])
        self.assertNotIn("stream_options", payloads[1])
        self.assertEqual(len(payloads), 2)

    async def test_parallel_tool_calls_keep_indexes_and_report_invalid_arguments(self):
        first = ChatChunk(
            tool_call_deltas={
                0: ToolCallDelta(index=0, id="call_1", name="search", arguments="{"),
                1: ToolCallDelta(index=1, id="call_2", name="clock", arguments="{}"),
            }
        )
        second = ChatChunk(
            tool_call_deltas={
                0: ToolCallDelta(index=0, arguments='"query":]'),
            }
        )

        calls = (first + second).tool_calls
        self.assertEqual([call.name for call in calls], ["search", "clock"])
        self.assertIsNotNone(calls[0].arguments_error)
        self.assertEqual(calls[1].arguments, {})

    async def test_official_mcp_v2_client_lists_and_calls_tools(self):
        server = MCPServer("runtime-test")

        @server.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        async with Client(server) as client:
            descriptors = await _list_descriptors(client)
            result = await client.call_tool("add", {"a": 2, "b": 3})

        self.assertEqual(descriptors[0].name, "add")
        self.assertIn("a", descriptors[0].input_schema.get("properties", {}))
        self.assertEqual(_normalize_result(result), {"result": 5})

    async def test_mcp_tool_listing_follows_pagination(self):
        first = SimpleNamespace(
            tools=[SimpleNamespace(name="one", description="1", input_schema={})],
            next_cursor="next",
        )
        second = SimpleNamespace(
            tools=[SimpleNamespace(name="two", description="2", input_schema={})],
            next_cursor=None,
        )
        client = SimpleNamespace(list_tools=AsyncMock(side_effect=[first, second]))

        descriptors = await _list_descriptors(client)

        self.assertEqual([tool.name for tool in descriptors], ["one", "two"])
        self.assertEqual(client.list_tools.await_args_list[0].kwargs["cursor"], None)
        self.assertEqual(client.list_tools.await_args_list[1].kwargs["cursor"], "next")

    async def test_mcp_error_result_becomes_tool_exception(self):
        result = SimpleNamespace(
            content=[SimpleNamespace(text="remote failure")],
            structured_content=None,
            is_error=True,
        )
        with self.assertRaisesRegex(RuntimeError, "remote failure"):
            _normalize_result(result)

    async def test_mcp_tool_names_are_sanitized_limited_and_deduplicated(self):
        seen = set()
        first = _unique_name("服务 A", "查询/明细" * 20, seen)
        second = _unique_name("服务 A", "查询/明细" * 20, seen)

        self.assertLessEqual(len(first), 64)
        self.assertRegex(first, r"^[a-zA-Z0-9_-]+$")
        self.assertNotEqual(first, second)

    async def test_function_loop_reuses_identical_tool_call_in_same_turn(self):
        calls = 0

        async def invoke(query: str) -> str:
            nonlocal calls
            calls += 1
            return f"result:{query}"

        tool = AgentTool(
            name="search",
            description="search",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            coroutine=invoke,
        )

        class Model:
            model_name = "fake"

            def __init__(self):
                self.iteration = 0

            def bind_tools(self, _tools):
                return self

            async def astream(self, _messages):
                self.iteration += 1
                if self.iteration <= 2:
                    yield ChatChunk(
                        tool_call_deltas={
                            0: ToolCallDelta(
                                index=0,
                                id=f"call_{self.iteration}",
                                name="search",
                                arguments='{"query":"echo"}',
                            )
                        },
                        finish_reason="tool_calls",
                    )
                else:
                    yield ChatChunk(content="done", finish_reason="stop")

        events = []
        async for event in run_function_calling(Model(), [tool], [HumanMessage("go")]):
            events.append(event)

        self.assertEqual(calls, 1)
        self.assertTrue(any(event.get("cached") for event in events))
        self.assertEqual(events[-1], {"type": "final", "text": "done"})

    async def test_function_loop_reports_invalid_arguments_without_running_tool(self):
        called = False

        async def invoke(query: str) -> str:
            nonlocal called
            called = True
            return query

        tool = AgentTool(
            name="search",
            description="search",
            input_schema={"type": "object"},
            coroutine=invoke,
        )

        class Model:
            model_name = "fake"

            def bind_tools(self, _tools):
                return self

            async def astream(self, _messages):
                yield ChatChunk(
                    tool_call_deltas={
                        0: ToolCallDelta(
                            index=0,
                            id="call_bad",
                            name="search",
                            arguments='{"query":]',
                        )
                    },
                    finish_reason="tool_calls",
                )

        events = []
        async for event in run_function_calling(Model(), [tool], [HumanMessage("go")]):
            events.append(event)

        self.assertFalse(called)
        errors = [event for event in events if event.get("type") == "tool_result"]
        self.assertEqual(errors[0]["status"], "error")
        self.assertIn("JSON", errors[0]["text"])

    async def test_function_loop_stops_after_five_tool_iterations(self):
        class Model:
            model_name = "fake"

            def __init__(self):
                self.iterations = 0

            def bind_tools(self, _tools):
                return self

            async def astream(self, _messages):
                self.iterations += 1
                yield ChatChunk(
                    tool_call_deltas={
                        0: ToolCallDelta(
                            index=0,
                            id=f"call_{self.iterations}",
                            name="missing",
                            arguments="{}",
                        )
                    },
                    finish_reason="tool_calls",
                )

        model = Model()
        events = []
        async for event in run_function_calling(model, [], [HumanMessage("go")]):
            events.append(event)

        self.assertEqual(model.iterations, 5)
        self.assertEqual(events[-1], {"type": "final", "text": "（未能生成回答）"})


if __name__ == "__main__":
    unittest.main()
