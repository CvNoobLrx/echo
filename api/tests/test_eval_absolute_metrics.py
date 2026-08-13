"""Absolute evaluation metadata and current-config retrieval tests."""

import asyncio
import json
from argparse import Namespace

from eval import clients, eval_config, reporters, run_eval
from eval.benchmarks import _common
from eval.benchmarks.cmteb_t2 import loader as cmteb_loader
from eval.benchmarks.cmteb_t2 import runner as cmteb_runner
from eval.run_manifest import RunManifest, describe_model


class FakeModel:
    def __init__(self, model_name: str, base_url: str, api_key: str = "secret"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_key = api_key


def test_report_details_and_manifest_share_one_run_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(reporters, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(_common, "_RESULTS_DIR", tmp_path)
    run = RunManifest(
        request={"benchmark": None},
        run_id="fixed-run",
        models={"embedding": describe_model(FakeModel("embed", "https://example.test/v1"))},
    )
    monkeypatch.setattr(type(run), "path", property(lambda _self: tmp_path / "manifest-fixed-run.json"))
    run.write()

    report = reporters.write_report({"RAG": {"当前配置(Hybrid)": {"Recall@5": 1.0}}}, run)
    details = reporters.write_details({"RAG": []}, run)

    assert report.name == "report-fixed-run.md"
    assert details.name == "details-fixed-run.json"
    manifest_text = run.path.read_text(encoding="utf-8")
    assert "secret" not in manifest_text
    manifest = json.loads(manifest_text)
    assert {item["kind"] for item in manifest["artifacts"]} == {"report", "details"}


def test_current_config_retrieval_returns_single_pipeline(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_hybrid(*_args, **_kwargs):
        calls.append("hybrid")
        return ["a", "b", "c"]

    async def fake_rerank(*_args, **_kwargs):
        calls.append("rerank")
        return ["b", "a"]

    monkeypatch.setattr(clients, "retrieve_hybrid", fake_hybrid)
    monkeypatch.setattr(clients, "rerank_sources", fake_rerank)

    ranked = asyncio.run(
        clients.retrieve_project_config(
            FakeModel("embed", "https://embed.test"),
            FakeModel("rerank", "https://rerank.test"),
            "uid",
            "query",
            top_k=2,
        )
    )

    assert ranked == ["b", "a"]
    assert calls == ["hybrid", "rerank"]


def test_cmteb_subset_adds_required_gold_documents(monkeypatch) -> None:
    dataset_rows = {
        "queries": [{"_id": "q1", "text": "question"}],
        "default": [{"query-id": "q1", "corpus-id": "gold-2", "score": 1}],
        "corpus": [
            {"_id": "base-1", "title": "base", "text": "base"},
            {"_id": "gold-2", "title": "gold", "text": "gold"},
        ],
    }

    def fake_load_dataset(_repo, config, **_kwargs):
        return dataset_rows[config]

    import datasets

    monkeypatch.setattr(datasets, "load_dataset", fake_load_dataset)
    data = cmteb_loader.load(corpus_limit=1, query_limit=1)

    assert {item["cid"] for item in data["corpus"]} == {"base-1", "gold-2"}
    assert data["gold_docs_added"] == 1
    assert data["gold_coverage"] == 1.0


def test_cmteb_does_not_require_chat_model(monkeypatch) -> None:
    args = Namespace(
        benchmark="cmteb-t2",
        skip_setup=False,
        only=None,
    )
    assert run_eval._needs_chat(args) is False

    def fail_chat():
        raise AssertionError("C-MTEB must not construct a chat client")

    monkeypatch.setattr(eval_config, "chat_client", fail_chat)


def test_cmteb_mrr_is_cut_off_at_ten() -> None:
    ranked = [f"wrong-{i}" for i in range(10)] + ["gold"]
    assert cmteb_runner._score([(ranked, ["gold"])])["MRR@10"] == 0.0
