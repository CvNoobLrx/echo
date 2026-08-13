"""评测总入口:读配置 → (① 自制集 或 ①.5 公共集) → 输出报告+明细 → (可选)清理。

用法:
    # ① 自制集(L1,默认)
    uv run python -m eval.run_eval                 # 全流程(模型自检 + setup + 全部评测,保留数据)
    uv run python -m eval.run_eval --reset         # 重跑:先清空旧数据再写入评测(推荐)
    uv run python -m eval.run_eval --skip-setup    # 跳过写入,直接评测(数据已写过)
    uv run python -m eval.run_eval --only retrieval # 只跑某项 retrieval/extraction/dedup/memory
    uv run python -m eval.run_eval --teardown      # 跑完清理评测数据

    # ①.5 公共评测基准(L2/L3)—— 默认轻量,跑通流程 + 出方向性数据
    uv run python -m eval.run_eval --benchmark cmteb-t2     # L2 中文检索(默认 corpus 1000/query 100,~10 分钟)
    uv run python -m eval.run_eval --benchmark hotpotqa     # L3 多跳推理(默认 100 题分层,~40 分钟)
    uv run python -m eval.run_eval --benchmark all          # 两套都跑(轻量默认)

    # 想放大就显式传(出更稳的简历数据)
    uv run python -m eval.run_eval --benchmark cmteb-t2 --corpus-limit 3000 --query-limit 300
    uv run python -m eval.run_eval --benchmark hotpotqa --sample 200

依赖:复制 eval/.env.eval.example 为 eval/.env.eval 并填模型 key(embedding 必需、chat 必需、rerank 可选)。
存储用 docker-compose 起的 PG/ES/Neo4j/Redis。
"""
import argparse
import asyncio
import sys

from app.config import settings
from app.db import elastic, neo4j, postgres, redis

from eval import clients, eval_config, reporters
from eval.pipeline.setup import setup_all
from eval.pipeline.teardown import teardown
from eval.tasks import dedup as t_dedup
from eval.tasks import extraction as t_extraction
from eval.tasks import retrieval as t_retrieval
from eval.run_manifest import RunManifest, describe_model


def _needs_chat(args) -> bool:
    if args.benchmark:
        return args.benchmark in ("hotpotqa", "all")
    if not args.skip_setup:
        return True
    return args.only in (None, "extraction", "dedup")


async def _check_storage(args) -> dict[str, bool]:
    """Check only the stores touched by the selected evaluation."""
    checks: dict[str, bool] = {}
    if args.use_app_models:
        checks["postgresql"] = await postgres.ping()
    checks["elasticsearch"] = await elastic.ping()
    if not args.benchmark:
        checks["neo4j"] = await neo4j.ping()
        checks["redis"] = await redis.ping()
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(f"存储连通性检查失败: {', '.join(failed)}")
    return checks


async def _check_models(embed, chat, rerank, need_chat: bool = True):
    """跑评测前先确认模型真的能调通,避免灌了一半数据才发现 key/url 错。

    embedding 必须可用(不通直接中止);chat 视任务需要(默认必需);
    rerank 可选,不通则打印告警并返回 None(评测自动跳过 rerank 对比)。
    返回最终可用的 rerank client(可能为 None)。
    """
    print("[check] 模型可用性自检…")

    # embedding(必需)—— 顺带校验维度是否与 ES 索引一致
    try:
        v = await embed.embed_one("评测连通性测试")
    except Exception as e:
        raise RuntimeError(f"embedding 模型不可用({embed.model_name}):{e}") from e
    dim = len(v)
    if dim != settings.embedding_dims:
        raise RuntimeError(
            f"embedding 维度 {dim} 与 ES 索引维度 {settings.embedding_dims} 不一致"
        )
    print(f"  ✓ embedding 可用({embed.model_name},维度 {dim})")

    # chat
    if need_chat:
        assert chat is not None
        try:
            txt = await chat.chat([{"role": "user", "content": "回复两个字:可用"}], max_tokens=16)
        except Exception as e:
            raise RuntimeError(f"chat 模型不可用({chat.model_name}):{e}") from e
        print(f"  ✓ chat 可用({chat.model_name}):{(txt or '').strip()[:20]}")
    else:
        print("  - 当前 benchmark 不需要 chat 模型,跳过 chat 自检")

    # rerank(可选)
    if rerank is None:
        print("  - 未配置 rerank,将跳过 rerank 对比列")
        return None, dim
    try:
        await rerank.rerank("测试查询", ["相关的文档内容", "完全无关的内容"], top_n=2)
        print(f"  ✓ rerank 可用({rerank.model_name})")
        return rerank, dim
    except Exception as e:
        print(f"  ⚠ rerank 不可用({rerank.model_name}),跳过 rerank 对比:{e}")
        return None, dim


