import io
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pokemon_events.cli import main
from pokemon_events.models import Category, EventStatus, PokemonEvent
from pokemon_events.services.curation import select_candidates
from pokemon_events.storage import SQLiteRepository


NOW = datetime(2026, 10, 5, 3, tzinfo=timezone.utc)


def event(event_id="goods", **overrides):
    values = dict(id=event_id, title="New Pokemon goods", category=Category.GOODS,
                  country="JP", source_name="Test", source_url=f"https://example.com/{event_id}",
                  collected_at=NOW, published_at=NOW, content_hash="v1")
    return PokemonEvent(**(values | overrides))


class CurationTest(unittest.TestCase):
    def test_goods_priority_recency_and_ended_filter(self):
        items = [event(), event("collab", category=Category.COLLAB),
                 event("game", title="Game update", category=Category.GAME),
                 event("old", published_at=NOW - timedelta(days=100)),
                 event("ended", status=EventStatus.ENDED),
                 event("past", end_date=NOW - timedelta(days=1)),
                 event("future", published_at=NOW + timedelta(days=10))]
        details = {item.id: {"types": {"NEW"}, "fields": set()} for item in items}
        candidates = select_candidates(items, details, NOW)
        self.assertEqual([item.event.id for item in candidates], ["collab", "goods"])
        self.assertIn("콜라보·협업", candidates[0].reasons)
        self.assertIn("가격·통화", candidates[0].checks)
        all_items = select_candidates(items, details, NOW, focus="all")
        self.assertIn("game", [item.event.id for item in all_items])

    def test_old_material_update_and_hash_only_exclusion(self):
        old = event(published_at=NOW - timedelta(days=100), collected_at=NOW - timedelta(days=30))
        with SQLiteRepository(":memory:") as repository:
            repository.save_event(old)
            repository.save_event(replace(old, content_hash="migration", collected_at=NOW))
            details = repository.get_recent_change_details(NOW - timedelta(days=7))
            self.assertEqual(select_candidates(repository.list_events(), details, NOW), [])
            repository.save_event(replace(old, title="Updated goods", content_hash="v2", collected_at=NOW))
            details = repository.get_recent_change_details(NOW - timedelta(days=7))
            candidates = select_candidates(repository.list_events(), details, NOW)
            self.assertEqual(candidates[0].changed_fields, ["title"])
            self.assertIn("기간 내 실제 정보 변경", candidates[0].reasons)

    def test_exact_link_grouping_keeps_country_and_product_variants(self):
        items = [event("a", source_url="https://example.com/product?id=1&utm_source=x#top"),
                 event("b", source_url="https://example.com/product?id=1"),
                 event("us", country="US", source_url="https://example.com/product?id=1"),
                 event("variant", source_url="https://example.com/product?id=2")]
        details = {item.id: {"types": {"NEW"}, "fields": set()} for item in items}
        candidates = select_candidates(items, details, NOW)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].related_ids, ["b"])
        self.assertEqual(len(select_candidates(items, details, NOW, source_country="US")), 1)

    def test_ending_and_keyword_signal(self):
        item = event(category=Category.OTHER, title="New コラボ announcement",
                     end_date=NOW + timedelta(days=2))
        candidates = select_candidates([item], {}, NOW)
        self.assertIn("종료까지 2일", candidates[0].reasons)
        self.assertIn("콜라보·협업", candidates[0].reasons)

    def test_cli_explanations_and_country_filter(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "events.db"
            with SQLiteRepository(database) as repository:
                repository.save_event(event(published_at=now, collected_at=now))
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["--db", str(database), "digest", "--source-country", "JP"]), 0)
            self.assertIn("선정 이유: 굿즈·상품", output.getvalue())
            self.assertIn("가격·통화", output.getvalue())
            self.assertIn("ID: goods", output.getvalue())


if __name__ == "__main__":
    unittest.main()
