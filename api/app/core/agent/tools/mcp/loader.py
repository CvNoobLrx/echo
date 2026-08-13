"""Discover and invoke MCP tools directly through the official MCP 2.0 SDK."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.tools.base import AgentTool
from app.core.agent.tools.mcp.connection import (
    MCPConnectionConfig,
    SSE_READ_TIMEOUT,
    build_connection,
    open_mcp_client,
)
from app.core.logging import get_logger
from app.models.mcp_server_model import MCPServer
from app.repositories.mcp_server_repository import MCPServerRepository

logger = get_logger(__name__)

_INVALID = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_NAME_LEN = 64
_MCP_CACHE_TTL = 300.0


@dataclass(frozen=True, slots=True)
class MCPToolDescriptor:
    name: str
    description: str
    input_schema: dict[str, Any]


# (user_id, server_id) -> (expires_at, updated_at fingerprint, descriptors)
_MCP_CACHE: dict[
    tuple[str, str], tuple[float, str, tuple[MCPToolDescriptor, ...]]
] = {}


def _server_fingerprint(server: MCPServer) -> str:
    return server.updated_at.isoformat() if server.updated_at else ""


def _sanitize(text: str) -> str:
    cleaned = _INVALID.sub("_", text).strip("_")
    return cleaned or "mcp"


def _unique_name(server_name: str, tool_name: str, seen: set[str]) -> str:
    base = f"{_sanitize(server_name)}__{_sanitize(tool_name)}"[:_MAX_NAME_LEN]
    name = base
    index = 1
    while name in seen:
        suffix = f"_{index}"
        name = base[: _MAX_NAME_LEN - len(suffix)] + suffix
        index += 1
    seen.add(name)
    return name


def _tool_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, dict):
        return schema
    if hasattr(schema, "model_dump"):
        return schema.model_dump(mode="json", by_alias=True)
    return {"type": "object", "properties": {}}


async def _list_descriptors(client: Any) -> list[MCPToolDescriptor]:
    descriptors: list[MCPToolDescriptor] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor, cache_mode="bypass")
        for tool in page.tools:
            descriptors.append(
                MCPToolDescriptor(
                    name=tool.name,
                    description=(tool.description or "")[:2000],
                    input_schema=_tool_schema(tool),
                )
            )
        cursor = getattr(page, "next_cursor", None)
        if not cursor:
            return descriptors


def _cached_descriptors(
    user_id: uuid.UUID, server: MCPServer
) -> tuple[MCPToolDescriptor, ...] | None:
    key = (str(user_id), str(server.id))
    cached = _MCP_CACHE.get(key)
    if not cached:
        return None
    expires_at, fingerprint, descriptors = cached
    if expires_at <= time.monotonic() or fingerprint != _server_fingerprint(server):
        _MCP_CACHE.pop(key, None)
        return None
    return descriptors


def _store_descriptors(
    user_id: uuid.UUID,
    server: MCPServer,
    descriptors: list[MCPToolDescriptor],
) -> tuple[MCPToolDescriptor, ...]:
    value = tuple(descriptors)
    _MCP_CACHE[(str(user_id), str(server.id))] = (
        time.monotonic() + _MCP_CACHE_TTL,
        _server_fingerprint(server),
        value,
    )
    return value


async def _discover_server(
    user_id: uuid.UUID, server: MCPServer
) -> tuple[MCPConnectionConfig, tuple[MCPToolDescriptor, ...]]:
    connection = build_connection(server)
    cached = _cached_descriptors(user_id, server)
    if cached is not None:
        return connection, cached
    async with open_mcp_client(connection) as client:
        descriptors = await _list_descriptors(client)
    return connection, _store_descriptors(user_id, server, descriptors)


def _serialize_content_block(block: Any) -> str:
    text = getattr(block, "text", None)
    if isinstance(text, str):
        return text
    if hasattr(block, "model_dump"):
        data = block.model_dump(mode="json", by_alias=True, exclude_none=True)
    elif isinstance(block, dict):
        data = block
    else:
        return str(block)
    return json.dumps(data, ensure_ascii=False)


def _normalize_result(result: Any) -> object:
    content = getattr(result, "content", None) or []
    text = "\n\n".join(
        part for part in (_serialize_content_block(block).strip() for block in content) if part
    )
    structured = getattr(result, "structured_content", None)
    if getattr(result, "is_error", False):
        detail = text
        if not detail and structured is not None:
            detail = json.dumps(structured, ensure_ascii=False)
        raise RuntimeError(detail or "MCP 工具返回错误")
    if structured is not None:
        return structured
    return text


def _build_stateless_tool(
    connection: MCPConnectionConfig,
    descriptor: MCPToolDescriptor,
    exposed_name: str,
) -> AgentTool:
    async def invoke(**arguments: Any) -> object:
        async with open_mcp_client(connection) as client:
            result = await client.call_tool(
                descriptor.name,
                arguments,
                read_timeout_seconds=SSE_READ_TIMEOUT,
            )
        return _normalize_result(result)

    return AgentTool(
        name=exposed_name,
        description=descriptor.description,
        input_schema=descriptor.input_schema,
        coroutine=invoke,
    )


def _build_connected_tool(
    client: Any,
    lock: asyncio.Lock,
    descriptor: MCPToolDescriptor,
    exposed_name: str,
) -> AgentTool:
    async def invoke(**arguments: Any) -> object:
        async with lock:
            result = await client.call_tool(
                descriptor.name,
                arguments,
                read_timeout_seconds=SSE_READ_TIMEOUT,
            )
        return _normalize_result(result)

    return AgentTool(
        name=exposed_name,
        description=descriptor.description,
        input_schema=descriptor.input_schema,
        coroutine=invoke,
    )


async def build_mcp_tools(
    session: AsyncSession, user_id: uuid.UUID
) -> list[AgentTool]:
    """Build lazy MCP tools; a real call opens its own short-lived Client."""
    servers = await MCPServerRepository(session).list_by_user(
        user_id, enabled_only=True
    )
    tools: list[AgentTool] = []
    seen: set[str] = set()
    for server in servers:
        try:
            connection, descriptors = await _discover_server(user_id, server)
        except Exception as exc:
            logger.warning("加载 MCP 工具失败（跳过）: %s: %s", server.name, exc)
            continue
        for descriptor in descriptors:
            name = _unique_name(server.name, descriptor.name, seen)
            tools.append(_build_stateless_tool(connection, descriptor, name))
    return tools


@asynccontextmanager
async def open_mcp_tools(session: AsyncSession, user_id: uuid.UUID):
    """Open one persistent MCP Client per server for the surrounding agent turn."""
    servers = await MCPServerRepository(session).list_by_user(
        user_id, enabled_only=True
    )
    stack = AsyncExitStack()
    tools: list[AgentTool] = []
    seen: set[str] = set()
    try:
        for server in servers:
            try:
                connection = build_connection(server)
                client = await stack.enter_async_context(open_mcp_client(connection))
                descriptors = _cached_descriptors(user_id, server)
                if descriptors is None:
                    descriptors = _store_descriptors(
                        user_id, server, await _list_descriptors(client)
                    )
            except Exception as exc:
                logger.warning("打开 MCP 会话失败（跳过）: %s: %s", server.name, exc)
                continue
            lock = asyncio.Lock()
            for descriptor in descriptors:
                name = _unique_name(server.name, descriptor.name, seen)
                tools.append(_build_connected_tool(client, lock, descriptor, name))
        yield tools
    finally:
        try:
            await stack.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭 MCP 会话出错（忽略）: %s", exc)


def invalidate_mcp_cache(user_id: uuid.UUID | str | None = None) -> None:
    if user_id is None:
        _MCP_CACHE.clear()
        return
    uid = str(user_id)
    for key in [key for key in _MCP_CACHE if key[0] == uid]:
        _MCP_CACHE.pop(key, None)


async def fetch_tools_meta(server: MCPServer) -> list[dict]:
    connection = build_connection(server)
    async with open_mcp_client(connection) as client:
        descriptors = await _list_descriptors(client)
    return [
        {"name": tool.name, "description": tool.description[:500]}
        for tool in descriptors
    ]


__all__ = [
    "build_mcp_tools",
    "fetch_tools_meta",
    "invalidate_mcp_cache",
    "open_mcp_tools",
]
