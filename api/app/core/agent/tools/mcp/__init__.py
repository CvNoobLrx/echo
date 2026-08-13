"""MCP 工具接入：把外部 MCP server 的工具转成原生 AgentTool。

基于官方 MCP Python SDK 2.x：
- connection：MCPServer 行 → 官方 Client/transport（含解密认证、SSRF 校验）
- loader：build_mcp_tools（问答用）+ fetch_tools_meta（test/sync 用）
"""
