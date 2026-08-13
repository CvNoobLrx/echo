"""C-MTEB T2Retrieval runner：把 corpus 灌进 ES → 跑 query → 输出 nDCG@10 / Recall@10 / MRR@10。

设计要点：
- 用独立命名空间 `EVAL_USER_ID`，corpus 写完跑完可清理；不污染主用户数据。
- source_id 用 corpus 项的 cid；检索按 source_id 维度算指标，符合 mteb 协议。
- 复用 `app.core.rag.retrieval` 的混合检索能力，证明的就是它在公共集上的表现。
- 评测 hybrid（向量+BM25 融合）作为默认列；若配了 rerank 则额外出「混合+rerank」列。
"""
from __future__ import annotations

import asyncio
import uuid

from app.core.rag.chunking import chunk_parent_child
from app.core.rag.indexing import (
    CHUNK_TYPE_CHILD,
    CHUNK_TYPE_PARENT,
    build_chunk_doc,
    bulk_index,
    delete_by_source,
    ensure_index,
)

from eval import clients, metrics
from eval.benchmarks._common import write_benchmark_details, write_benchmark_report
from eval.benchmarks.cmteb_t2.loader import load
from eval.run_manifest import RunManifest, stable_values_sha256

# 评测固定 k = 10（C-MTEB 官方设定）
K = 10
RECALL = 50  # 召回深度（足以覆盖 top-10）

# 单独的 user_id 命名空间避免污染 fixtures 数据
_CMTEB_USER_ID = uuid.UUID("eee10000-0000-0000-0000-0000000000c2")


def _score(per_query: list[tuple[list, list]]) -> dict:
    return {
        f"nDCG@{K}": metrics.avg([metrics.ndcg_at_k(r, g, K) for r, g in per_query]),
        f"Recall@{K}": metrics.avg([metrics.recall_at_k(r, g, K) for r, g in per_query]),
        f"MRR@{K}": metrics.avg([metrics.mrr(r[:K], g) for r, g in per_query]),
    }


async def _ingest_corpus(embed_client, corpus: list[dict]) -> int:
    """把 corpus 灌进 ES（每项一份 document，分块 + 向量化 + 写库）。"""
    await ensure_index()
    uid = str(_CMTEB_USER_ID)
    total = len(corpus)
    print(f"  [cmteb-t2] 灌入 corpus：共 {total} 篇…")
    for i, item in enumerate(corpus, 1):
        cid = item["cid"]
        title = item.get("title", "")
        body = item.get("text", "")
        text = (title + "\n\n" + body).strip() if title else body
        if not text:
            print(f"    [{i}/{total}] cid={cid} 空文本,跳过")
            continue
        parents = chunk_parent_child(text)
        n_children = sum(len(p.children) for p in parents)
        await delete_by_source(uid, cid)  # 幂等
        es_docs: list[dict] = []
        for parent in parents:
            parent_doc = build_chunk_doc(
                user_id=uid, source_type="document", source_id=cid,
                doc_name=title or cid, chunk_type=CHUNK_TYPE_PARENT,
                content=parent.content, vector=None,
            )
            es_docs.append(parent_doc)
            if parent.children:
                # 子块向量化批量
                vectors = await embed_client.embed(parent.children)
                for child, vec in zip(parent.children, vectors):
                    es_docs.append(build_chunk_doc(
                        user_id=uid, source_type="document", source_id=cid,
                        doc_name=title or cid, chunk_type=CHUNK_TYPE_CHILD,
                        content=child, vector=vec, parent_id=parent_doc["_id"],
                    ))
        if es_docs:
            await bulk_index(es_docs)
        print(f"    [{i}/{total}] cid={cid} | {len(parents)} 父块 / {n_children} 子块 | {title[:40]}")
    return total


async def _clear_corpus() -> None:
    """清掉本 benchmark 命名空间下的所有 chunk（独立 user_id 不影响 fixtures）。"""
    from app.core.rag.indexing import CHUNKS_INDEX
    from app.db.elastic import get_es
    es = get_es()
    try:
        await es.delete_by_query(
            index=CHUNKS_INDEX,
            body={"query": {"term": {"user_id": str(_CMTEB_USER_ID)}}},
            refresh=True,
            conflicts="proceed",
        )
    except Exception as e:  # noqa: BLE001
        print(f"[cmteb-t2] 清理 ES 失败（忽略）: {e}")


