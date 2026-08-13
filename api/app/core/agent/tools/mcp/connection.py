"""MCP 2.0 client connection factory with auth and SSRF protection."""
from __future__ import annotations

import ipaddress
import socket
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx2
from mcp.client import Client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from app.core.security import decrypt_secret
from app.models.mcp_server_model import (
    AUTH_API_KEY,
    AUTH_BEARER,
    TRANSPORT_SSE,
    MCPServer,
)

CONNECT_TIMEOUT = 15.0
SSE_READ_TIMEOUT = 60.0


@dataclass(frozen=True, slots=True)
class MCPConnectionConfig:
    server_id: str
    server_name: str
    transport: str
    url: str
    headers: dict[str, str]


def is_safe_url(url: str) -> bool:
    """Allow only public HTTP(S) endpoints."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    return True


def _build_headers(server: MCPServer) -> dict[str, str]:
    cfg = server.auth_config or {}
    if server.auth_type == AUTH_BEARER:
        token = cfg.get("token")
        if token:
            return {"Authorization": f"Bearer {decrypt_secret(token)}"}
    elif server.auth_type == AUTH_API_KEY:
        header_name = cfg.get("header") or "X-API-Key"
        key = cfg.get("key")
        if key:
            return {header_name: decrypt_secret(key)}
    return {}


def build_connection(server: MCPServer) -> MCPConnectionConfig:
    if not is_safe_url(server.url):
        raise ValueError("不允许访问该地址（内网/非法 URL）")
    return MCPConnectionConfig(
        server_id=str(server.id),
        server_name=server.name,
        transport=server.transport,
        url=server.url,
        headers=_build_headers(server),
    )


@asynccontextmanager
async def open_mcp_client(config: MCPConnectionConfig):
    """Open one MCP 2.0 client and own all transport resources."""
    stack = AsyncExitStack()
    try:
        if config.transport == TRANSPORT_SSE:
            transport = sse_client(
                config.url,
                headers=config.headers or None,
                timeout=CONNECT_TIMEOUT,
                sse_read_timeout=SSE_READ_TIMEOUT,
            )
            client = Client(
                transport,
                mode="legacy",
                read_timeout_seconds=SSE_READ_TIMEOUT,
                cache=None,
            )
        else:
            http_client = httpx2.AsyncClient(
                headers=config.headers or None,
                timeout=httpx2.Timeout(CONNECT_TIMEOUT, read=SSE_READ_TIMEOUT),
                follow_redirects=True,
            )
            await stack.enter_async_context(http_client)
            transport = streamable_http_client(
                config.url,
                http_client=http_client,
            )
            client = Client(
                transport,
                mode="auto",
                read_timeout_seconds=SSE_READ_TIMEOUT,
                cache=None,
            )
        connected = await stack.enter_async_context(client)
        yield connected
    finally:
        await stack.aclose()


__all__ = [
    "CONNECT_TIMEOUT",
    "MCPConnectionConfig",
    "SSE_READ_TIMEOUT",
    "build_connection",
    "is_safe_url",
    "open_mcp_client",
]
