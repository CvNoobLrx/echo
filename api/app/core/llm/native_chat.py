"""OpenAI-compatible native chat runtime with streaming tool-call support."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Iterable
from dataclasses import dataclass, replace
from typing import Any

import httpx

from app.core.llm.client import _get_shared_client, _post_with_retry
from app.core.llm.types import (
    AIMessage,
    ChatChunk,
    ChatCompletion,
    ChatMessage,
    ChatStreamEvent,
    HumanMessage,
    ToolCall,
    ToolCallDelta,
    Usage,
)

_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.5
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _coerce_messages(value: str | ChatMessage | Iterable[Any]) -> list[ChatMessage | ChatChunk | dict]:
    if isinstance(value, str):
        return [HumanMessage(content=value)]
    if isinstance(value, ChatMessage):
        return [value]
    return list(value)


def _message_payload(message: ChatMessage | ChatChunk | dict) -> dict[str, Any]:
    if isinstance(message, ChatChunk):
        return message.to_message().to_openai()
    if isinstance(message, ChatMessage):
        return message.to_openai()
    if isinstance(message, dict):
        return message
    raise TypeError(f"不支持的消息类型：{type(message).__name__}")


def _tool_payload(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _parse_tool_calls(raw_calls: list[dict[str, Any]] | None) -> list[ToolCall]:
    out: list[ToolCall] = []
    for index, item in enumerate(raw_calls or []):
        function = item.get("function") or {}
        raw_arguments = function.get("arguments") or "{}"
        error: str | None = None
        try:
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                arguments = {}
                error = "工具参数必须是 JSON 对象"
        except json.JSONDecodeError as exc:
            arguments = {}
            error = f"工具参数 JSON 无效：{exc.msg}"
        out.append(
            ToolCall(
                id=item.get("id") or f"call_{index}",
                name=function.get("name") or "",
                arguments=arguments,
                arguments_json=raw_arguments,
                arguments_error=error,
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class NativeChatModel:
    model_name: str
    api_key: str
    base_url: str
    temperature: float = 0.7
    streaming: bool = True
    stream_usage: bool = True
    tools: tuple[Any, ...] = ()

    @property
    def model(self) -> str:
        return self.model_name

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def bind_tools(self, tools: list[Any]) -> "NativeChatModel":
        return replace(self, tools=tuple(tools))

    def _payload(
        self,
        messages: str | ChatMessage | Iterable[Any],
        *,
        stream: bool,
        tools: list[Any] | tuple[Any, ...] | None,
        max_tokens: int | None,
        include_usage: bool = True,
    ) -> dict[str, Any]:
        selected_tools = self.tools if tools is None else tuple(tools)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [_message_payload(m) for m in _coerce_messages(messages)],
            "temperature": self.temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if selected_tools:
            payload["tools"] = [_tool_payload(tool) for tool in selected_tools]
            payload["tool_choice"] = "auto"
        if stream and self.stream_usage and include_usage:
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def complete(
        self,
        messages: str | ChatMessage | Iterable[Any],
        *,
        tools: list[Any] | tuple[Any, ...] | None = None,
        max_tokens: int | None = None,
    ) -> ChatCompletion:
        payload = self._payload(
            messages, stream=False, tools=tools, max_tokens=max_tokens
        )
        data = await _post_with_retry(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers=self._headers,
            json=payload,
            timeout=120,
        )
        choice = (data.get("choices") or [{}])[0]
        raw_message = choice.get("message") or {}
        content = raw_message.get("content") or ""
        usage = Usage.from_openai(data.get("usage"))
        message = AIMessage(
            content=content,
            tool_calls=_parse_tool_calls(raw_message.get("tool_calls")),
            usage=usage,
        )
        return ChatCompletion(
            message=message,
            usage=usage,
            finish_reason=choice.get("finish_reason"),
        )

    async def _stream_payloads(
        self,
        messages: str | ChatMessage | Iterable[Any],
        *,
        tools: list[Any] | tuple[Any, ...] | None,
        max_tokens: int | None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        client = _get_shared_client()
        include_usage = True
        emitted = False
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            payload = self._payload(
                messages,
                stream=True,
                tools=tools,
                max_tokens=max_tokens,
                include_usage=include_usage,
            )
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers=self._headers,
                    json=payload,
                    timeout=httpx.Timeout(120.0, read=120.0),
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode(errors="replace")
                        lowered = body.lower()
                        if (
                            response.status_code == 400
                            and include_usage
                            and ("stream_options" in lowered or "include_usage" in lowered)
                        ):
                            include_usage = False
                            continue
                        if response.status_code in _RETRY_STATUS and not emitted:
                            raise httpx.HTTPStatusError(
                                f"可重试状态 {response.status_code}: {body[:300]}",
                                request=response.request,
                                response=response,
                            )
                        raise httpx.HTTPStatusError(
                            f"LLM 流式请求失败 {response.status_code}: {body[:500]}",
                            request=response.request,
                            response=response,
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":") or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        emitted = True
                        yield json.loads(data)
                    return
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code if exc.response is not None else None
                if emitted or status not in _RETRY_STATUS or attempt >= _MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
            except (httpx.TransportError, json.JSONDecodeError) as exc:
                last_exc = exc
                if emitted or attempt >= _MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))

        if last_exc is not None:
            raise last_exc

    async def stream(
        self,
        messages: str | ChatMessage | Iterable[Any],
        *,
        tools: list[Any] | tuple[Any, ...] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        gathered = ChatChunk()
        async for data in self._stream_payloads(
            messages, tools=tools, max_tokens=max_tokens
        ):
            usage = Usage.from_openai(data.get("usage"))
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            content = delta.get("content") or ""
            if not isinstance(content, str):
                content = str(content)
            tool_deltas: dict[int, ToolCallDelta] = {}
            for raw_call in delta.get("tool_calls") or []:
                function = raw_call.get("function") or {}
                index = int(raw_call.get("index") or 0)
                tool_deltas[index] = ToolCallDelta(
                    index=index,
                    id=raw_call.get("id") or "",
                    name=function.get("name") or "",
                    arguments=function.get("arguments") or "",
                )
            chunk = ChatChunk(
                content=content,
                tool_call_deltas=tool_deltas,
                usage=usage,
                finish_reason=choice.get("finish_reason"),
            )
            gathered = gathered + chunk
            yield ChatStreamEvent(type="delta", delta=chunk)

        completion = ChatCompletion(
            message=gathered.to_message(),
            usage=gathered.usage,
            finish_reason=gathered.finish_reason,
        )
        yield ChatStreamEvent(type="done", completion=completion)

    async def ainvoke(
        self, messages: str | ChatMessage | Iterable[Any]
    ) -> AIMessage:
        return (await self.complete(messages)).message

    async def astream(
        self, messages: str | ChatMessage | Iterable[Any]
    ) -> AsyncGenerator[ChatChunk, None]:
        async for event in self.stream(messages):
            if event.type == "delta" and event.delta is not None:
                yield event.delta


__all__ = ["NativeChatModel"]
