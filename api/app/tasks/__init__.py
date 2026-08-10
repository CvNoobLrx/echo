"""Celery 任务包。各阶段在此新增任务模块：

- parse   文档/图片解析（阶段3）
- memory  记忆萃取/去重（阶段4）
- image   图片识别与入库
"""
from app.celery_app import celery_app


@celery_app.task(name="app.tasks.ping")
def ping() -> str:
    """连通性自检任务。"""
    return "pong"
