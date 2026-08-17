import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.memory.extraction.models import ExtractedStatement, TripletExtractionResult
from app.core.memory.extraction.orchestrator import _event_id, run_extraction
from app.core.memory.retrieval.searcher import format_memory_context
from app.repositories.neo4j import cypher_queries as cq
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository


class EventStableIdTests(unittest.TestCase):
    def test_equivalent_text_produces_same_id(self):
        occurred_at = datetime(2026, 8, 10, 6, 56, 33)

        first = _event_id(
            "user-1",
            "吃螺蛳粉",
            "用户今天吃了一碗螺蛳粉。",
            occurred_at,
            occurred_at,
        )
        second = _event_id(
            "user-1",
            " 吃 螺蛳粉 ",
            "用户今天吃了一碗螺蛳粉",
            occurred_at,
            occurred_at,
        )

        self.assertEqual(first, second)

    def test_dialogue_time_distinguishes_untimed_events(self):
        first_dialogue = datetime(2026, 8, 10, 6, 56, 33)
        second_dialogue = first_dialogue + timedelta(days=1)

        first = _event_id("user-1", "吃饭", "用户吃饭", None, first_dialogue)
        second = _event_id("user-1", "吃饭", "用户吃饭", None, second_dialogue)

        self.assertNotEqual(first, second)


class MemoryRelationFormattingTests(unittest.TestCase):
    def test_relation_surface_is_preferred_over_canonical_predicate(self):
        context = format_memory_context(
            [
                {
                    "name": "用户",
                    "type": "生命体",
                    "description": "",
                    "confidence": 0.9,
                    "relations": [
                        {
                            "predicate": "社会关系",
                            "predicate_surface": "妹妹",
                            "object_name": "林晓",
                            "confidence": 0.9,
                        }
                    ],
                }
            ]
        )

        self.assertIn("用户 妹妹 林晓", context)
        self.assertNotIn("用户 社会关系 林晓", context)


class EventBatchDeduplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_events_and_participants_are_written_once(self):
        dialogue_at = datetime(2026, 8, 10, 6, 56, 33)
        result = TripletExtractionResult(
            entities=[{"entity_idx": 0, "name": "用户", "type": "人物"}],
            events=[
                {
                    "title": "吃螺蛳粉",
                    "description": "用户今天吃了一碗螺蛳粉。",
                    "participants": ["用户", "用户"],
                },
                {
                    "title": " 吃 螺蛳粉 ",
                    "description": "用户今天吃了一碗螺蛳粉",
                    "participants": ["用户"],
                },
            ],
        )

        with (
            patch(
                "app.core.memory.extraction.orchestrator.chunker.split_chunks",
                return_value=["用户今天吃了一碗螺蛳粉。"],
            ),
            patch(
                "app.core.memory.extraction.orchestrator.statement_extractor.extract_statements",
                new=AsyncMock(
                    return_value=[ExtractedStatement(statement="用户今天吃了一碗螺蛳粉。")]
                ),
            ),
            patch(
                "app.core.memory.extraction.orchestrator.triplet_extractor.extract_triplets_batch",
                new=AsyncMock(return_value=[result]),
            ),
            patch(
                "app.core.memory.extraction.orchestrator.embedder.embed_texts",
                new=AsyncMock(return_value=[[0.1, 0.2]]),
            ),
            patch(
                "app.core.memory.extraction.orchestrator.dedup.dedup_within_batch",
                new=AsyncMock(side_effect=lambda _client, entities: (entities, {})),
            ),
            patch(
                "app.core.memory.extraction.orchestrator.dedup.merge_with_graph",
                new=AsyncMock(side_effect=lambda _client, _repo, _user, entities: (entities, {})),
            ),
            patch(
                "app.core.memory.extraction.orchestrator._persist",
                new=AsyncMock(),
            ) as persist,
            patch(
                "app.core.memory.extraction.orchestrator._maybe_trigger_reflection",
                new=AsyncMock(),
            ),
            patch(
                "app.core.memory.extraction.orchestrator.MemoryGraphRepository.merge_duplicate_events",
                new=AsyncMock(return_value=0),
            ),
        ):
            stats = await run_extraction(
                chat_client=SimpleNamespace(),
                embed_client=SimpleNamespace(),
                user_id="user-1",
                text="用户今天吃了一碗螺蛳粉。",
                dialog_at=dialogue_at,
            )

        persisted = persist.await_args.kwargs
        self.assertEqual(stats.event_count, 1)
        self.assertEqual(len(persisted["events"]), 1)
        self.assertEqual(len(persisted["involves"]), 1)
        self.assertEqual(
            persisted["events"][0].id,
            persisted["involves"][0].event_id,
        )


class HistoricalEventMergeTests(unittest.IsolatedAsyncioTestCase):
    async def test_merge_relinks_participants_before_deleting_duplicate(self):
        calls: list[tuple[str, dict]] = []

        class _Rows:
            def __init__(self, rows):
                self._rows = rows

            def __aiter__(self):
                async def iterate():
                    for row in self._rows:
                        yield row

                return iterate()

        class _Tx:
            async def run(self, query: str, **params):
                calls.append((query, params))
                if query == cq.EVENT_DUPLICATE_GROUPS:
                    return _Rows([{"ids": ["event-b", "event-a"]}])
                if query == cq.EVENT_PARTICIPANTS:
                    return _Rows(
                        [
                            {
                                "entity_id": "entity-1",
                                "role": "参与者",
                                "created_at": "2026-08-10T06:56:33",
                            }
                        ]
                    )
                return _Rows([])

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def execute_write(self, callback):
                return await callback(_Tx())

        class _Driver:
            def session(self):
                return _Session()

        repo = MemoryGraphRepository.__new__(MemoryGraphRepository)
        repo._driver = _Driver()

        removed = await repo.merge_duplicate_events("user-1")

        self.assertEqual(removed, 1)
        self.assertEqual(
            [query for query, _ in calls],
            [
                cq.EVENT_DUPLICATE_GROUPS,
                cq.EVENT_PARTICIPANTS,
                cq.EVENT_RELINK_PARTICIPANTS,
                cq.EVENT_DELETE_DUPLICATE,
            ],
        )
        self.assertEqual(calls[2][1]["keep_id"], "event-a")
        self.assertEqual(calls[3][1]["event_id"], "event-b")

    def test_historical_merge_only_targets_events_with_explicit_time(self):
        self.assertIn("WHERE ev.event_time IS NOT NULL", cq.EVENT_DUPLICATE_GROUPS)


if __name__ == "__main__":
    unittest.main()
