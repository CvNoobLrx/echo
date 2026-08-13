"""C-MTEB T2Retrieval 数据加载（HuggingFace datasets）。

数据集结构（mteb 风格）：
- corpus:  {_id, title, text}    —— 文档集合
- queries: {_id, text}           —— 查询集合
- qrels:   {query-id, corpus-id, score}  —— 相关性标注（dev/test 切分）

我们用 dev 切分（约 2k 量级，跑得动）。首次下载会缓存到 `api/eval/cache/`。
"""
from __future__ import annotations

from typing import TypedDict

from eval.benchmarks._common import cache_path

# HuggingFace 上的数据集 id(MMTEB 统一迁移到 `mteb/` 组织下,旧路径 `C-MTEB/T2Retrieval`
# 只剩 default config,新路径保留完整三 subset 结构 corpus/queries/default)
_HF_REPO = "mteb/T2Retrieval"
_HF_REVISION = "921dd3af6e78d1ae7ee0368aa8d7eaee02c8f08e"


class CMTEBQuery(TypedDict):
    qid: str
    text: str
    relevant_doc_ids: list[str]


class CMTEBCorpusItem(TypedDict):
    cid: str
    title: str
    text: str


class CMTEBData(TypedDict):
    corpus: list[CMTEBCorpusItem]
    queries: list[CMTEBQuery]
    split: str
    dataset_revision: str
    requested_corpus_limit: int | None
    gold_docs_added: int
    gold_coverage: float


def load(split: str = "dev", corpus_limit: int | None = None,
         query_limit: int | None = None) -> CMTEBData:
    """加载 T2Retrieval 数据。corpus_limit / query_limit 用于本地小规模快速验证。

    返回:
        corpus:  [{cid, title, text}, ...]
        queries: [{qid, text, relevant_doc_ids: [cid, ...]}, ...]
    """
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise RuntimeError(
            "缺少 datasets 依赖。请在 api/ 下执行：uv sync（已在 pyproject.toml 加入）"
        ) from e

    cache_dir = str(cache_path("hf_datasets").parent)  # HF 自管缓存目录

    # 加载 queries
    ds_queries = load_dataset(
        _HF_REPO, "queries", cache_dir=cache_dir, split="dev", revision=_HF_REVISION,
    )
    qmap: dict[str, str] = {}
    for row in ds_queries:
        qid = str(row.get("_id") or row.get("id"))
        qmap[qid] = (row.get("text") or "").strip()

    # 加载 qrels(标注,default subset / dev split)—— 形如 {query-id, corpus-id, score}
    ds_qrels = load_dataset(
        _HF_REPO, "default", cache_dir=cache_dir, split=split, revision=_HF_REVISION,
    )
    qrel_by_query: dict[str, list[str]] = {}
    for row in ds_qrels:
        qid = str(row.get("query-id") or row.get("query_id"))
        cid = str(row.get("corpus-id") or row.get("corpus_id"))
        score = float(row.get("score") or 1.0)
        if score <= 0:
            continue
        qrel_by_query.setdefault(qid, []).append(cid)

    # 装配 query 集
    queries: list[CMTEBQuery] = []
    for qid, rel_cids in qrel_by_query.items():
        if qid not in qmap:
            continue
        queries.append({"qid": qid, "text": qmap[qid], "relevant_doc_ids": rel_cids})
    if query_limit is not None:
        queries = queries[:query_limit]

    # 先按 corpus_limit 取基础子集，再补齐所选 query 的全部 gold 文档。
    # 否则简单截断 corpus 会把 gold 排除在候选集合外，指标不再反映检索能力。
    required_gold = {
        cid for query in queries for cid in query["relevant_doc_ids"]
    }
    ds_corpus = load_dataset(
        _HF_REPO, "corpus", cache_dir=cache_dir, split="dev", revision=_HF_REVISION,
    )
    corpus: list[CMTEBCorpusItem] = []
    seen: set[str] = set()
    gold_docs_added = 0
    for i, row in enumerate(ds_corpus):
        cid = str(row.get("_id") or row.get("id") or i)
        in_base = corpus_limit is None or i < corpus_limit
        if not in_base and cid not in required_gold:
            continue
        corpus.append({
            "cid": cid,
            "title": (row.get("title") or "").strip(),
            "text": (row.get("text") or "").strip(),
        })
        seen.add(cid)
        if not in_base:
            gold_docs_added += 1

    covered_gold = required_gold & seen
    gold_coverage = len(covered_gold) / len(required_gold) if required_gold else 1.0
    if gold_coverage < 1.0:
        missing = sorted(required_gold - seen)[:5]
        raise RuntimeError(f"C-MTEB 子集缺少 gold 文档: {missing}")

    return {
        "corpus": corpus,
        "queries": queries,
        "split": split,
        "dataset_revision": _HF_REVISION,
        "requested_corpus_limit": corpus_limit,
        "gold_docs_added": gold_docs_added,
        "gold_coverage": gold_coverage,
    }
