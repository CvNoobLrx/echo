"""检索评测：当前项目 RAG 配置 + 记忆检索。指标 Recall@k / Precision@k / MRR / nDCG@k。

返回 (指标表, 明细列表)。明细记录每题召回了哪些、命中没、漏了哪些，供调策略。
"""
import json
from pathlib import Path

from app.core.memory.retrieval.searcher import search_memory
from eval import clients, metrics
from eval.eval_config import EVAL_USER_ID

_GOLD = Path(__file__).parent.parent / "fixtures" / "gold"
K = 5
RECALL = 20


def _load(name: str) -> list[dict]:
    return json.loads((_GOLD / name).read_text(encoding="utf-8"))


def _score(per_query: list[tuple[list, list]]) -> dict:
    return {
        f"Recall@{K}": metrics.avg([metrics.recall_at_k(r, g, K) for r, g in per_query]),
        f"Prec@{K}": metrics.avg([metrics.precision_at_k(r, g, K) for r, g in per_query]),
        "MRR": metrics.avg([metrics.mrr(r, g) for r, g in per_query]),
        f"nDCG@{K}": metrics.avg([metrics.ndcg_at_k(r, g, K) for r, g in per_query]),
    }


def _detail(question: str, gold: list, ranked: list) -> dict:
    topk = ranked[:K]
    return {
        "question": question,
        "gold": gold,
        "retrieved_topk": topk,
        "hit": bool(set(topk) & set(gold)),
        "missed": [g for g in gold if g not in topk],
    }


async def eval_rag(embed_client, rerank_client) -> tuple[dict, list]:
    data = _load("retrieval.json")
    uid = str(EVAL_USER_ID)
    scored: list[tuple[list, list]] = []
    details: list[dict] = []
    total = len(data)
    for i, item in enumerate(data, 1):
        q, gold = item["question"], item.get("relevant_doc_ids", [])
        print(f"    [RAG] {i}/{total} {q[:24]}…")
        ranked = await clients.retrieve_project_config(
            embed_client,
            rerank_client,
            uid,
            q,
            top_k=K,
            recall=RECALL,
        )
        scored.append((ranked, gold))
        details.append({
            "question": q,
            "gold": gold,
            "retrieved_topk": ranked[:K],
            "hit": bool(set(ranked[:K]) & set(gold)),
            "missed": [item for item in gold if item not in ranked[:K]],
        })

    label = "当前配置(Hybrid+Rerank)" if rerank_client else "当前配置(Hybrid)"
    return {label: _score(scored)}, details


async def eval_memory(embed_client) -> tuple[dict, list]:
    data = _load("memory_retrieval.json")
    per_query: list[tuple[list, list]] = []
    details: list[dict] = []
    total = len(data)
    for i, item in enumerate(data, 1):
        q, gold = item["question"], item.get("relevant_entities", [])
        print(f"    [记忆检索] {i}/{total} {q[:24]}…")
        hits = await search_memory(
            embed_client=embed_client, user_id=EVAL_USER_ID, query=q, top_k=RECALL
        )
        ranked_raw = [h.get("name") for h in hits if h.get("name")]
        ranked = metrics.canonicalize(ranked_raw, gold)  # 归一化+包含口径，更完整的名算命中
        per_query.append((ranked, gold))
        d = _detail(q, gold, ranked)
        d["retrieved_raw_topk"] = ranked_raw[:K]  # 保留原始召回名便于排查
        details.append(d)
    return {"图谱混合检索": _score(per_query)}, details
