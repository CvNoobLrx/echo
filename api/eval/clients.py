"""Evaluation access to the project's current document retrieval pipeline."""
from app.core.rag.indexing import CHUNK_TYPE_CHILD, CHUNKS_INDEX
from app.core.llm.client import close_llm_client
from app.db.elastic import close as _es_close
from app.db.elastic import get_es
from app.db.neo4j import close as _neo_close
from app.db.postgres import close as _pg_close
from app.db.redis import close as _redis_close


def _base_filter(uid: str) -> list[dict]:
    return [{"term": {"user_id": uid}}, {"term": {"chunk_type": CHUNK_TYPE_CHILD}}]


def _dedup_sources(hits: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        sid = h["_source"].get("source_id")
        if sid and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


async def retrieve_vector(embed_client, uid: str, query: str, recall: int = 20) -> list[str]:
    es = get_es()
    qv = await embed_client.embed_one(query)
    resp = await es.search(index=CHUNKS_INDEX, body={
        "size": recall,
        "query": {"bool": {"filter": _base_filter(uid)}},
        "knn": {"field": "vector", "query_vector": qv, "k": recall,
                "num_candidates": recall * 5, "filter": {"bool": {"filter": _base_filter(uid)}}},
    })
    return _dedup_sources(resp["hits"]["hits"])


async def retrieve_bm25(uid: str, query: str, recall: int = 20) -> list[str]:
    es = get_es()
    resp = await es.search(index=CHUNKS_INDEX, body={
        "size": recall,
        "query": {"bool": {"must": [{"match": {"content": query}}], "filter": _base_filter(uid)}},
    })
    return _dedup_sources(resp["hits"]["hits"])


async def retrieve_hybrid(embed_client, uid: str, query: str, recall: int = 20,
                          wv: float = 0.6, wb: float = 0.4) -> list[str]:
    es = get_es()
    qv = await embed_client.embed_one(query)
    knn = await es.search(index=CHUNKS_INDEX, body={
        "size": recall, "query": {"bool": {"filter": _base_filter(uid)}},
        "knn": {"field": "vector", "query_vector": qv, "k": recall, "num_candidates": recall * 5,
                "filter": {"bool": {"filter": _base_filter(uid)}}}})
    bm = await es.search(index=CHUNKS_INDEX, body={
        "size": recall, "query": {"bool": {"must": [{"match": {"content": query}}],
                                           "filter": _base_filter(uid)}}})
    chunk_src: dict[str, str] = {}
    vs: dict[str, float] = {}
    bs: dict[str, float] = {}
    for h in knn["hits"]["hits"]:
        vs[h["_id"]] = h["_score"]
        chunk_src[h["_id"]] = h["_source"].get("source_id")
    for h in bm["hits"]["hits"]:
        bs[h["_id"]] = h["_score"]
        chunk_src[h["_id"]] = h["_source"].get("source_id")
    vn, bn = _normalize(vs), _normalize(bs)
    fused = {cid: wv * vn.get(cid, 0.0) + wb * bn.get(cid, 0.0) for cid in chunk_src}
    seen: set[str] = set()
    out: list[str] = []
    for cid in sorted(fused, key=fused.get, reverse=True):
        sid = chunk_src.get(cid)
        if sid and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


async def retrieve_project_config(
    embed_client,
    rerank_client,
    uid: str,
    query: str,
    *,
    top_k: int,
    recall: int = 20,
) -> list[str]:
    """Run the same 0.6/0.4 hybrid fusion and optional rerank as the app."""
    ranked = await retrieve_hybrid(embed_client, uid, query, recall, wv=0.6, wb=0.4)
    if rerank_client is not None and ranked:
        return await rerank_sources(rerank_client, uid, query, ranked[:recall], top_k)
    return ranked[:top_k]


async def rerank_sources(rerank_client, uid: str, query: str,
                         source_ids: list[str], top_k: int) -> list[str]:
    """对候选 source 取代表 chunk 内容做 cross-encoder rerank，返回重排后的 source_id。"""
    if not source_ids:
        return []
    es = get_es()
    contents: list[str] = []
    for sid in source_ids:
        resp = await es.search(index=CHUNKS_INDEX, body={
            "size": 1,
            "query": {"bool": {"filter": [
                {"term": {"user_id": uid}}, {"term": {"source_id": sid}},
            ]}},
        })
        hits = resp["hits"]["hits"]
        contents.append(hits[0]["_source"].get("content", "") if hits else "")
    pairs = await rerank_client.rerank(query, contents, top_n=top_k)
    return [source_ids[idx] for idx, _ in pairs]


async def close_clients() -> None:
    for closer in (_es_close, _neo_close, _redis_close, _pg_close, close_llm_client):
        try:
            await closer()
        except Exception:
            pass
