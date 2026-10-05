import unittest
from dataclasses import replace
from datetime import datetime, timezone

from pokemon_events.models import Category, EventStatus, PokemonEvent
from pokemon_events.services import ChangeType, deduplicate_events
from pokemon_events.storage import SQLiteRepository


class RepositoryTest(unittest.TestCase):
    def test_schema_and_event_round_trip(self) -> None:
        now = datetime(2026, 9, 18, tzinfo=timezone.utc)
        event = PokemonEvent(
            id="pokemon-japan:11805",
            title="ポケモン公式イベント",
            category=Category.OTHER,
            pokemon=["ピカチュウ"],
            country="JP",
            source_country="KR",
            source_name="Pokémon Japan",
            source_url="https://www.pokemon.co.jp/info/example.html",
            collected_at=now,
            status=EventStatus.UPCOMING,
            content_hash="abc123",
            source_hash="source123",
            detail_hash="detail123",
            detail_checked_at=now,
        )

        with SQLiteRepository(":memory:") as repository:
            self.assertEqual(repository.save_event(event), ChangeType.NEW)
            self.assertEqual(repository.get_event(event.id), event)
            tables = {
                row[0]
                for row in repository.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

        self.assertTrue({"events", "event_history", "collection_runs", "sources"} <= tables)
        self.assertEqual(event.source_country, "KR")

        with self.assertRaises(ValueError):
            PokemonEvent(
                id="bad",
                title="bad dates",
                category=Category.OTHER,
                country="JP",
                source_name="test",
                source_url="https://example.com",
                collected_at=datetime(2026, 9, 18),
                content_hash="x",
            )

    def test_change_history_and_deduplication(self) -> None:
        first = datetime(2026, 9, 18, 1, tzinfo=timezone.utc)
        event = PokemonEvent(
            id="pokemon-japan:42",
            title="original",
            category=Category.OTHER,
            country="JP",
            source_name="Pokémon Japan",
            source_url="https://www.pokemon.co.jp/info/example.html",
            collected_at=first,
            content_hash="v1",
        )
        unchanged = replace(event, collected_at=first.replace(hour=2))
        updated = replace(unchanged, title="updated", content_hash="v2", collected_at=first.replace(hour=3))
        ended = replace(updated, status=EventStatus.ENDED, collected_at=first.replace(hour=4))

        self.assertEqual(deduplicate_events([event, unchanged]), [unchanged])
        with self.assertRaises(ValueError):
            deduplicate_events([event, updated])

        with SQLiteRepository(":memory:") as repository:
            changes = [repository.save_event(item) for item in (event, unchanged, updated, ended)]
            current = repository.get_event(event.id)
            history = repository.connection.execute(
                "SELECT change_type FROM event_history ORDER BY id"
            ).fetchall()
            seen = repository.connection.execute(
                "SELECT first_seen_at, last_seen_at FROM events WHERE id = ?", (event.id,)
            ).fetchone()

        self.assertEqual(
            changes,
            [ChangeType.NEW, ChangeType.UNCHANGED, ChangeType.UPDATED, ChangeType.ENDED],
        )
        self.assertEqual(current, ended)
        self.assertEqual([row[0] for row in history], ["NEW", "UPDATED", "ENDED"])
        self.assertEqual(seen["first_seen_at"], first.isoformat())
        self.assertEqual(seen["last_seen_at"], ended.collected_at.isoformat())

    def test_recent_changes_ignore_hash_only_updates(self) -> None:
        now = datetime(2026, 9, 18, tzinfo=timezone.utc)
        event = PokemonEvent(
            id="pokemon-japan:migration",
            title="same",
            category=Category.OTHER,
            country="JP",
            source_name="Pokémon Japan",
            source_url="https://www.pokemon.co.jp/info/same.html",
            collected_at=now,
            content_hash="old",
        )
        with SQLiteRepository(":memory:") as repository:
            repository.save_event(event)
            repository.save_event(
                replace(event, content_hash="new", source_hash="new")
            )
            changes = repository.get_recent_changes(now)

        self.assertEqual(changes[event.id], {"NEW"})


if __name__ == "__main__":
    unittest.main()
