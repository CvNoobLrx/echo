"""聚合 Echo 保留的 API 路由。"""
from fastapi import APIRouter

from app.controllers import (
    agent_config_controller,
    agent_persona_controller,
    auth_controller,
    chat_controller,
    dashboard_controller,
    document_controller,
    favorite_controller,
    file_controller,
    health_controller,
    image_controller,
    knowledge_base_controller,
    mcp_controller,
    memory_controller,
    model_config_controller,
    notify_controller,
    persona_group_controller,
    research_controller,
    skill_controller,
    tag_controller,
    tool_controller,
    trace_controller,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health_controller.router)
api_router.include_router(auth_controller.router)
api_router.include_router(model_config_controller.router)
api_router.include_router(document_controller.router)
api_router.include_router(image_controller.router)
api_router.include_router(knowledge_base_controller.router)
api_router.include_router(tag_controller.router)
api_router.include_router(file_controller.router)
api_router.include_router(memory_controller.router)
api_router.include_router(chat_controller.router)
api_router.include_router(agent_config_controller.router)
api_router.include_router(agent_persona_controller.router)
api_router.include_router(persona_group_controller.router)
api_router.include_router(mcp_controller.router)
api_router.include_router(tool_controller.router)
api_router.include_router(favorite_controller.router)
api_router.include_router(dashboard_controller.router)
api_router.include_router(research_controller.router)
api_router.include_router(notify_controller.router)
api_router.include_router(skill_controller.router)
api_router.include_router(trace_controller.router)
