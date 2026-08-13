"""评测独立配置：直接用 .env.eval 里的模型 key 建 LLMClient，不依赖 app 的「用户+模型配置表」。

设计：评测自带模型凭证 + 固定评测命名空间 EVAL_USER_ID（数据写它名下、可整体清理），
从而完全自包含、可复现，不需要在系统里先建用户/配模型/灌数据。
"""
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

from app.core.llm.client import LLMClient
from app.core.security import decrypt_secret
from app.db.postgres import SessionLocal
from app.models.model_config_model import ModelConfig
from app.models.user_model import User

# 加载评测专用环境变量（与 app 的 .env 隔离）
load_dotenv(Path(__file__).parent / ".env.eval")

# 固定评测命名空间：所有评测数据写在此 user_id 下，便于隔离与一键清理
EVAL_USER_ID = uuid.UUID("eee00000-0000-0000-0000-0000000000ee")


def _build(prefix: str) -> LLMClient | None:
    base = os.getenv(f"{prefix}_BASE_URL")
    key = os.getenv(f"{prefix}_KEY")
    model = os.getenv(f"{prefix}_MODEL")
    if not (base and key and model):
        return None
    return LLMClient(base_url=base, api_key=key, model_name=model)


def embed_client() -> LLMClient:
    c = _build("EVAL_EMBED")
    if c is None:
        raise RuntimeError("缺少 EVAL_EMBED_* 配置（请复制 .env.eval.example 为 .env.eval 并填写）")
    return c


def chat_client() -> LLMClient:
    c = _build("EVAL_CHAT")
    if c is None:
        raise RuntimeError("缺少 EVAL_CHAT_* 配置（请复制 .env.eval.example 为 .env.eval 并填写）")
    return c


def rerank_client() -> LLMClient | None:
    """可选；未配置返回 None（评测时跳过 rerank 相关项）。"""
    return _build("EVAL_RERANK")


def verifier_client() -> LLMClient | None:
    """V0.0.5 ② Verifier Loop 的「跨 family」验证模型(评测期专用)。

    未配置返回 None,hotpotqa A/B 实验时:
    - --verifier=cross 时若 None 自动降级到 same 并打 warning
    - --verifier=same 时不使用,本函数不调
    """
    return _build("EVAL_VERIFIER")


def _pick_default(configs: list[ModelConfig], type_: str) -> ModelConfig | None:
    typed = [config for config in configs if config.type == type_]
    if not typed:
        return None
    return next((config for config in typed if config.is_default), typed[0])


async def app_model_clients(
    user: str,
    *,
    need_chat: bool,
) -> tuple[LLMClient, LLMClient | None, LLMClient | None]:
    """Load one user's default app models without exposing or persisting API keys."""
    try:
        user_id = uuid.UUID(user)
    except ValueError:
        user_id = None

    async with SessionLocal() as session:
        user_stmt = select(User)
        if user_id is not None:
            user_stmt = user_stmt.where(User.id == user_id)
        else:
            user_stmt = user_stmt.where(User.username == user)
        app_user = (await session.execute(user_stmt)).scalar_one_or_none()
        if app_user is None:
            raise RuntimeError(f"找不到应用用户: {user}")

        configs = list(
            (
                await session.execute(
                    select(ModelConfig)
                    .where(ModelConfig.user_id == app_user.id)
                    .order_by(ModelConfig.created_at.desc())
                )
            ).scalars().all()
        )

    def build(type_: str, *, required: bool) -> LLMClient | None:
        config = _pick_default(configs, type_)
        if config is None:
            if required:
                raise RuntimeError(f"用户 {app_user.username} 未配置 {type_} 模型")
            return None
        return LLMClient(
            base_url=config.base_url,
            api_key=decrypt_secret(config.api_key_encrypted),
            model_name=config.model_name,
        )

    embed = build("embedding", required=True)
    chat = build("chat", required=need_chat)
    rerank = build("rerank", required=False)
    assert embed is not None
    return embed, chat, rerank
