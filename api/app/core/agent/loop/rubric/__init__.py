"""Rubric:Verifier 评分维度定义。

研究 rubric 字段定义直接对齐 ① 离线评测的指标
(尤其 RAGAS faithfulness 对齐到「引用对齐」),做到「评测 - 生产一致性」。
"""
from app.core.agent.loop.rubric.research import RESEARCH_RUBRIC

# 名字 → rubric 注册表(controller 按 rubric_name 取)
RUBRICS = {
    "research": RESEARCH_RUBRIC,
}

__all__ = ["RUBRICS", "RESEARCH_RUBRIC"]
