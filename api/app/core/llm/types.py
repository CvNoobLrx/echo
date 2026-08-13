"""Native chat message and completion types used by the agent runtime."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

MessageContent = str | list[dict[str, Any]]


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_json: str = ""
    arguments_error: str | None = None

    def get(self, key: str, default: Any = None) -> Any:
        """Provide the small mapping surface used by the existing orchestrator."""
        values = {
            "id": self.id,
            "name": self.name,
            "args": self.arguments,
            "args_error": self.arguments_error,
        }
        return values.get(key, default)

    def to_openai(self) -> dict[str, Any]:
        arguments = self.arguments_json
        if not arguments:
            arguments = json.dumps(self.arguments, ensure_ascii=False)
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": arguments},
        }


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    @classmethod
    def from_openai(cls, data: dict[str, Any] | None) -> "Usage":
        usage = data or {}
        details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        return cls(
            input_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            output_tokens=int(
                usage.get("completion_tokens") or usage.get("output_tokens") or 0
            ),
            cached_tokens=int(
                details.get("cached_tokens")
                or details.get("cache_read")
                or usage.get("cached_tokens")
                or 0
            ),
        )

    def to_metadata(self) -> dict[str, Any]:
        if not (self.input_tokens or self.output_tokens or self.cached_tokens):
            return {}
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_token_details": {"cache_read": self.cached_tokens},
        }

    def merged(self, other: "Usage") -> "Usage":
        if other.input_tokens or other.output_tokens or other.cached_tokens:
            return other
        return self


@dataclass(slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: MessageContent = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    usage: Usage = field(default_factory=Usage)

    @property
    def usage_metadata(self) -> dict[str, Any]:
        return self.usage.to_metadata()

    def to_openai(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.role == "assistant" and self.tool_calls:
            message["tool_calls"] = [call.to_openai() for call in self.tool_calls]
        if self.role == "tool" and self.tool_call_id:
            message["tool_call_id"] = self.tool_call_id
        return message


class HumanMessage(ChatMessage):
    def __init__(self, content: MessageContent):
        super().__init__(role="user", content=content)


class SystemMessage(ChatMessage):
    def __init__(self, content: MessageContent):
        super().__init__(role="system", content=content)


class AIMessage(ChatMessage):
    def __init__(
        self,
        content: MessageContent = "",
        *,
        tool_calls: list[ToolCall] | None = None,
        usage: Usage | None = None,
    ):
        super().__init__(
            role="assistant",
            content=content,
            tool_calls=tool_calls or [],
            usage=usage or Usage(),
        )


class ToolMessage(ChatMessage):
    def __init__(self, content: MessageContent, tool_call_id: str):
        super().__init__(role="tool", content=content, tool_call_id=tool_call_id)


@dataclass(slots=True)
class ToolCallDelta:
    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass(slots=True)
class ChatChunk:
    content: str = ""
    tool_call_deltas: dict[int, ToolCallDelta] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None

    @property
    def role(self) -> str:
        return "assistant"

    @property
    def usage_metadata(self) -> dict[str, Any]:
        return self.usage.to_metadata()

    @property
    def tool_calls(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for index in sorted(self.tool_call_deltas):
            delta = self.tool_call_deltas[index]
            raw = delta.arguments or "{}"
            error: str | None = None
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    error = "工具参数必须是 JSON 对象"
                    parsed = {}
            except json.JSONDecodeError as exc:
                parsed = {}
                error = f"工具参数 JSON 无效：{exc.msg}"
            calls.append(
                ToolCall(
                    id=delta.id or f"call_{index}",
                    name=delta.name,
                    arguments=parsed,
                    arguments_json=raw,
                    arguments_error=error,
                )
            )
        return calls

    def to_message(self) -> AIMessage:
        return AIMessage(content=self.content, tool_calls=self.tool_calls, usage=self.usage)

    def __add__(self, other: "ChatChunk") -> "ChatChunk":
        merged = {
            index: ToolCallDelta(
                index=delta.index,
                id=delta.id,
                name=delta.name,
                arguments=delta.arguments,
            )
            for index, delta in self.tool_call_deltas.items()
        }
        for index, incoming in other.tool_call_deltas.items():
            current = merged.get(index)
            if current is None:
                merged[index] = ToolCallDelta(
                    index=index,
                    id=incoming.id,
                    name=incoming.name,
                    arguments=incoming.arguments,
                )
            else:
                if incoming.id:
                    current.id = incoming.id
                current.name += incoming.name
                current.arguments += incoming.arguments
        return ChatChunk(
            content=self.content + other.content,
            tool_call_deltas=merged,
            usage=self.usage.merged(other.usage),
            finish_reason=other.finish_reason or self.finish_reason,
        )


@dataclass(slots=True)
class ChatCompletion:
    message: AIMessage
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None

    @property
    def content(self) -> MessageContent:
        return self.message.content

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self.message.tool_calls

    @property
    def usage_metadata(self) -> dict[str, Any]:
        return self.usage.to_metadata()


@dataclass(slots=True)
class ChatStreamEvent:
    type: Literal["delta", "done"]
    delta: ChatChunk | None = None
    completion: ChatCompletion | None = None


__all__ = [
    "AIMessage",
    "ChatChunk",
    "ChatCompletion",
    "ChatMessage",
    "ChatStreamEvent",
    "HumanMessage",
    "MessageContent",
    "SystemMessage",
    "ToolCall",
    "ToolCallDelta",
    "ToolMessage",
    "Usage",
]
