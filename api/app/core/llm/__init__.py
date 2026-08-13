"""原生 LLM provider 适配层。

四个 provider（openai/qwen/doubao/deepseek）均兼容 OpenAI 接口，
差异主要在 base_url 与默认模型，连接测试统一走 OpenAI 兼容协议。
"""

from app.core.llm.native_chat import NativeChatModel
from app.core.llm.types import ChatMessage, ToolCall, Usage

__all__ = ["ChatMessage", "NativeChatModel", "ToolCall", "Usage"]