async def _run_fixtures(args, embed, chat, rerank, run: RunManifest) -> None:
    """① 自制集评测流程(原 L1)。"""
    only = args.only
    setup_stats = None
    run.record_dataset("fixtures", {
        "corpus_documents": 10,
        "dialogues": 17,
        "rag_questions": 22,
        "memory_questions": 19,
        "extraction_cases": 10,
        "dedup_cases": 3,
        "rag_top_k": t_retrieval.K,
        "rag_recall_depth": t_retrieval.RECALL,
        "retrieval_config": {
            "vector_weight": 0.6,
            "bm25_weight": 0.4,
            "rerank_enabled": rerank is not None,
        },
        "tracing_enabled": settings.tracing_enabled,
        "reflection_trigger_threshold": settings.reflection_trigger_threshold,
        "entity_match": "normalized substring match; 用户 exact only",
    })

    # 0.5 可选:先清空评测命名空间旧数据
    if args.reset and not args.skip_setup:
        print("[reset] 清空旧评测数据(ES + Neo4j)…")
        await teardown()
    # 1. 写入(除非 --skip-setup)
    if not args.skip_setup:
        assert chat is not None
        print("[setup] 写入评测语料与记忆…")
        setup_stats = await setup_all(chat, embed)
        print(f"[setup] 完成:{setup_stats}")

    # 2. 各评测
    results: dict = {}
    details: dict = {}

    if only in (None, "retrieval"):
        print("[eval] RAG 检索…")
        results["RAG 检索"], details["RAG 检索"] = await t_retrieval.eval_rag(embed, rerank)
    if only in (None, "memory"):
        print("[eval] 记忆检索…")
        results["记忆检索"], details["记忆检索"] = await t_retrieval.eval_memory(embed)
    if only in (None, "extraction"):
        assert chat is not None
        print("[eval] 三元组抽取…")
        results["三元组抽取"], details["三元组抽取"] = await t_extraction.eval_extraction(chat)
    if only in (None, "dedup"):
        assert chat is not None
        print("[eval] 实体去重…")
        results["实体去重"], details["实体去重"] = await t_dedup.eval_dedup(chat, embed)

    # 3. 输出
    reporters.print_summary(results)
    rpt = reporters.write_report(results, run, setup_stats)
    det = reporters.write_details(details, run)
    print(f"\n报告:{rpt}\n明细:{det}")

    # 4. 可选清理
    if args.teardown:
        print("[teardown] 清理评测数据…")
        await teardown()


async def _run_benchmark(args, embed, chat, rerank, run: RunManifest) -> None:
    """①.5 公共评测基准入口。"""
    name = args.benchmark
    targets = ["cmteb-t2", "hotpotqa"] if name == "all" else [name]
    for bm in targets:
        print(f"\n========== ①.5 benchmark: {bm} ==========")
        if bm == "cmteb-t2":
            from eval.benchmarks.cmteb_t2 import run_benchmark
            await run_benchmark(
                embed, rerank,
                corpus_limit=args.corpus_limit,
                query_limit=args.query_limit,
                skip_ingest=args.skip_setup,
                keep_corpus=args.keep_corpus,
                run=run,
            )
        elif bm == "hotpotqa":
            from eval.benchmarks.hotpotqa import run_benchmark
            assert chat is not None
            await run_benchmark(
                embed, chat, rerank,
                sample=args.sample,
                verifier=args.verifier,
                seed=args.seed,
                verifier_client_factory=eval_config.verifier_client,
                run=run,
            )
        else:
            print(f"  未知 benchmark: {bm}")