async def run_benchmark(
    embed_client, rerank_client=None, *,
    corpus_limit: int | None = None,
    query_limit: int | None = None,
    skip_ingest: bool = False,
    keep_corpus: bool = False,
    run: RunManifest,
) -> tuple[dict, list]:
    """跑 C-MTEB T2Retrieval。

    Args:
        embed_client / rerank_client: 由 run_eval 注入
        corpus_limit / query_limit: 本地快速验证用（默认全跑）
        skip_ingest: 已灌过数据则跳过重新写入
        keep_corpus: 跑完保留 corpus（默认会清理）
    """
    print("[cmteb-t2] 加载数据集…")
    data = load(corpus_limit=corpus_limit, query_limit=query_limit)
    corpus = data["corpus"]
    queries = data["queries"]
    print(f"  corpus={len(corpus)} 篇，queries={len(queries)} 条（split={data['split']}）")
    run.record_dataset("cmteb-t2", {
        "repository": "mteb/T2Retrieval",
        "revision": data["dataset_revision"],
        "split": data["split"],
        "requested_corpus_limit": data["requested_corpus_limit"],
        "actual_corpus_size": len(corpus),
        "query_count": len(queries),
        "query_ids_sha256": stable_values_sha256([query["qid"] for query in queries]),
        "gold_docs_added": data["gold_docs_added"],
        "gold_coverage": data["gold_coverage"],
    })

    n_docs = 0
    if not skip_ingest:
        await _clear_corpus()
        n_docs = await _ingest_corpus(embed_client, corpus)
        # 给 ES 一点时间索引完成
        await asyncio.sleep(2)

    uid = str(_CMTEB_USER_ID)
    scored: list[tuple[list, list]] = []
    details: list[dict] = []
    total = len(queries)
    for i, q in enumerate(queries, 1):
        qtext = q["text"]
        gold = q["relevant_doc_ids"]
        print(f"  [cmteb-t2] {i}/{total}  qid={q['qid']}")
        print(f"    Q: {qtext[:80]}")
        ranked = await clients.retrieve_project_config(
            embed_client,
            rerank_client,
            uid,
            qtext,
            top_k=K,
            recall=RECALL,
        )
        scored.append((ranked, gold))
        hit = bool(set(ranked[:K]) & set(gold))
        d = {
            "qid": q["qid"],
            "question": qtext,
            "gold": gold,
            "retrieved_topk": ranked[:K],
            "hit": hit,
        }
        mark = "✓" if hit else "✗"
        print(f"    {mark} 当前配置 top-{K} 命中: {hit}")
        details.append(d)

    label = "当前配置(Hybrid+Rerank)" if rerank_client else "当前配置(Hybrid)"
    table = {label: _score(scored)}

    meta = {
        "数据集": "C-MTEB/T2Retrieval",
        "切分": data["split"],
        "corpus 篇数": len(corpus),
        "query 条数": len(queries),
        "数据集 revision": data["dataset_revision"],
        "请求 corpus 上限": data["requested_corpus_limit"],
        "为 gold 补入文档": data["gold_docs_added"],
        "gold 文档覆盖率": data["gold_coverage"],
        "评测命名空间": str(_CMTEB_USER_ID),
        "embedding 模型": embed_client.model_name,
        "rerank 模型": rerank_client.model_name if rerank_client else "（未配置）",
        "检索配置": "Hybrid(vector=0.6, BM25=0.4), recall=50, top_k=10",
    }
    if not skip_ingest:
        meta["本次写入"] = f"{n_docs} 篇"

    notes = [
        "C-MTEB T2Retrieval 评测：用真实中文搜索场景的 corpus 与 query，"
        "记录当前项目检索配置的绝对指标，不作排行榜或模型领先性断言。",
        "指标遵循 C-MTEB 官方协议（k=10）；source_id 用 corpus 原 cid。",
    ]
    report = write_benchmark_report("cmteb-t2", "C-MTEB T2Retrieval (L2)",
                                    table, meta=meta, extra_notes=notes,
                                    category="rag", run=run)
    detail_path = write_benchmark_details(
        "cmteb-t2", details, category="rag", run=run,
    )
    print(f"  报告: {report}\n  明细: {detail_path}")

    if not keep_corpus:
        print("[cmteb-t2] 清理 corpus…")
        await _clear_corpus()

    return table, details