async def _run(args) -> None:
    request = {"argv": sys.argv[1:], **vars(args)}
    run = RunManifest(request=request)
    run.write()
    try:
        need_chat = _needs_chat(args)
        if not args.skip_check:
            print("[check] 存储连通性自检…")
            run.checks["storage"] = await _check_storage(args)
            run.write()

        if args.use_app_models:
            embed, chat, rerank = await eval_config.app_model_clients(
                args.app_user,
                need_chat=need_chat,
            )
            model_source = "app"
        else:
            embed = eval_config.embed_client()
            chat = eval_config.chat_client() if need_chat else None
            rerank = eval_config.rerank_client()
            model_source = "eval-env"

        run.models = {
            "source": model_source,
            "embedding": describe_model(embed),
            "chat": describe_model(chat),
            "rerank": describe_model(rerank),
        }
        run.write()

        if not args.skip_check:
            rerank, embedding_dimensions = await _check_models(
                embed, chat, rerank, need_chat=need_chat,
            )
            run.models["embedding"]["dimensions"] = embedding_dimensions
            run.checks["models"] = {
                "embedding": True,
                "chat": True if need_chat else "not-required",
                "rerank": True if rerank is not None else "not-configured-or-unavailable",
            }
            run.write()

        if args.check_only:
            print(f"[check] 预检完成,manifest: {run.path}")
            run.complete()
            return

        if args.benchmark:
            await _run_benchmark(args, embed, chat, rerank, run)
        else:
            await _run_fixtures(args, embed, chat, rerank, run)
        run.complete()
    except BaseException as exc:
        run.fail(exc)
        raise
    finally:
        await clients.close_clients()


def main() -> None:
    p = argparse.ArgumentParser(description="Echo 离线评测(RAG + 记忆,L1 自制集 + L2/L3 公共基准)")
    # 通用
    p.add_argument("--skip-check", action="store_true", help="跳过模型可用性自检")
    p.add_argument(
        "--check-only",
        action="store_true",
        help="只检查所需存储与模型,不写入评测数据",
    )
    p.add_argument(
        "--use-app-models",
        action="store_true",
        help="复用应用数据库中指定用户的默认模型配置",
    )
    p.add_argument(
        "--app-user",
        help="--use-app-models 对应的用户名或用户 UUID",
    )

    # L1 自制集开关
    p.add_argument("--skip-setup", action="store_true", help="跳过写入,直接评测")
    p.add_argument("--reset", action="store_true", help="setup 前先清空旧评测数据(推荐重跑时用)")
    p.add_argument("--teardown", action="store_true", help="跑完清理评测数据")
    p.add_argument("--only", choices=["retrieval", "memory", "extraction", "dedup"],
                   help="只跑某一项(L1)")

    # ①.5 公共基准开关
    p.add_argument(
        "--benchmark",
        choices=["cmteb-t2", "hotpotqa", "all"],
        help="跑 ①.5 公共评测基准(指定后忽略 --only 等 L1 选项)",
    )
    # cmteb-t2 控制
    p.add_argument("--corpus-limit", type=int, default=1000,
                   help="[cmteb-t2] corpus 数量上限（默认 1000，全量约 100w 篇极重）")
    p.add_argument("--query-limit", type=int, default=100,
                   help="[cmteb-t2] query 数量上限（默认 100，全量约 2k 条）")
    p.add_argument("--keep-corpus", action="store_true",
                   help="[cmteb-t2] 跑完保留 corpus（默认会清理）")
    # hotpotqa 控制
    p.add_argument("--sample", type=int, default=100,
                   help="[hotpotqa] 采样题数（默认 100，分层 bridge/comparison；全量 dev 约 7400 题极重）")
    p.add_argument("--verifier", choices=["none", "same", "cross"], default="none",
                   help="[hotpotqa] Verifier 配置（等 ② Verifier Loop 完成后启用）")
    p.add_argument("--seed", type=int, default=42, help="[hotpotqa] 采样种子")

    args = p.parse_args()
    if args.check_only and args.skip_check:
        p.error("--check-only 不能与 --skip-check 同时使用")
    if args.use_app_models and not args.app_user:
        p.error("--use-app-models 需要同时传 --app-user")
    if args.app_user and not args.use_app_models:
        p.error("--app-user 只能与 --use-app-models 一起使用")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
